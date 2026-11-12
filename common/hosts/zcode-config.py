#!/usr/bin/env python3
"""Harr host helper: manage the LeanCTX MCP registration in the global ZCode config.

Harr owns only the `mcp.servers["lean-ctx"]` entry of `~/.zcode/cli/config.json`.
Every other key (plugins, hooks, unrelated servers) is preserved untouched.
The ZCode policy keeps Harr MCP calls minimal, so unlike Codex/OpenCode no other
Harr MCP is registered for ZCode: CodeGraph and the enabled service MCPs are
reached through the LeanCTX gateway (`mcp__lean-ctx__ctx_tools`), and Workspace
authority uses the `harr workspace` CLI through the native shell.
"""
from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any

SERVER_NAME = "lean-ctx"


def default_leanctx_command() -> Path:
    explicit = os.environ.get("HARR_LEANCTX_COMMAND")
    if explicit:
        return Path(explicit).expanduser()
    if os.name == "nt":
        local = Path(os.environ.get("HARR_LOCALAPPDATA") or os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
        return local / "Harr" / "bin" / "lean-ctx.cmd"
    return Path.home() / ".local" / "bin" / "lean-ctx"


LEANCTX = default_leanctx_command()
ZCODE_HOME = Path(os.environ.get("HARR_ZCODE_HOME") or (Path.home() / ".zcode")).expanduser()
CONFIG = ZCODE_HOME / "cli" / "config.json"


def expected_entry() -> dict[str, Any]:
    return {"type": "stdio", "command": str(LEANCTX), "args": ["mcp"]}


def bootstrap_entry() -> dict[str, Any]:
    """The pre-Harr manual registration shape Harr may adopt."""
    return {"type": "stdio", "command": "lean-ctx", "args": ["mcp"]}


def load_config() -> dict[str, Any]:
    if not CONFIG.exists():
        return {}
    text = CONFIG.read_text(encoding="utf-8-sig")
    if not text.strip():
        return {}
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"cannot parse ZCode config {CONFIG}: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"ZCode config must contain a JSON object: {CONFIG}")
    return value


def current_entry(config: dict[str, Any]) -> dict[str, Any] | None:
    mcp = config.get("mcp")
    servers = mcp.get("servers") if isinstance(mcp, dict) else None
    if not isinstance(servers, dict):
        return None
    entry = servers.get(SERVER_NAME)
    return entry if isinstance(entry, dict) else None


def write_config(config: dict[str, Any]) -> None:
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    mode = stat.S_IMODE(CONFIG.stat().st_mode) if CONFIG.exists() else 0o644
    fd, tmp_name = tempfile.mkstemp(prefix="config.json.", dir=CONFIG.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(config, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.chmod(tmp_name, mode)
        except OSError:
            # Windows ACLs, not POSIX mode bits, control the effective access.
            pass
        os.replace(tmp_name, CONFIG)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


def apply() -> None:
    config = load_config()
    entry = current_entry(config)
    if entry is not None and entry not in (expected_entry(), bootstrap_entry()):
        raise RuntimeError(
            f"refusing to overwrite a foreign ZCode MCP entry for {SERVER_NAME!r} in {CONFIG}; "
            "remove or adjust it manually before applying Harr"
        )
    mcp = config.get("mcp")
    if not isinstance(mcp, dict):
        mcp = {}
        config["mcp"] = mcp
    servers = mcp.get("servers")
    if not isinstance(servers, dict):
        servers = {}
        mcp["servers"] = servers
    servers[SERVER_NAME] = expected_entry()
    write_config(config)
    print(f"Applied Harr ZCode MCP registration: {CONFIG}")


def status() -> int:
    if not CONFIG.exists():
        print(f"zcode-config\tmissing\t{CONFIG}")
        return 1
    try:
        config = load_config()
    except Exception as exc:
        print(f"zcode-config\tinvalid\t{exc}")
        return 2
    entry = current_entry(config)
    if entry is None:
        print(f"zcode-config\tmissing\tLeanCTX MCP not registered in {CONFIG}")
        return 1
    if entry == expected_entry():
        print(f"zcode-config\tmanaged\t{CONFIG}")
        return 0
    if entry == bootstrap_entry():
        print(f"zcode-config\tstale\tpre-Harr bootstrap entry (relative command); run apply to adopt {LEANCTX}")
        return 1
    print(
        "zcode-config\tstale\t"
        f"expected {expected_entry()!r}; got {entry!r}"
    )
    return 1


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else "status"
    if command == "apply":
        apply()
        return 0
    if command == "status":
        return status()
    print("usage: zcode-config.py {apply|status}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
