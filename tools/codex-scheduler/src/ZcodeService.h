#pragma once

#include <QtCore/QString>
#include <QtCore/QStringList>

#include "AgentService.h"

namespace harr {

// ZCode adapter over the public standalone CLI contract only:
//   zcode [--resume <sessionId>] --prompt <text> --cwd <workspace>
//         --mode <mode> --json
// No `zcode app-server`, no JSON-RPC session calls, no desktop attachment,
// and no reading of internal provider/runtime state. Session enumeration
// and the model catalog have no documented public CLI/API yet, so those
// surfaces stay explicitly unavailable until ZCode ships them.
class ZcodeService {
public:
    static QString zcodeExecutable(const QString &requested = {});

    // Full command (program + arguments) for one scheduled turn. The turn
    // resumes the given session when one is set, otherwise starts a new
    // turn in the workspace. Requires prompt and workspace.
    static QStringList turnCommand(const AgentExecRequest &req, QString *error);
};

} // namespace harr
