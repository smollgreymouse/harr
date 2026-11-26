#include "AgentService.h"
#include "CodexService.h"
#include "ZcodeService.h"

#include <QtCore/QFileInfo>
#include <QtCore/QProcess>

namespace harr {

std::optional<QString> AgentService::validateSessionCwd(const QJsonObject &session, QString *error,
                                                        bool requireGit)
{
    return validateAgentCwd(session.value("cwd").toString().trimmed(), error, requireGit);
}

std::optional<QString> validateAgentCwd(const QString &cwdValue, QString *error, bool requireGit)
{
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

namespace {

// Codex keeps its previous behavior: metadata through the app-server API,
// turns through `codex exec`.
class CodexAgentService final : public AgentService {
public:
    QString id() const override { return QStringLiteral("codex"); }
    QString displayName() const override { return QStringLiteral("Codex"); }
    AgentCapabilities capabilities() const override
    {
        return {/*sessionRequired*/ true, /*sessionSelector*/ true, /*modelRequired*/ true,
                /*modelSelector*/ true, /*reasoning*/ true, /*speed*/ true, /*mode*/ false};
    }

    QVector<QJsonObject> listModels(QString *error, const QString &agentBin) override
    {
        return CodexService::listModels(error, agentBin);
    }

    QVector<QJsonObject> listSessions(QString *error, int limit, const QString &agentBin) override
    {
        return CodexService::listSessions(error, limit, agentBin);
    }

    std::optional<QJsonObject> readSession(const QString &session, QString *error,
                                           const QString &agentBin) override
    {
        return CodexService::readThread(session, error, agentBin);
    }

    std::optional<QString> validateSessionCwd(const QJsonObject &session, QString *error,
                                              bool requireGit) override
    {
        return CodexService::validateThreadCwd(session, error, requireGit);
    }

    QStringList execCommand(const AgentExecRequest &req, QString *error) override
    {
        const QString codex = CodexService::codexExecutable(req.agentBin);
        if (codex.isEmpty()) {
            if (error) *error = "codex executable not found";
            return {};
        }
        const QString serviceTier = req.speed == "fast" ? QStringLiteral("fast")
                                                        : QStringLiteral("default");
        QStringList args{
            codex, "exec", "-m", req.model,
            "-c", QString("service_tier=\"%1\"").arg(serviceTier),
            "-c", QString("model_reasoning_effort=\"%1\"").arg(req.reasoning)
        };
        if (req.emitEvents) args << QStringLiteral("--json");
        args << QStringLiteral("resume") << req.session << req.prompt;
        return args;
    }
};

// Zcode uses the public standalone CLI only. Session enumeration and the
// model catalog have no documented public CLI/API yet, so those lookups
// stay explicitly unavailable instead of falling back to internal state.
class ZcodeAgentService final : public AgentService {
public:
    QString id() const override { return QStringLiteral("zcode"); }
    QString displayName() const override { return QStringLiteral("ZCode"); }
    AgentCapabilities capabilities() const override
    {
        return {/*sessionRequired*/ false, /*sessionSelector*/ false, /*modelRequired*/ false,
                /*modelSelector*/ false, /*reasoning*/ false, /*speed*/ false, /*mode*/ true};
    }

    QVector<QJsonObject> listModels(QString *error, const QString &agentBin) override
    {
        Q_UNUSED(agentBin);
        if (error)
            *error = QStringLiteral(
                "zcode model catalog is not available via the public CLI yet");
        return {};
    }

    QVector<QJsonObject> listSessions(QString *error, int limit, const QString &agentBin) override
    {
        Q_UNUSED(limit);
        Q_UNUSED(agentBin);
        if (error)
            *error = QStringLiteral(
                "zcode session enumeration is not available via the public CLI yet");
        return {};
    }

    std::optional<QJsonObject> readSession(const QString &session, QString *error,
                                           const QString &agentBin) override
    {
        Q_UNUSED(session);
        Q_UNUSED(agentBin);
        if (error)
            *error = QStringLiteral(
                "zcode session metadata is not available via the public CLI yet");
        return std::nullopt;
    }

    QStringList execCommand(const AgentExecRequest &req, QString *error) override
    {
        return ZcodeService::turnCommand(req, error);
    }
};

} // namespace

QStringList agentIds() { return {QStringLiteral("codex"), QStringLiteral("zcode")}; }

QString agentDisplayName(const QString &agentId)
{
    if (AgentService *service = agentService(agentId)) return service->displayName();
    return agentId;
}

bool isKnownAgent(const QString &agentId) { return agentService(agentId) != nullptr; }

AgentService *agentService(const QString &agentId)
{
    static CodexAgentService codex;
    static ZcodeAgentService zcode;
    if (agentId == QLatin1String("codex")) return &codex;
    if (agentId == QLatin1String("zcode")) return &zcode;
    return nullptr;
}

QString defaultAgentId() { return QStringLiteral("codex"); }

} // namespace harr
