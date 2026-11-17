#include "ZcodeService.h"
#include "Common.h"

#include <QtCore/QCoreApplication>
#include <QtCore/QDir>
#include <QtCore/QDirIterator>
#include <QtCore/QElapsedTimer>
#include <QtCore/QFile>
#include <QtCore/QFileInfo>
#include <QtCore/QJsonArray>
#include <QtCore/QJsonDocument>
#include <QtCore/QProcess>
#include <QtCore/QProcessEnvironment>
#include <QtCore/QStandardPaths>
#include <QtCore/QSysInfo>
#include <QtCore/QTextStream>

#include <algorithm>
#include <iostream>

namespace harr {

namespace {

void emitEvent(const QJsonObject &event)
{
    QTextStream(stdout) << QString::fromUtf8(QJsonDocument(event).toJson(QJsonDocument::Compact))
                        << '\n';
    std::cout.flush();
}

// The desktop passes its runtime builtin provider config through the
// environment; the bare launcher only sets the packaged copy, which lacks
// the account provider rules. Prefer the environment value, then the newest
// runtime copy under ~/.zcode/v2/runtime/provider/.
QString builtinConfigPath()
{
    const QString fromEnv = qEnvironmentVariable("ZCODE_BUILTIN_PROVIDER_CONFIG_FILE");
    if (!fromEnv.isEmpty() && QFileInfo::exists(fromEnv)) return fromEnv;

    QDir runtime = QDir::home().filePath(".zcode/v2/runtime/provider");
    if (!runtime.exists()) return {};
    QString newest;
    QDateTime newestModified;
    QDirIterator it(runtime.absolutePath(), {"zcode-builtin.json"}, QDir::Files,
                    QDirIterator::Subdirectories);
    while (it.hasNext()) {
        const QString path = it.next();
        if (!path.contains(QLatin1String("endpoint-"))) continue;
        const QDateTime modified = QFileInfo(path).lastModified();
        if (newest.isEmpty() || modified > newestModified) {
            newest = path;
            newestModified = modified;
        }
    }
    return newest;
}

// Model entries are keyed as "providerId/modelId" — the same selection
// string ZCode's own model picker reports.
QVector<QJsonObject> parseBuiltinModels(const QJsonObject &config, QString *error)
{
    QVector<QJsonObject> models;
    const QJsonObject rules = config.value("config").toObject()
                                  .value("providerConfigRules").toObject();
    for (const QJsonValue &value : rules.value("providerRules").toArray()) {
        const QJsonObject rule = value.toObject();
        const QJsonObject ruleConfig = rule.value("config").toObject();
        if (ruleConfig.value("access").toObject().value("type").toString()
            != QLatin1String("zhipu-account")) continue;
        const QString providerId = rule.value("providerId").toString().trimmed();
        const QString providerName = rule.value("providerName").toString().trimmed();
        if (providerId.isEmpty()) continue;
        for (const QJsonValue &modelValue : ruleConfig.value("builtinModelIds").toArray()) {
            const QString modelId = modelValue.toString().trimmed();
            if (modelId.isEmpty()) continue;
            models.push_back(QJsonObject{
                {"model", providerId + "/" + modelId},
                {"displayName", modelId},
                {"description", providerName},
                {"hidden", false},
                {"isDefault", false}
            });
        }
    }
    if (models.isEmpty() && error) *error = "no account models found in zcode builtin provider config";
    return models;
}

struct TurnTerminal {
    bool terminal = false;
    bool failed = false;
    QString message;
};

TurnTerminal classifyNotification(const QJsonObject &notification)
{
    TurnTerminal result;
    const QString method = notification.value("method").toString();
    const QJsonObject params = notification.value("params").toObject();

    // v4/telemetry/event kind=turn.terminal {status, errorCode?, errorMessage?}
    if (method == QLatin1String("v4/telemetry/event")
        && params.value("kind").toString() == QLatin1String("turn.terminal")) {
        result.terminal = true;
        const QString status = params.value("status").toString();
        result.failed = status != QLatin1String("completed") && status != QLatin1String("succeeded")
                        && status != QLatin1String("ok");
        QString text = params.value("errorMessage").toString();
        if (text.isEmpty()) text = params.value("errorCode").toString();
        if (text.isEmpty() && result.failed) text = "zcode turn finished with status " + status;
        result.message = text;
        return result;
    }
    // computer-use/operation-event kind=turn-started|turn-failed|turn-completed...
    if (method == QLatin1String("computer-use/operation-event")) {
        const QString kind = params.value("kind").toString();
        if (kind == QLatin1String("turn-failed")) {
            result.terminal = true;
            result.failed = true;
            result.message = "zcode turn failed";
            return result;
        }
        if (kind == QLatin1String("turn-completed") || kind == QLatin1String("turn-finished")) {
            result.terminal = true;
            return result;
        }
    }
    // state.updated carries coarse status flips (idle → running → idle).
    if (method == QLatin1String("state.updated")) {
        const QString status = params.value("patch").toObject().value("status").toString();
        if (!status.isEmpty()) result.message = "session " + status;
    }
    return result;
}

QString extractMessageText(const QJsonObject &message)
{
    QStringList parts;
    for (const QJsonValue &value : message.value("parts").toArray()) {
        if (value.isString()) {
            parts << value.toString();
            continue;
        }
        if (!value.isObject()) continue;
        const QJsonObject part = value.toObject();
        QString text = part.value("text").toString();
        if (text.isEmpty()) text = part.value("content").toString();
        if (!text.isEmpty()) parts << text;
    }
    return parts.join('\n').trimmed();
}

} // namespace

QString ZcodeService::zcodeExecutable(const QString &requested)
{
    if (!requested.isEmpty()) return requested;
    QString zcode = qEnvironmentVariable("ZCODE_BIN");
    if (!zcode.isEmpty()) return zcode;
    return QStandardPaths::findExecutable("zcode");
}

std::optional<QJsonObject> ZcodeService::request(const QString &method, const QJsonObject &params,
                                                 QString *error, const QString &zcodeBin,
                                                 int timeoutMs)
{
    const QString zcode = zcodeExecutable(zcodeBin);
    if (zcode.isEmpty()) {
        if (error) *error = "zcode executable not found";
        return std::nullopt;
    }

    QProcess proc;
    proc.setProgram(zcode);
    proc.setArguments({"app-server"});
    // Mirror the desktop's provider runtime wiring so the process sees the
    // same builtin config the desktop itself consumes.
    const QString builtin = builtinConfigPath();
    if (!builtin.isEmpty()) {
        QProcessEnvironment environment = QProcessEnvironment::systemEnvironment();
        environment.insert("ZCODE_BUILTIN_PROVIDER_CONFIG_FILE", builtin);
        const QString personal = QDir::home().filePath(".zcode/v2/provider_config.json");
        if (QFileInfo::exists(personal))
            environment.insert("ZCODE_PERSONAL_PROVIDER_CONFIG_FILE", personal);
        proc.setProcessEnvironment(environment);
    }
    proc.start();
    if (!proc.waitForStarted(std::min(timeoutMs, 5000))) {
        if (error) *error = "cannot start zcode app-server: " + proc.errorString();
        return std::nullopt;
    }

    proc.write(QJsonDocument(QJsonObject{{"method", method}, {"id", 1}, {"params", params}})
                   .toJson(QJsonDocument::Compact));
    proc.write("\n");
    proc.waitForBytesWritten(1000);

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
            if (!message.contains("id") || message.value("id").toInt(-1) != 1) {
                // Server-to-client request (id + method): method-not-found
                // triggers the server's compatibility fallback. Notifications
                // carry no id and are ignored.
                if (message.contains("id") && message.contains("method")
                    && !message.contains("result") && !message.contains("error")) {
                    const QJsonObject refusal{
                        {"id", message.value("id")},
                        {"error", QJsonObject{{"code", -32601}, {"message", "Method not found"}}}
                    };
                    proc.write(QJsonDocument(refusal).toJson(QJsonDocument::Compact));
                    proc.write("\n");
                    proc.waitForBytesWritten(1000);
                }
                continue;
            }
            if (message.contains("error")) {
                const QJsonValue value = message.value("error");
                QString detail;
                if (value.isObject()) detail = value.toObject().value("message").toString();
                if (detail.isEmpty()) detail = value.toVariant().toString();
                if (error) *error = "zcode app-server request failed: " + detail;
                proc.terminate();
                if (!proc.waitForFinished(1000)) proc.kill();
                return std::nullopt;
            }
            if (!message.value("result").isObject()) {
                if (error) *error = "zcode app-server returned malformed result";
                proc.terminate();
                if (!proc.waitForFinished(1000)) proc.kill();
                return std::nullopt;
            }
            proc.terminate();
            if (!proc.waitForFinished(1000)) proc.kill();
            return message.value("result").toObject();
        }
        if (proc.state() == QProcess::NotRunning) break;
    }
    if (error) {
        *error = QString("timed out waiting for zcode app-server response (%1)").arg(method);
        const QString stderrText = QString::fromUtf8(proc.readAllStandardError()).trimmed();
        if (!stderrText.isEmpty()) *error += "; app-server stderr: " + stderrText;
    }
    proc.terminate();
    if (!proc.waitForFinished(1000)) proc.kill();
    return std::nullopt;
}

QVector<QJsonObject> ZcodeService::listSessions(QString *error, int limit, const QString &zcodeBin)
{
    auto result = request("session/list", QJsonObject{}, error, zcodeBin);
    QVector<QJsonObject> sessions;
    if (!result) return sessions;
    for (const QJsonValue &value : result->value("sessions").toArray()) {
        if (!value.isObject()) continue;
        const QJsonObject raw = value.toObject();
        const QString id = raw.value("sessionId").toString().trimmed();
        if (id.isEmpty()) continue;
        if (raw.value("sessionKind").toString() == QLatin1String("subagent")) continue;
        const QString title = raw.value("title").toString();
        sessions.push_back(QJsonObject{
            {"id", id},
            {"name", title},
            {"preview", title},
            {"cwd", raw.value("workspace").toObject().value("workspacePath")},
            {"createdAt", raw.value("createdAt")},
            {"updatedAt", raw.value("updatedAt")},
            {"status", raw.value("status")},
            {"archived", false}
        });
    }
    std::sort(sessions.begin(), sessions.end(), [](const QJsonObject &a, const QJsonObject &b) {
        return a.value("updatedAt").toVariant().toLongLong()
             > b.value("updatedAt").toVariant().toLongLong();
    });
    if (limit > 0 && sessions.size() > limit) sessions.resize(limit);
    return sessions;
}

std::optional<QJsonObject> ZcodeService::readSession(const QString &session, QString *error,
                                                     const QString &zcodeBin)
{
    const auto sessions = listSessions(error, 0, zcodeBin);
    for (const QJsonObject &entry : sessions) {
        if (entry.value("id").toString() == session) return entry;
    }
    if (error && error->isEmpty())
        *error = "session not found in the zcode session list: " + session;
    return std::nullopt;
}

QVector<QJsonObject> ZcodeService::listModels(QString *error, const QString &zcodeBin)
{
    Q_UNUSED(zcodeBin);
    const QString path = builtinConfigPath();
    if (path.isEmpty()) {
        if (error) *error = "zcode builtin provider config not found";
        return {};
    }
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly)) {
        if (error) *error = "cannot read zcode builtin provider config: " + path;
        return {};
    }
    QJsonParseError parse;
    const QJsonDocument doc = QJsonDocument::fromJson(file.readAll(), &parse);
    if (parse.error != QJsonParseError::NoError || !doc.isObject()) {
        if (error) *error = "malformed zcode builtin provider config: " + path;
        return {};
    }
    return parseBuiltinModels(doc.object(), error);
}

int ZcodeService::runTurn(const QString &session, const QString &prompt, const QString &model,
                          const QString &mode, const QString &zcodeBin)
{
    // Upper bound for the whole turn; codex at-jobs have no timeout, but an
    // agent-exec process must not linger forever without a session runtime.
    constexpr int TURN_TIMEOUT_MS = 6 * 60 * 60 * 1000;
    constexpr int STEP_TIMEOUT_MS = 60 * 1000;

    const QString zcode = zcodeExecutable(zcodeBin);
    if (zcode.isEmpty()) {
        emitEvent(QJsonObject{{"type", "error"}, {"message", "zcode executable not found"}});
        return 127;
    }

    QProcess proc;
    proc.setProgram(zcode);
    proc.setArguments({"app-server"});
    proc.setProcessChannelMode(QProcess::SeparateChannels);
    const QString builtin = builtinConfigPath();
    if (!builtin.isEmpty()) {
        QProcessEnvironment environment = QProcessEnvironment::systemEnvironment();
        environment.insert("ZCODE_BUILTIN_PROVIDER_CONFIG_FILE", builtin);
        const QString personal = QDir::home().filePath(".zcode/v2/provider_config.json");
        if (QFileInfo::exists(personal))
            environment.insert("ZCODE_PERSONAL_PROVIDER_CONFIG_FILE", personal);
        proc.setProcessEnvironment(environment);
    }
    proc.start();
    if (!proc.waitForStarted(5000)) {
        emitEvent(QJsonObject{{"type", "error"},
                              {"message", "cannot start zcode app-server: " + proc.errorString()}});
        return 127;
    }

    int nextId = 1;
    auto send = [&](const QString &method, const QJsonObject &params) {
        const int id = nextId++;
        proc.write(QJsonDocument(QJsonObject{{"method", method}, {"id", id}, {"params", params}})
                       .toJson(QJsonDocument::Compact));
        proc.write("\n");
        proc.waitForBytesWritten(1000);
        return id;
    };
    auto refuse = [&](const QJsonObject &message) {
        proc.write(QJsonDocument(QJsonObject{
                          {"id", message.value("id")},
                          {"error", QJsonObject{{"code", -32601}, {"message", "Method not found"}}}})
                       .toJson(QJsonDocument::Compact));
        proc.write("\n");
        proc.waitForBytesWritten(1000);
    };
    auto terminate = [&proc]() {
        proc.terminate();
        if (!proc.waitForFinished(2000)) proc.kill();
        proc.waitForFinished(500);
    };
    auto fail = [&](const QString &message) {
        emitEvent(QJsonObject{{"type", "error"}, {"message", message}});
        terminate();
        return 1;
    };

    QElapsedTimer turnClock;
    turnClock.start();
    QByteArray pending;
    auto readMessage = [&]() -> std::optional<QJsonObject> {
        while (true) {
            // Drain complete lines already buffered, even while the server
            // is shutting down behind us.
            while (true) {
                const qsizetype newline = pending.indexOf('\n');
                if (newline < 0) break;
                const QByteArray line = pending.left(newline).trimmed();
                pending.remove(0, newline + 1);
                if (line.isEmpty()) continue;
                QJsonParseError parse;
                const QJsonDocument doc = QJsonDocument::fromJson(line, &parse);
                if (parse.error == QJsonParseError::NoError && doc.isObject()) return doc.object();
            }
            if (turnClock.elapsed() >= TURN_TIMEOUT_MS || proc.state() == QProcess::NotRunning)
                return std::nullopt;
            proc.waitForReadyRead(250);
            pending += proc.readAllStandardOutput();
        }
    };
    // Wait for the response to a specific request id. Notifications are
    // classified on the way; server-to-client requests (id + method) are
    // refused so the server applies its compatibility fallbacks.
    auto waitResponse = [&](int id, QString *error, int timeoutMs) -> std::optional<QJsonObject> {
        QElapsedTimer step;
        step.start();
        while (step.elapsed() < timeoutMs) {
            auto message = readMessage();
            if (!message) {
                if (error && error->isEmpty())
                    *error = proc.state() == QProcess::NotRunning
                                 ? QStringLiteral("zcode app-server exited unexpectedly")
                                 : QStringLiteral("timed out waiting for zcode app-server");
                return std::nullopt;
            }
            if (!message->contains("id")) {
                // Notification: watch for an early terminal event.
                const TurnTerminal terminal = classifyNotification(*message);
                if (terminal.terminal) {
                    if (error && !terminal.message.isEmpty()) *error = terminal.message;
                    return std::nullopt;
                }
                if (!terminal.message.isEmpty())
                    emitEvent(QJsonObject{{"type", "status"}, {"message", terminal.message}});
                continue;
            }
            if (message->contains("method") && !message->contains("result")
                && !message->contains("error")) {
                // Server-to-client request: refuse with method-not-found.
                refuse(*message);
                continue;
            }
            if (message->value("id").toInt(-1) != id) continue;
            if (message->contains("error")) {
                const QJsonValue value = message->value("error");
                QString detail;
                if (value.isObject()) detail = value.toObject().value("message").toString();
                if (detail.isEmpty()) detail = value.toVariant().toString();
                if (error) *error = detail;
                return std::nullopt;
            }
            return message->value("result").toObject();
        }
        if (error) *error = QStringLiteral("timed out waiting for zcode app-server response");
        return std::nullopt;
    };

    // Drain notifications until the turn reaches a terminal event. Returns 0
    // on a completed turn, 1 on failure, timeout or server exit.
    auto waitForTurnEnd = [&](QString *errorText) -> int {
        while (turnClock.elapsed() < TURN_TIMEOUT_MS && proc.state() != QProcess::NotRunning) {
            auto message = readMessage();
            if (!message) break;
            if (!message->contains("method")) continue; // stray response
            const TurnTerminal terminal = classifyNotification(*message);
            if (terminal.terminal)
                return terminal.failed ? 1 : 0;
            if (!terminal.message.isEmpty())
                emitEvent(QJsonObject{{"type", "status"}, {"message", terminal.message}});
            if (message->contains("id") && !message->contains("result")
                && !message->contains("error"))
                refuse(*message);
        }
        if (errorText)
            *errorText = proc.state() == QProcess::NotRunning
                             ? QStringLiteral("zcode app-server exited during the turn")
                             : QStringLiteral("zcode turn did not complete in time");
        return 1;
    };

    emitEvent(QJsonObject{{"type", "status"}, {"message", "resuming session " + session}});

    // session/create with sessionId resumes the persisted session; the
    // resume schema has no workspace/mode fields, so the session's own
    // project stays authoritative.
    QString error;
    const int createId = send("session/create",
                              QJsonObject{{"sessionId", session}, {"titleGenerationEnabled", false}});
    auto created = waitResponse(createId, &error, STEP_TIMEOUT_MS);
    if (!created) return fail(error.isEmpty() ? QStringLiteral("zcode session could not be resumed")
                                              : error);

    if (!mode.isEmpty()) {
        const int modeId = send("session/setMode",
                                QJsonObject{{"sessionId", session}, {"mode", mode}});
        QString modeError;
        auto applied = waitResponse(modeId, &modeError, STEP_TIMEOUT_MS);
        if (!applied)
            emitEvent(QJsonObject{{"type", "status"},
                                  {"message", "session/setMode ignored: " + modeError}});
    }

    const int readyId = send("session/lifecycle/ensureReady", QJsonObject{{"sessionId", session}});
    auto ready = waitResponse(readyId, &error, STEP_TIMEOUT_MS);
    if (!ready) return fail(error.isEmpty() ? QStringLiteral("zcode session runtime is not ready")
                                            : error);

    QJsonObject sendParams{{"sessionId", session}, {"content", prompt}};
    if (!model.isEmpty()) {
        const qsizetype slash = model.indexOf('/');
        if (slash > 0) {
            sendParams.insert("modelSelection",
                              QJsonObject{{"providerId", model.left(slash)},
                                          {"modelId", model.mid(slash + 1)}});
        } else {
            emitEvent(QJsonObject{
                {"type", "status"},
                {"message", "ignoring model override without providerId/: " + model}});
        }
    }
    emitEvent(QJsonObject{{"type", "status"}, {"message", "prompt submitted"}});
    const int sendId = send("session/send", sendParams);
    auto accepted = waitResponse(sendId, &error, STEP_TIMEOUT_MS);
    if (!accepted) return fail(error.isEmpty() ? QStringLiteral("zcode did not accept the prompt")
                                               : error);

    // The turn is running; drain notifications until its terminal event.
    QString turnError;
    if (waitForTurnEnd(&turnError) != 0) return fail(turnError);

    // Fetch the transcript and emit the final assistant message so the
    // saved answer and the task transcript stay complete.
    const int readId = send("session/read", QJsonObject{{"sessionId", session}});
    QString readError;
    auto transcript = waitResponse(readId, &readError, STEP_TIMEOUT_MS);
    if (transcript) {
        const QJsonArray messages = transcript->value("messages").toArray();
        for (int i = messages.size() - 1; i >= 0; --i) {
            const QJsonObject message = messages.at(i).toObject();
            const QJsonObject info = message.value("info").toObject();
            const QString kind = info.value("semantics").toObject().value("kind").toString();
            if (kind != QLatin1String("assistant_response")
                && info.value("role").toString() != QLatin1String("assistant"))
                continue;
            const QString text = extractMessageText(message);
            if (!text.isEmpty()) {
                emitEvent(QJsonObject{
                    {"type", "item.completed"},
                    {"item", QJsonObject{{"type", "agent_message"}, {"text", text}}}});
                break;
            }
        }
    } else {
        emitEvent(QJsonObject{{"type", "status"},
                              {"message", "could not read final answer: " + readError}});
    }
    emitEvent(QJsonObject{{"type", "turn.completed"}});
    terminate();
    return 0;
}

} // namespace harr
