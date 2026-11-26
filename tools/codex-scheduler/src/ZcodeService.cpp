#include "ZcodeService.h"

#include <QtCore/QStandardPaths>

namespace harr {

QString ZcodeService::zcodeExecutable(const QString &requested)
{
    if (!requested.isEmpty()) return requested;
    const QString zcode = qEnvironmentVariable("ZCODE_BIN");
    if (!zcode.isEmpty()) return zcode;
    return QStandardPaths::findExecutable("zcode");
}

QStringList ZcodeService::turnCommand(const AgentExecRequest &req, QString *error)
{
    const QString zcode = zcodeExecutable(req.agentBin);
    if (zcode.isEmpty()) {
        if (error) *error = "zcode executable not found";
        return {};
    }
    if (req.prompt.trimmed().isEmpty()) {
        if (error) *error = "zcode turn requires --prompt";
        return {};
    }
    if (req.workspace.trimmed().isEmpty()) {
        if (error) *error = "zcode turn requires a verified working directory";
        return {};
    }
    // The CLI documents no --model launch flag: model selection is
    // configuration-driven, so req.model is intentionally not forwarded.
    QStringList args{
        zcode,
        QStringLiteral("--prompt"), req.prompt.trimmed(),
        QStringLiteral("--cwd"), req.workspace.trimmed(),
        QStringLiteral("--mode"), req.mode.trimmed().isEmpty() ? QStringLiteral("yolo")
                                                               : req.mode.trimmed(),
        QStringLiteral("--json")
    };
    if (!req.session.trimmed().isEmpty()) {
        args << QStringLiteral("--resume") << req.session.trimmed();
    }
    return args;
}

} // namespace harr
