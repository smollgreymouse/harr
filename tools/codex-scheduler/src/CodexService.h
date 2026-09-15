#pragma once

#include <QtCore/QJsonObject>
#include <QtCore/QString>
#include <QtCore/QVector>
#include <optional>

namespace harr {

class CodexService {
public:
    static QString codexExecutable(QString requested = {});
    static std::optional<QJsonObject> request(const QString &method, const QJsonObject &params,
                                              QString *error = nullptr, const QString &codexBin = {},
                                              int timeoutMs = 10000);
    static QVector<QJsonObject> listSessions(QString *error = nullptr, int limit = 50,
                                             const QString &codexBin = {});
    static std::optional<QJsonObject> readThread(const QString &session, QString *error = nullptr,
                                                 const QString &codexBin = {});
    static std::optional<QString> validateThreadCwd(const QJsonObject &thread, QString *error = nullptr,
                                                    bool requireGit = true);
    static std::optional<QString> resolveCwd(const QString &session, QString *error = nullptr,
                                             const QString &codexBin = {}, bool requireGit = true);
};

} // namespace harr
