#pragma once

#include <QtCore/QJsonObject>
#include <QtCore/QString>
#include <QtCore/QStringList>
#include <QtCore/QVector>

#include <optional>

namespace harr {

// Selector capabilities a task page renders for the agent.
struct AgentCapabilities {
    bool modelRequired = false; // refuse drafts without an explicit model
    bool reasoning = false;     // reasoning-effort selector (Codex)
    bool speed = false;         // service-tier selector (Codex)
    bool mode = false;          // permission-mode selector (ZCode)
};

// What one agent turn needs at execution time. The adapter turns this into
// the concrete command line placed after "--" in an at job.
struct AgentExecRequest {
    QString session;
    QString prompt;
    QString model;      // optional override, agent-specific format
    QString reasoning;  // codex only
    QString speed;      // codex only
    QString mode;       // zcode only
    QString agentBin;   // optional explicit agent binary (--codex-bin and friends)
    bool emitEvents = false; // request structured JSONL events on stdout
};

// One adapter per supported agent. All methods are blocking one-shot calls;
// adapters own their transport (app-server stdio, CLI shells). Session and
// model entries follow the codex shape so widgets stay agent-agnostic:
// sessions carry {"id", "name", "preview", "cwd", "archived", ...} and
// models carry {"model"/"id", "displayName", "hidden", "isDefault"}.
class AgentService {
public:
    virtual ~AgentService() = default;

    virtual QString id() const = 0;
    virtual QString displayName() const = 0;
    virtual AgentCapabilities capabilities() const = 0;
    virtual QVector<QJsonObject> listModels(QString *error, const QString &agentBin = {}) = 0;
    virtual QVector<QJsonObject> listSessions(QString *error, int limit = 50,
                                              const QString &agentBin = {}) = 0;
    virtual std::optional<QJsonObject> readSession(const QString &session, QString *error,
                                                   const QString &agentBin = {}) = 0;
    virtual std::optional<QString> validateSessionCwd(const QJsonObject &session, QString *error,
                                                      bool requireGit);
    // Full command (program + arguments) that runs one agent turn; empty
    // result means a refusal, with *error explaining why.
    virtual QStringList execCommand(const AgentExecRequest &req, QString *error) = 0;
};

QStringList agentIds();
QString agentDisplayName(const QString &agentId);
bool isKnownAgent(const QString &agentId);
AgentService *agentService(const QString &agentId);
QString defaultAgentId();

// Shared cwd validation: absolute, existing, optional Git worktree.
std::optional<QString> validateAgentCwd(const QString &cwd, QString *error, bool requireGit);

} // namespace harr
