#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
from typing import Any

SERVER_NAME = "lean-ctx"
DEFAULT_TOOLS_APPROVAL_MODE = "auto"
CODEX_HOME = Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex")).expanduser()
CONFIG = CODEX_HOME / "config.toml"


def default_leanctx_command() -> Path:
    explicit = os.environ.get("HARR_LEANCTX_COMMAND")
    if explicit:
        return Path(explicit).expanduser()
    if os.name == "nt":
        local = Path(os.environ.get("HARR_LOCALAPPDATA") or os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
        return local / "Harr" / "bin" / "lean-ctx.cmd"
    return Path.home() / ".local" / "bin" / "lean-ctx"


LEANCTX = default_leanctx_command()
_TABLE_RE = re.compile(r"^\s*\[(?!\[)(.*)\]\s*(?:#.*)?$")
_ARRAY_TABLE_RE = re.compile(r"^\s*\[\[(.*)\]\]\s*(?:#.*)?$")
_DEFAULT_TOOLS_APPROVAL_RE = re.compile(r"^\s*default_tools_approval_mode\s*=")


def load_config_text() -> str:
    return CONFIG.read_text(encoding="utf-8") if CONFIG.exists() else ""


def parse_config(text: str) -> dict[str, Any]:
    if not text.strip():
        return {}
    try:
        value = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise RuntimeError(f"cannot parse Codex config {CONFIG}: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"Codex config must contain a TOML object: {CONFIG}")
    return value


def expected_entry() -> dict[str, Any]:
    return {
        "command": str(LEANCTX),
        "enabled": True,
        "default_tools_approval_mode": DEFAULT_TOOLS_APPROVAL_MODE,
    }


def current_entry(config: dict[str, Any]) -> dict[str, Any] | None:
    servers = config.get("mcp_servers")
    if not isinstance(servers, dict):
        return None
    entry = servers.get(SERVER_NAME)
    return entry if isinstance(entry, dict) else None


def entry_is_managed(entry: dict[str, Any] | None) -> bool:
    if entry is None:
        return False
    return (
        entry.get("command") == str(LEANCTX)
        and entry.get("enabled", True) is True
        and entry.get("default_tools_approval_mode") == DEFAULT_TOOLS_APPROVAL_MODE
    )


def codex_cli() -> str | None:
    if os.environ.get("HARR_CODEX_DISABLE_CLI") == "1":
        return None
    explicit = os.environ.get("HARR_CODEX_CLI")
    return explicit or shutil.which("codex")


def apply_with_codex_cli(binary: str) -> None:
    CODEX_HOME.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["CODEX_HOME"] = str(CODEX_HOME)
    result = subprocess.run(
        [binary, "mcp", "add", SERVER_NAME, "--", str(LEANCTX)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
        timeout=60,
    )
    if result.returncode != 0:
        output = result.stdout.strip()
        raise RuntimeError(
            f"official Codex MCP writer failed ({binary} mcp add): {output or f'exit {result.returncode}'}"
        )

    # The official writer can replace this MCP table, so restore Harr's trust
    # setting after it runs instead of relying on the writer to preserve it.
    ensure_default_tools_approval_mode()
    data = parse_config(load_config_text())
    if not entry_is_managed(current_entry(data)):
        raise RuntimeError("Codex CLI completed but LeanCTX MCP registration is not the expected Harr entry")
    print(f"Applied Harr Codex MCP registration using official Codex CLI: {CONFIG}")


def parse_dotted_key(expr: str) -> list[str] | None:
    try:
        value: Any = tomllib.loads(f"{expr} = 0")
    except tomllib.TOMLDecodeError:
        return None
    path: list[str] = []
    while isinstance(value, dict) and len(value) == 1:
        key, value = next(iter(value.items()))
        path.append(str(key))
    return path if value == 0 else None


def table_header(line: str) -> tuple[str, list[str]] | None:
    match = _ARRAY_TABLE_RE.match(line)
    if match:
        path = parse_dotted_key(match.group(1).strip())
        return ("array", path) if path else None
    match = _TABLE_RE.match(line)
    if match:
        path = parse_dotted_key(match.group(1).strip())
        return ("table", path) if path else None
    return None


def is_target_path(path: list[str]) -> bool:
    return len(path) >= 2 and path[0] == "mcp_servers" and path[1] == SERVER_NAME


def remove_existing_target_tables(text: str, had_target: bool) -> str:
    lines = text.splitlines(keepends=True)
    remove = [False] * len(lines)
    found_target_table = False
    i = 0
    while i < len(lines):
        header = table_header(lines[i])
        if header is None:
            i += 1
            continue
        kind, path = header
        if kind == "table" and is_target_path(path):
            found_target_table = True
            remove[i] = True
            i += 1
            while i < len(lines) and table_header(lines[i]) is None:
                remove[i] = True
                i += 1
            continue
        i += 1
    if had_target and not found_target_table:
        raise RuntimeError(
            "existing mcp_servers.lean-ctx is encoded as an inline/dotted value that Harr's fallback writer "
            "will not rewrite. Install/use the Codex CLI and rerun, or normalize that one MCP entry to a table."
        )
    return "".join(line for idx, line in enumerate(lines) if not remove[idx])


def toml_basic_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def write_config_text(text: str) -> None:
    mode = stat.S_IMODE(CONFIG.stat().st_mode) if CONFIG.exists() else 0o600
    fd, tmp_name = tempfile.mkstemp(prefix="config.toml.", dir=CODEX_HOME)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
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


def ensure_default_tools_approval_mode() -> None:
    text = load_config_text()
    lines = text.splitlines(keepends=True)
    target_header = None

    for index, line in enumerate(lines):
        header = table_header(line)
        if header == ("table", ["mcp_servers", SERVER_NAME]):
            target_header = index
            break

    if target_header is None:
        raise RuntimeError("Codex CLI did not create the LeanCTX MCP table")

    table_end = len(lines)
    for index in range(target_header + 1, len(lines)):
        if table_header(lines[index]) is not None:
            table_end = index
            break

    replacement = f'default_tools_approval_mode = "{DEFAULT_TOOLS_APPROVAL_MODE}"\n'
    for index in range(target_header + 1, table_end):
        if _DEFAULT_TOOLS_APPROVAL_RE.match(lines[index]):
            lines[index] = replacement
            break
    else:
        lines.insert(table_end, replacement)

    new_text = "".join(lines)
    parse_config(new_text)
    write_config_text(new_text)


def apply_with_fallback() -> None:
    CODEX_HOME.mkdir(parents=True, exist_ok=True)
    old_text = load_config_text()
    old_config = parse_config(old_text)
    base = remove_existing_target_tables(old_text, current_entry(old_config) is not None).rstrip()
    block = (
        "[mcp_servers.lean-ctx]\n"
        f"command = {toml_basic_string(str(LEANCTX))}\n"
        "enabled = true\n"
        f'default_tools_approval_mode = "{DEFAULT_TOOLS_APPROVAL_MODE}"\n'
    )
    new_text = f"{base}\n\n{block}" if base else block
    data = parse_config(new_text)
    if not entry_is_managed(current_entry(data)):
        raise RuntimeError("generated Codex TOML did not contain the expected Harr LeanCTX MCP entry")
    write_config_text(new_text)
    print(f"Applied Harr Codex MCP registration using validated TOML fallback: {CONFIG}")


def apply() -> None:
    binary = codex_cli()
    apply_with_codex_cli(binary) if binary else apply_with_fallback()


def status() -> int:
    if not CONFIG.exists():
        print(f"codex-config\tmissing\t{CONFIG}")
        return 1
    try:
        config = parse_config(load_config_text())
    except Exception as exc:
        print(f"codex-config\tinvalid\t{exc}")
        return 2
    entry = current_entry(config)
    if entry is None:
        print(f"codex-config\tmissing\tLeanCTX MCP not registered in {CONFIG}")
        return 1
    if entry_is_managed(entry):
        print(f"codex-config\tmanaged\t{CONFIG}")
        return 0
    print(
        "codex-config\tstale\t"
        f"expected command={LEANCTX} enabled=true default_tools_approval_mode={DEFAULT_TOOLS_APPROVAL_MODE!r}; "
        f"got command={entry.get('command')!r} enabled={entry.get('enabled', True)!r} "
        f"default_tools_approval_mode={entry.get('default_tools_approval_mode')!r}"
    )
    return 1


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else "status"
    if command == "apply":
        apply()
        return 0
    if command == "status":
        return status()
    print("usage: codex-config.py {apply|status}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
