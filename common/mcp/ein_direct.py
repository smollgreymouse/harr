#!/usr/bin/env python3
"""Direct Codex frontdoor for one named Ein instance.

This wrapper keeps Codex Desktop's MCP App surface on the named Ein server while
reusing the same runtime preparation as the LeanCTX gateway path.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.mcp.ein_instances import prepare_instance_runtime_env


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: ein_direct.py <instance>", file=sys.stderr)
        return 2
    instance = sys.argv[1]
    env = prepare_instance_runtime_env(instance, os.environ.copy())
    env["HARR_EIN_MCP_APP"] = "1"

    icon = Path(__file__).with_name("assets") / "harr.png"
    if not icon.is_file():
        source_icon = ROOT / "harr.png"
        if source_icon.is_file():
            icon = source_icon
    if icon.is_file():
        env["HARR_MCP_ICON_PATH"] = str(icon)

    server = Path(__file__).with_name("einherjar_server.py")
    command = [sys.executable, str(server)]
    if os.name == "nt":
        return subprocess.call(command, env=env)
    os.execvpe(command[0], command, env)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
