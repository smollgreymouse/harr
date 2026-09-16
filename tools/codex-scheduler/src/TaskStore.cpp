#include "TaskStore.h"
#include "Common.h"

#include <QtCore/QDir>
#include <QtCore/QFile>
#include <QtCore/QFileInfo>
#include <QtCore/QJsonArray>
#include <QtCore/QJsonDocument>
#include <QtCore/QProcess>
#include <QtCore/QSaveFile>
#include <QtCore/QStandardPaths>
#include <QtCore/QUuid>

#include <algorithm>
#include <cerrno>
#include <stdexcept>
#include <sys/file.h>
#include <signal.h>

namespace harr {

bool writeJsonAtomic(const QString &path, const QJsonObject &object, QString *error)
{
    QDir().mkpath(QFileInfo(path).absolutePath());
    QSaveFile file(path);
    if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate)) {
        if (error) *error = file.errorString();
        return false;
    }
    const QByteArray data = QJsonDocument(object).toJson(QJsonDocument::Indented);
    if (file.write(data) != data.size()) {
        if (error) *error = file.errorString();
        return false;
    }
    if (!file.commit()) {
        if (error) *error = file.errorString();
        return false;
    }
    return true;
}

std::optional<QJsonObject> readJsonObject(const QString &path)
{
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly)) return std::nullopt;
    QJsonParseError parseError;
    const QJsonDocument doc = QJsonDocument::fromJson(file.readAll(), &parseError);
    if (parseError.error != QJsonParseError::NoError || !doc.isObject()) return std::nullopt;
    return doc.object();
}

TaskStore::TaskStore(QString root) : m_root(root.isEmpty() ? stateRootPath() : std::move(root))
{
    QDir().mkpath(tasksDir());
    QDir().mkpath(jobsDir());
}

QString TaskStore::root() const { return m_root; }
QString TaskStore::tasksDir() const { return QDir(m_root).filePath("tasks"); }
QString TaskStore::jobsDir() const { return QDir(m_root).filePath("jobs"); }
QString TaskStore::uiPath() const { return QDir(m_root).filePath("ui.json"); }
QString TaskStore::taskPath(const QString &id) const { return QDir(tasksDir()).filePath(id + ".json"); }

QJsonObject TaskStore::newDraft()
{
    const QString id = QUuid::createUuid().toString(QUuid::WithoutBraces).remove('-');
    const QString now = utcNow();
    QJsonObject task{
        {"id", id}, {"status", "draft"}, {"created_at", now}, {"updated_at", now},
        {"model", "gpt-5.6-terra"}, {"reasoning", "high"}, {"speed", "standard"},
        {"session", ""}, {"scheduled", QJsonValue::Null}, {"cwd", QJsonValue::Null}, {"prompt", ""},
        {"at_job", QJsonValue::Null}, {"pid", QJsonValue::Null},
        {"log", QDir(jobsDir()).filePath(id + ".jsonl")}, {"answer", QJsonValue::Null},
        {"cancel_requested", false}, {"error", QJsonValue::Null},
        {"started_at", QJsonValue::Null}, {"finished_at", QJsonValue::Null}
    };
    QString error;
    if (!writeJsonAtomic(taskPath(id), task, &error)) throw std::runtime_error(error.toStdString());
    return task;
}

std::optional<QJsonObject> TaskStore::load(const QString &id) const
{
    auto object = readJsonObject(taskPath(id));
    if (!object || object->value("id").toString() != id) return std::nullopt;
    return object;
}

QJsonObject TaskStore::patch(const QString &id, const QJsonObject &values)
{
    const QString path = taskPath(id);
    QDir().mkpath(QFileInfo(path).absolutePath());
    QFile lock(path + ".lock");
    if (!lock.open(QIODevice::ReadWrite)) throw std::runtime_error(lock.errorString().toStdString());
    if (::flock(lock.handle(), LOCK_EX) != 0) throw std::runtime_error("cannot lock task state");

    QJsonObject current;
    if (auto existing = readJsonObject(path)) current = *existing;
    for (auto it = values.begin(); it != values.end(); ++it) current.insert(it.key(), it.value());
    current.insert("updated_at", utcNow());

    QString error;
    const bool ok = writeJsonAtomic(path, current, &error);
    ::flock(lock.handle(), LOCK_UN);
    if (!ok) throw std::runtime_error(error.toStdString());
    return current;
}

QVector<QJsonObject> TaskStore::list() const
{
    QVector<QJsonObject> result;
    QDir dir(tasksDir());
    for (const QString &file : dir.entryList({"*.json"}, QDir::Files | QDir::Readable)) {
        const QString id = QFileInfo(file).completeBaseName();
        if (auto task = load(id)) result.push_back(*task);
    }
    std::sort(result.begin(), result.end(), [](const QJsonObject &a, const QJsonObject &b) {
        const QString ak = a.value("updated_at").toString(a.value("created_at").toString());
        const QString bk = b.value("updated_at").toString(b.value("created_at").toString());
        return ak > bk;
    });
    return result;
}

QJsonObject TaskStore::loadUi() const
{
    if (auto ui = readJsonObject(uiPath())) return *ui;
    return {{"open_task_ids", QJsonArray{}}, {"current_task_id", QJsonValue::Null}};
}

void TaskStore::saveUi(const QStringList &openIds, const QString &currentId)
{
    QJsonArray ids;
    for (const QString &id : openIds) if (!id.isEmpty()) ids.append(id);
    QJsonObject ui{{"open_task_ids", ids}, {"updated_at", utcNow()}};
    ui.insert("current_task_id", currentId.isEmpty() ? QJsonValue(QJsonValue::Null) : QJsonValue(currentId));
    QString error;
    if (!writeJsonAtomic(uiPath(), ui, &error)) throw std::runtime_error(error.toStdString());
}

bool TaskStore::isEmptyDraft(const QJsonObject &task) const
{
    return task.value("status").toString() == "draft"
        && task.value("session").toString().trimmed().isEmpty()
        && task.value("prompt").toString().trimmed().isEmpty()
        && (task.value("scheduled").isNull() || task.value("scheduled").toString().isEmpty())
        && (task.value("answer").isNull() || task.value("answer").toString().isEmpty());
}

QJsonObject TaskStore::cancel(const QString &id, QString *error)
{
    auto maybeTask = load(id);
    if (!maybeTask) { if (error) *error = "task not found"; return {}; }
    QJsonObject task = *maybeTask;
    const QString status = task.value("status").toString();
    if (status != "scheduled" && status != "running" && status != "cancelling") return task;

    patch(id, {{"cancel_requested", true}, {"status", "cancelling"}});
    if (status == "scheduled" && !task.value("at_job").toString().isEmpty()) {
        QString atrm = QStandardPaths::findExecutable("atrm");
        if (atrm.isEmpty()) atrm = "atrm";
        QProcess proc;
        proc.start(atrm, {task.value("at_job").toString()});
        proc.waitForFinished(5000);
        if (proc.exitStatus() == QProcess::NormalExit && proc.exitCode() == 0)
            return patch(id, {{"status", "cancelled"}, {"finished_at", utcNow()}, {"pid", QJsonValue::Null}});
    }

    task = load(id).value_or(task);
    const qint64 pid = task.value("pid").toVariant().toLongLong();
    if (pid > 0) {
        if (::kill(-static_cast<pid_t>(pid), SIGTERM) != 0 && errno != ESRCH) {
            if (error) *error = QString("cannot terminate process group %1: errno %2").arg(pid).arg(errno);
            return task;
        }
        return patch(id, {{"status", "cancelling"}, {"cancel_requested", true}});
    }
    if (status == "scheduled" && error) *error = "at job could not be removed and the task has not reported a running pid";
    return load(id).value_or(task);
}

bool TaskStore::remove(const QString &id, bool deleteLog, bool deleteAnswer, QString *error)
{
    auto task = load(id);
    if (!task) return true;
    const QString status = task->value("status").toString();
    if (status == "scheduled" || status == "running" || status == "cancelling") {
        if (error) *error = "cancel an active task before deleting it";
        return false;
    }
    if (deleteLog) QFile::remove(task->value("log").toString());
    if (deleteAnswer) QFile::remove(task->value("answer").toString());
    QFile::remove(taskPath(id));
    QFile::remove(taskPath(id) + ".lock");
    return true;
}

} // namespace harr
