#pragma once

#include <QtCore/QJsonObject>
#include <QtCore/QString>
#include <QtCore/QVector>

#include <optional>

namespace harr {

// Client for the ZCode Protocol stdio app-server (`zcode app-server`).
// Metadata calls are one-shot: spawn, newline-delimited JSON-RPC exchange,
// terminate. Server-to-client requests are answered with JSON-RPC method
// not found so the server applies its compatibility fallbacks.
//
// Turn execution (`runTurn`) keeps one app-server process alive for the
// whole turn: session/create (resume) → lifecycle ensureReady → session/send
// → notifications, then emits codex-style JSONL events on stdout so
// JobRunner can log and render the transcript with its existing parser.
//
// Note: as of ZCode CLI 0.17.x a standalone app-server has an empty model
// registry (models are injected by the desktop client), so turns fail with
// a clear configuration error until ZCode exposes standalone model
// resolution. Metadata and catalogs work regardless.
class ZcodeService {
public:
    static QString zcodeExecutable(const QString &requested = {});

    static std::optional<QJsonObject> request(const QString &method, const QJsonObject &params,
                                              QString *error = nullptr, const QString &zcodeBin = {},
                                              int timeoutMs = 20000);
    // {"id","name","preview","cwd","archived":false,"updatedAt","status"} entries.
    static QVector<QJsonObject> listSessions(QString *error = nullptr, int limit = 50,
                                             const QString &zcodeBin = {});
    // Single entry from the session list, or nullopt when absent.
    static std::optional<QJsonObject> readSession(const QString &session, QString *error = nullptr,
                                                  const QString &zcodeBin = {});
    // Model catalog from the agent's own builtin provider config
    // (ZCODE_BUILTIN_PROVIDER_CONFIG_FILE, runtime path fallback). Codex-shape
    // entries whose "model" is the "providerId/modelId" selection string.
    static QVector<QJsonObject> listModels(QString *error = nullptr, const QString &zcodeBin = {});

    // Run one turn in an existing session; prints codex-style JSONL events to
    // stdout. Returns the process exit code (0 = turn completed).
    static int runTurn(const QString &session, const QString &prompt, const QString &model,
                       const QString &mode, const QString &zcodeBin = {});
};

} // namespace harr
