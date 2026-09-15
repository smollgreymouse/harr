#pragma once

#include <QtCore/QJsonObject>
#include <QtCore/QStringList>
#include <QtCore/QVector>
#include <optional>

namespace harr {

class TaskStore {
public:
    explicit TaskStore(QString root = {});

    QString root() const;
    QString tasksDir() const;
    QString jobsDir() const;
    QString uiPath() const;
    QString taskPath(const QString &id) const;

    QJsonObject newDraft();
    std::optional<QJsonObject> load(const QString &id) const;
    QJsonObject patch(const QString &id, const QJsonObject &values);
    QVector<QJsonObject> list() const;
    QJsonObject loadUi() const;
    void saveUi(const QStringList &openIds, const QString &currentId);
    bool isEmptyDraft(const QJsonObject &task) const;
    QJsonObject cancel(const QString &id, QString *error = nullptr);
    bool remove(const QString &id, bool deleteLog, bool deleteAnswer, QString *error = nullptr);

private:
    QString m_root;
};

std::optional<QJsonObject> readJsonObject(const QString &path);
bool writeJsonAtomic(const QString &path, const QJsonObject &object, QString *error = nullptr);

} // namespace harr
