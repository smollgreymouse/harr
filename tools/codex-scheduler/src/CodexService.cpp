#include "CodexService.h"

#include <QtCore/QElapsedTimer>
#include <QtCore/QFileInfo>
#include <QtCore/QJsonArray>
#include <QtCore/QJsonDocument>
#include <QtCore/QProcess>
#include <QtCore/QStandardPaths>

#include <algorithm>

namespace harr {

QString CodexService::codexExecutable(QString requested)
{
    if (!requested.isEmpty()) return requested;
    requested = qEnvironmentVariable("CODEX_BIN");
    if (!requested.isEmpty()) return requested;
    return QStandardPaths::findExecutable("codex");
}

std::optional<QJsonObject> CodexService::request(const QString &method, const QJsonObject &params,
                                                 QString *error, const QString &codexBin, int timeoutMs)
{
    const QString codex = codexExecutable(codexBin);
    if (codex.isEmpty()) {
        if (error) *error = "codex executable not found";
        return std::nullopt;
    }

    QProcess proc;
    proc.setProgram(codex);
    proc.setArguments({"app-server"});
    proc.start();
    if (!proc.waitForStarted(std::min(timeoutMs, 3000))) {
        if (error) *error = "cannot start codex app-server: " + proc.errorString();
        return std::nullopt;
    }

    auto send = [&proc](const QJsonObject &object) {
        proc.write(QJsonDocument(object).toJson(QJsonDocument::Compact));
        proc.write("\n");
        proc.waitForBytesWritten(1000);
    };

    auto waitResponse = [&proc, timeoutMs](int id, QString *err) -> std::optional<QJsonObject> {
        QElapsedTimer timer;
        timer.start();
        QByteArray pending;
        while (timer.elapsed() < timeoutMs) {
            const int remaining = std::max(1, timeoutMs - static_cast<int>(timer.elapsed()));
            proc.waitForReadyRead(std::min(remaining, 250));
            pending += proc.readAllStandardOutput();
            while (true) {
                const qsizetype newline = pending.indexOf('\n');
                if (newline < 0) break;
                const QByteArray line = pending.left(newline).trimmed();
                pending.remove(0, newline + 1);
                if (line.isEmpty()) continue;
                QJsonParseError parse;
                const QJsonDocument doc = QJsonDocument::fromJson(line, &parse);
                if (parse.error != QJsonParseError::NoError || !doc.isObject()) continue;
                const QJsonObject message = doc.object();
                if (message.value("id").toInt(-1) != id) continue;
                if (message.contains("error")) {
                    const QJsonValue value = message.value("error");
                    QString detail;
                    if (value.isObject()) detail = value.toObject().value("message").toString();
                    if (detail.isEmpty()) detail = value.toVariant().toString();
                    if (err) *err = "codex app-server request failed: " + detail;
                    return std::nullopt;
                }
                if (!message.value("result").isObject()) {
                    if (err) *err = "codex app-server returned malformed result";
                    return std::nullopt;
                }
                return message.value("result").toObject();
            }
            if (proc.state() == QProcess::NotRunning && pending.isEmpty()) break;
        }
        if (err) {
            *err = QString("timed out waiting for codex app-server response id=%1").arg(id);
            const QString stderrText = QString::fromUtf8(proc.readAllStandardError()).trimmed();
            if (!stderrText.isEmpty()) *err += "; app-server stderr: " + stderrText;
        }
        return std::nullopt;
    };

    send({{"method", "initialize"}, {"id", 0}, {"params", QJsonObject{
        {"clientInfo", QJsonObject{{"name", "harr_codex_scheduler"}, {"title", "Harr Codex Scheduler"}, {"version", "2.0.0"}}}
    }}});
    QString localError;
    if (!waitResponse(0, &localError)) {
        proc.kill();
        proc.waitForFinished(1000);
        if (error) *error = localError;
        return std::nullopt;
    }

    send({{"method", "initialized"}, {"params", QJsonObject{}}});
    send({{"method", method}, {"id", 1}, {"params", params}});
    auto result = waitResponse(1, &localError);
    proc.terminate();
    if (!proc.waitForFinished(1000)) {
        proc.kill();
        proc.waitForFinished(1000);
    }
    if (!result && error) *error = localError;
    return result;
}

QVector<QJsonObject> CodexService::listSessions(QString *error, int limit, const QString &codexBin)
{
    QJsonArray sourceKinds;
    for (const QString &kind : {QString("cli"), QString("vscode"), QString("exec"), QString("appServer")}) sourceKinds.append(kind);
    const QJsonObject params{
        {"cursor", QJsonValue::Null},
        {"limit", std::clamp(limit, 1, 100)},
        {"sortKey", "recency_at"},
        {"sortDirection", "desc"},
        {"archived", false},
        {"sourceKinds", sourceKinds}
    };
    auto result = request("thread/list", params, error, codexBin);
    QVector<QJsonObject> sessions;
    if (!result) return sessions;
    for (const QJsonValue &value : result->value("data").toArray()) {
        if (!value.isObject()) continue;
        const QJsonObject raw = value.toObject();
        if (raw.value("archived").toBool(false)) continue;
        const QString id = raw.value("id").toString().trimmed();
        if (id.isEmpty()) continue;
        sessions.push_back({
            {"id", id}, {"name", raw.value("name")}, {"preview", raw.value("preview")},
            {"cwd", raw.value("cwd")}, {"createdAt", raw.value("createdAt")},
            {"updatedAt", raw.value("updatedAt")}, {"status", raw.value("status")}, {"archived", false}
        });
    }
    return sessions;
}

std::optional<QJsonObject> CodexService::readThread(const QString &session, QString *error, const QString &codexBin)
{
    auto result = request("thread/read", {{"threadId", session}, {"includeTurns", false}}, error, codexBin);
    if (!result || !result->value("thread").isObject()) {
        if (error && error->isEmpty()) *error = "thread/read response does not contain a thread object";
        return std::nullopt;
    }
    const QJsonObject thread = result->value("thread").toObject();
    const QString returnedId = thread.value("id").toString();
    if (!returnedId.isEmpty() && returnedId != session) {
        if (error) *error = "thread/read returned unexpected thread id";
        return std::nullopt;
    }
    return thread;
}

std::optional<QString> CodexService::validateThreadCwd(const QJsonObject &thread, QString *error, bool requireGit)
{
    const QString cwdValue = thread.value("cwd").toString().trimmed();
    QFileInfo info(cwdValue);
    if (cwdValue.isEmpty() || !info.isAbsolute() || !info.exists() || !info.isDir()) {
        if (error) *error = "saved session cwd does not exist or is not a directory: " + cwdValue;
        return std::nullopt;
    }
    const QString cwd = info.canonicalFilePath();
    if (requireGit) {
        QProcess git;
        git.start("git", {"-C", cwd, "rev-parse", "--show-toplevel"});
        if (!git.waitForFinished(5000) || git.exitStatus() != QProcess::NormalExit || git.exitCode() != 0) {
            if (error) *error = "session cwd is not a usable Git worktree: " + cwd;
            return std::nullopt;
        }
    }
    return cwd;
}

std::optional<QString> CodexService::resolveCwd(const QString &session, QString *error,
                                                const QString &codexBin, bool requireGit)
{
    auto thread = readThread(session, error, codexBin);
    if (!thread) return std::nullopt;
    return validateThreadCwd(*thread, error, requireGit);
}

} // namespace harr
