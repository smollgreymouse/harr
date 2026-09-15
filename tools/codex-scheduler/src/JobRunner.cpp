#include "Scheduler.h"
#include "Common.h"
#include "TaskStore.h"

#include <QtCore/QDir>
#include <QtCore/QFile>
#include <QtCore/QFileInfo>
#include <QtCore/QProcess>
#include <QtCore/QSaveFile>
#include <QtCore/QStandardPaths>
#include <QtCore/QTextStream>

namespace harr {

static std::optional<TaskStore> storeForTaskState(const QString &taskState)
{
    if (taskState.isEmpty()) return std::nullopt;
    QDir dir = QFileInfo(taskState).absoluteDir();
    if (dir.dirName() != "tasks") return std::nullopt;
    if (!dir.cdUp()) return std::nullopt;
    return TaskStore(dir.absolutePath());
}

int runJobRunner(const QStringList &args)
{
    QString logPath, answerPath, taskState;
    QStringList command;
    bool commandMode = false;
    for (int i = 0; i < args.size(); ++i) {
        const QString arg = args[i];
        if (commandMode) {
            command << arg;
            continue;
        }
        if (arg == "--") {
            commandMode = true;
            continue;
        }
        if (arg == "--log" && i + 1 < args.size()) logPath = args[++i];
        else if (arg == "--answer" && i + 1 < args.size()) answerPath = args[++i];
        else if (arg == "--task-state" && i + 1 < args.size()) taskState = args[++i];
        else {
            QTextStream(stderr) << "job-runner: unknown argument: " << arg << '\n';
            return 2;
        }
    }
    if (logPath.isEmpty() || command.isEmpty()) {
        QTextStream(stderr) << "job-runner: --log and command after -- are required\n";
        return 2;
    }

    QDir().mkpath(QFileInfo(logPath).absolutePath());
    QFile log(logPath);
    if (!log.open(QIODevice::WriteOnly | QIODevice::Truncate)) {
        QTextStream(stderr) << "job-runner: cannot open log: " << log.errorString() << '\n';
        return 2;
    }

    auto taskStore = storeForTaskState(taskState);
    const QString taskId = taskState.isEmpty() ? QString{} : QFileInfo(taskState).completeBaseName();
    auto patchState = [&](const QJsonObject &patch) {
        if (!taskStore || taskId.isEmpty()) return;
        try { taskStore->patch(taskId, patch); } catch (...) {}
    };

    QString program = command.takeFirst();
    QStringList processArgs = command;
    const QString setsid = QStandardPaths::findExecutable("setsid");
    if (!setsid.isEmpty()) {
        processArgs.prepend(program);
        program = setsid;
    }

    QProcess process;
    process.setProcessChannelMode(QProcess::MergedChannels);
    process.start(program, processArgs);
    if (!process.waitForStarted(5000)) {
        patchState({{"status", "failed"}, {"pid", QJsonValue::Null},
                    {"finished_at", utcNow()}, {"error", process.errorString()}});
        QTextStream(stderr) << "job-runner: cannot start command: " << process.errorString() << '\n';
        return 127;
    }

    const qint64 pid = process.processId();
    patchState({{"status", "running"}, {"pid", pid}, {"started_at", utcNow()},
                {"finished_at", QJsonValue::Null}, {"error", QJsonValue::Null}});

    QByteArray pending;
    QByteArray rawAll;
    QStringList assistantMessages;
    auto consume = [&](const QByteArray &chunk, bool final) {
        if (!chunk.isEmpty()) {
            log.write(chunk);
            log.flush();
            rawAll += chunk;
            pending += chunk;
        }
        while (true) {
            const qsizetype newline = pending.indexOf('\n');
            if (newline < 0) break;
            const QByteArray line = pending.left(newline);
            pending.remove(0, newline + 1);
            for (const auto &event : parseCodexJsonLine(line)) {
                if (event.kind == "assistant") assistantMessages << event.text;
            }
        }
        if (final && !pending.isEmpty()) {
            for (const auto &event : parseCodexJsonLine(pending)) {
                if (event.kind == "assistant") assistantMessages << event.text;
            }
            pending.clear();
        }
    };

    while (process.state() != QProcess::NotRunning) {
        process.waitForReadyRead(250);
        consume(process.readAll(), false);
    }
    process.waitForFinished(1000);
    consume(process.readAll(), true);
    const int rc = process.exitStatus() == QProcess::NormalExit ? process.exitCode() : 128;

    if (!answerPath.isEmpty()) {
        QString answer = assistantMessages.join("\n\n").trimmed();
        if (answer.isEmpty()) answer = QString::fromUtf8(rawAll).trimmed();
        QDir().mkpath(QFileInfo(answerPath).absolutePath());
        QSaveFile answerFile(answerPath);
        if (answerFile.open(QIODevice::WriteOnly | QIODevice::Truncate)) {
            if (!answer.isEmpty()) answer += '\n';
            answerFile.write(answer.toUtf8());
            answerFile.commit();
        }
    }

    bool cancelled = false;
    if (!taskState.isEmpty()) {
        if (auto state = readJsonObject(taskState)) cancelled = state->value("cancel_requested").toBool(false);
    }
    const QString finalStatus = cancelled ? "cancelled" : (rc == 0 ? "completed" : "failed");
    QJsonObject finalPatch{{"status", finalStatus}, {"pid", QJsonValue::Null}, {"finished_at", utcNow()}};
    if (!cancelled && rc != 0) finalPatch.insert("error", QString("Codex exited with status %1").arg(rc));
    else finalPatch.insert("error", QJsonValue::Null);
    patchState(finalPatch);
    return rc;
}

} // namespace harr
