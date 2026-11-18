#!/usr/bin/env python3
"""Run one LeanCTX MCP host profile without changing global environment/config."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
import sys

PROFILES = {"zcode": "harr-zcode", "opencode": "harr-opencode"}


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] not in PROFILES:
        print("usage: leanctx-mcp-host.py {zcode|opencode} LEANCTX_BINARY", file=sys.stderr)
        return 2
    binary = Path(sys.argv[2]).expanduser()
    if not binary.is_file():
        print(f"LeanCTX binary does not exist: {binary}", file=sys.stderr)
        return 1
    env = os.environ.copy()
    env["LEAN_CTX_CONFIG_PROFILE"] = PROFILES[sys.argv[1]]
    if os.name == "nt":
        return subprocess.call([str(binary), "mcp"], env=env)
    os.execve(str(binary), [str(binary), "mcp"], env)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
