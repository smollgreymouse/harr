#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from typing import Any

XDG_CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
OPENCODE_DIR = XDG_CONFIG_HOME / "opencode"
JSONC = OPENCODE_DIR / "opencode.jsonc"
JSON = OPENCODE_DIR / "opencode.json"

OLD_AGENTS = {
    "flow",
    "wf-design",
    "wf-build",
    "reviewer",
    "explorer",
    "git",
    "codegraph",
    "lean-ctx",
    "lean-ctx-edit",
    "lean-ctx-shell",
    "lean-ctx-git",
}
OLD_COMMANDS = {
    "build-log.md",
    "build-ok.md",
    "quick.md",
    "review.md",
    "safe.md",
    "validate.md",
}
OLD_TOOL_KEYS = {
    "bash",
    "grep",
    "read",
    "edit",
    "write",
    "glob",
    "lean-ctx_*",
    "ctx_*",
    "codegraph_*",
}
OLD_PERMISSION_KEYS = OLD_TOOL_KEYS | {"task", "git_*"}


def strip_jsonc(text: str) -> str:
    out: list[str] = []
    i = 0
    in_string = False
    escaped = False
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if in_string:
            out.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue
        if ch == "/" and nxt == "/":
            i += 2
            while i < len(text) and text[i] not in "\r\n":
                i += 1
            continue
        if ch == "/" and nxt == "*":
            i += 2
            while i + 1 < len(text) and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(ch)
        i += 1

    cleaned = "".join(out)
    result: list[str] = []
    in_string = False
    escaped = False
    i = 0
    while i < len(cleaned):
        ch = cleaned[i]
        if in_string:
            result.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            result.append(ch)
            i += 1
            continue
        if ch == ",":
            j = i + 1
            while j < len(cleaned) and cleaned[j].isspace():
                j += 1
            if j < len(cleaned) and cleaned[j] in "}]":
                i += 1
                continue
        result.append(ch)
        i += 1
    return "".join(result)


def load_active() -> dict[str, Any]:
    source = JSONC if JSONC.exists() else JSON if JSON.exists() else None
    if source is None or not source.read_text(encoding="utf-8").strip():
        return {}
    raw = source.read_text(encoding="utf-8-sig")
    try:
        value = json.loads(strip_jsonc(raw))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"cannot parse OpenCode config {source}: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"OpenCode config must be an object: {source}")
    return value


def clean_mapping(config: dict[str, Any], key: str, owned: set[str]) -> None:
    value = config.get(key)
    if not isinstance(value, dict):
        return
    for owned_key in owned:
        value.pop(owned_key, None)
    if not value:
        config.pop(key, None)


def build_harr_config(current: dict[str, Any]) -> dict[str, Any]:
    config = dict(current)

    plugins = config.get("plugin")
    if isinstance(plugins, str):
        plugins = [plugins]
    if isinstance(plugins, list):
        plugins = [p for p in plugins if str(p).strip() != "opencode-mcp-triage"]
        if plugins:
            config["plugin"] = plugins
        else:
            config.pop("plugin", None)

    agents = config.get("agent")
    if isinstance(agents, dict):
        for name in OLD_AGENTS:
            agents.pop(name, None)
        if not agents:
            config.pop("agent", None)

    if config.get("default_agent") == "flow":
        config.pop("default_agent", None)
    if config.get("subagent_depth") == 2:
        config.pop("subagent_depth", None)

    clean_mapping(config, "tools", OLD_TOOL_KEYS)
    clean_mapping(config, "permission", OLD_PERMISSION_KEYS)

    mcp = config.get("mcp")
    if not isinstance(mcp, dict):
        mcp = {}
    else:
        mcp = dict(mcp)
    # Harr's normal OpenCode MCP surface is LeanCTX. Specialized Harr MCPs stay
    # behind LeanCTX; unrelated third-party MCP registrations are preserved.
    mcp.pop("codegraph", None)
    mcp.pop("gitlab", None)
    mcp["lean-ctx"] = {
        "type": "local",
        "command": ["lean-ctx"],
        "enabled": True,
    }
    config["mcp"] = mcp
    config.setdefault("$schema", "https://opencode.ai/config.json")
    return config


def apply() -> None:
    current = load_active()
    config = build_harr_config(current)
    OPENCODE_DIR.mkdir(parents=True, exist_ok=True)
    JSONC.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if JSON.exists():
        JSON.unlink()

    command_dir = OPENCODE_DIR / "commands"
    for name in OLD_COMMANDS:
        path = command_dir / name
        if path.exists() or path.is_symlink():
            path.unlink()

    print(f"Applied Harr OpenCode global harness config: {JSONC}")


def status() -> int:
    try:
        config = load_active()
    except Exception as exc:
        print(f"opencode-config\tinvalid\t{exc}")
        return 2

    problems: list[str] = []
    agents = config.get("agent")
    if isinstance(agents, dict):
        present = sorted(OLD_AGENTS.intersection(agents))
        if present:
            problems.append("legacy-agents=" + ",".join(present))

    plugins = config.get("plugin")
    if isinstance(plugins, str):
        plugins = [plugins]
    if isinstance(plugins, list) and "opencode-mcp-triage" in plugins:
        problems.append("legacy-triage-plugin")

    mcp = config.get("mcp")
    if not isinstance(mcp, dict) or "lean-ctx" not in mcp:
        problems.append("lean-ctx-missing")
    if isinstance(mcp, dict) and "codegraph" in mcp:
        problems.append("direct-codegraph-present")
    if isinstance(mcp, dict) and "gitlab" in mcp:
        problems.append("direct-gitlab-present")

    if problems:
        print("opencode-config\tstale\t" + ";".join(problems))
        return 1
    print(f"opencode-config\tmanaged\t{JSONC if JSONC.exists() else JSON}")
    return 0


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else "status"
    if command == "apply":
        apply()
        return 0
    if command == "status":
        return status()
    print("usage: opencode-config.py {apply|status}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
