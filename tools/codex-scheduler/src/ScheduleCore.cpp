#include "Scheduler.h"
#include "CodexService.h"
#include "Common.h"

#include <QtCore/QCoreApplication>
#include <QtCore/QDateTime>
#include <QtCore/QDir>
#include <QtCore/QFileInfo>
#include <QtCore/QJsonArray>
#include <QtCore/QJsonDocument>
#include <QtCore/QProcess>
#include <QtCore/QRegularExpression>
#include <QtCore/QStandardPaths>
#include <QtCore/QTextStream>

#include <unistd.h>

namespace harr {

static bool validateTimestamp(const QString &value, QString *error)
{
    if (!QRegularExpression("^[0-9]{12}$").match(value).hasMatch()) {
        if (error) *error = "invalid --timestamp (expected CCYYMMDDhhmm): " + value;
        return false;
    }
    const QDateTime dt = QDateTime::fromString(value, "yyyyMMddHHmm");
    if (!dt.isValid() || dt.toString("yyyyMMddHHmm") != value) {
        if (error) *error = "invalid calendar date/time for --timestamp: " + value;
        return false;
    }
    if (dt <= QDateTime::currentDateTime()) {
        if (error) *error = "--timestamp must be in the future: " + value;
        return false;
    }
    return true;
}

static bool validateAtSpec(const QString &value, QString *error)
{
    const auto match = QRegularExpression("^([0-9]{1,2}):([0-9]{2})$").match(value);
    if (!match.hasMatch()) return true;
    if (match.captured(1).toInt() > 23 || match.captured(2).toInt() > 59) {
        if (error) *error = "invalid HH:MM --at time: " + value;
        return false;
    }
    return true;
}

ScheduleResult scheduleJob(ScheduleRequest req)
{
    ScheduleResult result;
    if (req.model.isEmpty() || req.session.trimmed().isEmpty() || req.prompt.trimmed().isEmpty()) {
        result.output = "--model, --session and --prompt are required";
        return result;
    }
    if (req.atSpec.isEmpty() == req.timestamp.isEmpty()) {
        result.output = "specify exactly one of --at or --timestamp";
        return result;
    }
    if (!req.taskState.isEmpty() && req.logJson.isEmpty()) {
        result.output = "--task-state requires --log-json";
        return result;
    }
    if (!QStringList{"minimal", "low", "medium", "high", "xhigh"}.contains(req.reasoning)) {
        result.output = "unsupported reasoning: " + req.reasoning;
        return result;
    }
    if (req.speed != "standard" && req.speed != "fast") {
        result.output = "unsupported speed: " + req.speed;
        return result;
    }

    QString validationError;
    if ((!req.timestamp.isEmpty() && !validateTimestamp(req.timestamp, &validationError)) ||
        (!req.atSpec.isEmpty() && !validateAtSpec(req.atSpec, &validationError))) {
        result.output = validationError;
        return result;
    }

    if (req.codexBin.isEmpty()) req.codexBin = CodexService::codexExecutable();
    if (req.atBin.isEmpty()) {
        req.atBin = qEnvironmentVariable("AT_BIN");
        if (req.atBin.isEmpty()) req.atBin = QStandardPaths::findExecutable("at");
    }
    if (req.codexBin.isEmpty()) {
        result.exitCode = 127;
        result.output = "codex executable not found";
        return result;
    }
    if (req.atBin.isEmpty()) {
        result.exitCode = 127;
        result.output = "at executable not found (install package: at)";
        return result;
    }

    QString resolveError;
    auto resolved = CodexService::resolveCwd(req.session, &resolveError, req.codexBin, true);
    QString cwd = resolved.value_or(QString{});
    if (!req.manualCwd.isEmpty()) {
        QFileInfo manualInfo(req.manualCwd);
        const QString manual = manualInfo.canonicalFilePath();
        if (manual.isEmpty() || !QFileInfo(manual).isDir()) {
            result.output = "working directory does not exist: " + req.manualCwd;
            return result;
        }
        QProcess git;
        git.start("git", {"-C", manual, "rev-parse", "--show-toplevel"});
        git.waitForFinished(5000);
        if (git.exitStatus() != QProcess::NormalExit || git.exitCode() != 0) {
            result.output = "--cwd is not inside a Git worktree: " + manual;
            return result;
        }
        if (!cwd.isEmpty() && cwd != manual) {
            result.output = QString("--cwd mismatch: session says '%1' but override says '%2'").arg(cwd, manual);
            return result;
        }
        cwd = manual;
    } else if (cwd.isEmpty()) {
        result.output = resolveError + "\nrefusing to schedule without a verified session cwd";
        return result;
    }

    const QString serviceTier = req.speed == "fast" ? "fast" : "default";
    QStringList codexArgs{
        "exec", "-m", req.model,
        "-c", QString("service_tier=\"%1\"").arg(serviceTier),
        "-c", QString("model_reasoning_effort=\"%1\"").arg(req.reasoning)
    };
    if (!req.logJson.isEmpty()) codexArgs << "--json";
    codexArgs << "resume" << req.session << req.prompt;

    QString job = "cd " + shellQuote(cwd) + " || exit 125; ";
    if (!req.logJson.isEmpty()) {
        QDir().mkpath(QFileInfo(req.logJson).absolutePath());
        req.logJson = QFileInfo(req.logJson).absoluteFilePath();
        QStringList runner{QCoreApplication::applicationFilePath(), "job-runner", "--log", req.logJson};
        if (!req.saveAnswer.isEmpty()) {
            QDir().mkpath(QFileInfo(req.saveAnswer).absolutePath());
            req.saveAnswer = QFileInfo(req.saveAnswer).absoluteFilePath();
            runner << "--answer" << req.saveAnswer;
        }
        if (!req.taskState.isEmpty()) {
            QDir().mkpath(QFileInfo(req.taskState).absolutePath());
            req.taskState = QFileInfo(req.taskState).absoluteFilePath();
            runner << "--task-state" << req.taskState;
        }
        runner << "--" << req.codexBin;
        runner << codexArgs;
        for (const QString &arg : runner) job += shellQuote(arg) + " ";
    } else {
        QStringList command{req.codexBin};
        command << codexArgs;
        for (const QString &arg : command) job += shellQuote(arg) + " ";
        if (!req.output.isEmpty()) {
            QDir().mkpath(QFileInfo(req.output).absolutePath());
            job += "> " + shellQuote(QFileInfo(req.output).absoluteFilePath()) + " 2>&1";
        } else {
            if (req.ttyPath.isEmpty()) req.ttyPath = qEnvironmentVariable("TTY_PATH");
            if (req.ttyPath.isEmpty()) {
                if (const char *tty = ::ttyname(STDOUT_FILENO)) req.ttyPath = QString::fromLocal8Bit(tty);
            }
            if (req.ttyPath.isEmpty() || req.ttyPath == "not a tty") {
                result.output = "no TTY available; use --output or --log-json";
                return result;
            }
            job += "> " + shellQuote(req.ttyPath) + " 2>&1";
        }
    }

    QProcess at;
    QStringList atArgs;
    if (!req.timestamp.isEmpty()) atArgs << "-t" << req.timestamp;
    else atArgs << req.atSpec;
    at.start(req.atBin, atArgs);
    if (!at.waitForStarted(3000)) {
        result.exitCode = 127;
        result.output = "cannot start at: " + at.errorString();
        return result;
    }
    at.write(job.toUtf8());
    at.write("\n");
    at.closeWriteChannel();
    if (!at.waitForFinished(10000)) {
        at.kill();
        at.waitForFinished(1000);
        result.output = "at timed out";
        return result;
    }
    const QString combined = QString::fromUtf8(at.readAllStandardOutput() + at.readAllStandardError()).trimmed();
    if (at.exitStatus() != QProcess::NormalExit || at.exitCode() != 0) {
        result.exitCode = at.exitCode();
        result.output = combined;
        return result;
    }

    const auto match = QRegularExpression("\\bjob\\s+(\\d+)\\b").match(combined);
    result.ok = true;
    result.exitCode = 0;
    result.output = combined;
    result.cwd = cwd;
    if (match.hasMatch()) result.jobId = match.captured(1);
    return result;
}

int runScheduleCli(const QStringList &args)
{
    ScheduleRequest req;
    for (int i = 0; i < args.size(); ++i) {
        const QString arg = args[i];
        auto next = [&](QString &dst) -> bool {
            if (i + 1 >= args.size()) return false;
            dst = args[++i];
            return true;
        };
        if (arg == "--model") { if (!next(req.model)) return 2; }
        else if (arg == "--reasoning") { if (!next(req.reasoning)) return 2; }
        else if (arg == "--speed") { if (!next(req.speed)) return 2; }
        else if (arg == "--at") { if (!next(req.atSpec)) return 2; }
        else if (arg == "--timestamp") { if (!next(req.timestamp)) return 2; }
        else if (arg == "--session") { if (!next(req.session)) return 2; }
        else if (arg == "--prompt") { if (!next(req.prompt)) return 2; }
        else if (arg == "--cwd") { if (!next(req.manualCwd)) return 2; }
        else if (arg == "--output") { if (!next(req.output)) return 2; }
        else if (arg == "--log-json") { if (!next(req.logJson)) return 2; }
        else if (arg == "--save-answer") { if (!next(req.saveAnswer)) return 2; }
        else if (arg == "--task-state") { if (!next(req.taskState)) return 2; }
        else if (arg == "--tty") { if (!next(req.ttyPath)) return 2; }
        else if (arg == "--codex-bin") { if (!next(req.codexBin)) return 2; }
        else if (arg == "--at-bin") { if (!next(req.atBin)) return 2; }
        else if (arg == "-h" || arg == "--help") {
            QTextStream(stdout) << "Usage: harr-codex-scheduler schedule --model MODEL (--at SPEC | --timestamp CCYYMMDDhhmm) --session ID --prompt TEXT [options]\n";
            return 0;
        } else {
            QTextStream(stderr) << "codex-schedule: unknown argument: " << arg << '\n';
            return 2;
        }
    }
    const auto result = scheduleJob(req);
    if (!result.ok) {
        QTextStream(stderr) << "codex-schedule: " << result.output << '\n';
        return result.exitCode;
    }
    QTextStream(stdout) << "session cwd: " << result.cwd << '\n' << result.output << '\n';
    return 0;
}

int runSessionListCli(const QStringList &args)
{
    int limit = 50;
    QString codex;
    for (int i = 0; i < args.size(); ++i) {
        if (args[i] == "--limit" && i + 1 < args.size()) limit = args[++i].toInt();
        else if (args[i] == "--codex-bin" && i + 1 < args.size()) codex = args[++i];
        else return 2;
    }
    QString error;
    const auto sessions = CodexService::listSessions(&error, limit, codex);
    if (!error.isEmpty() && sessions.isEmpty()) {
        QTextStream(stderr) << error << '\n';
        return 2;
    }
    QJsonArray array;
    for (const auto &session : sessions) array.append(session);
    QTextStream(stdout) << QJsonDocument(array).toJson(QJsonDocument::Compact) << '\n';
    return 0;
}

int runSessionCwdCli(const QStringList &args)
{
    QString session, codex;
    bool requireGit = true;
    for (int i = 0; i < args.size(); ++i) {
        if (args[i] == "--session" && i + 1 < args.size()) session = args[++i];
        else if (args[i] == "--codex-bin" && i + 1 < args.size()) codex = args[++i];
        else if (args[i] == "--no-git-check") requireGit = false;
        else return 2;
    }
    QString error;
    auto cwd = CodexService::resolveCwd(session, &error, codex, requireGit);
    if (!cwd) {
        QTextStream(stderr) << error << '\n';
        return 2;
    }
    QTextStream(stdout) << *cwd << '\n';
    return 0;
}

} // namespace harr
