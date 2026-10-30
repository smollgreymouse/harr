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

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

SERVER_NAME = "lean-ctx"
DEFAULT_TOOLS_APPROVAL_MODE = "auto"
MCP_TOOL_TIMEOUT_SEC = 1900
TRUSTED_TOOLS = (
    "ctx_read",
    "ctx_search",
    "ctx_glob",
    "ctx_shell",
    "ctx_tools",
)
TRUSTED_TOOL_APPROVAL_MODE = "approve"
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
_TOOL_TIMEOUT_RE = re.compile(r"^\s*tool_timeout_sec\s*=")


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
        "tool_timeout_sec": MCP_TOOL_TIMEOUT_SEC,
        "tools": {
            name: {"approval_mode": TRUSTED_TOOL_APPROVAL_MODE}
            for name in TRUSTED_TOOLS
        },
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
    if (
        entry.get("command") != str(LEANCTX)
        or entry.get("enabled", True) is not True
        or entry.get("default_tools_approval_mode") != DEFAULT_TOOLS_APPROVAL_MODE
        or entry.get("tool_timeout_sec") != MCP_TOOL_TIMEOUT_SEC
    ):
        return False
    tools = entry.get("tools")
    if not isinstance(tools, dict):
        return False
    for name in TRUSTED_TOOLS:
        tool = tools.get(name)
        if not isinstance(tool, dict) or tool.get("approval_mode") != TRUSTED_TOOL_APPROVAL_MODE:
            return False
    return True


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
    # settings after it runs instead of relying on the writer to preserve them.
    ensure_approval_settings()
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


def remove_exact_table(text: str, target: list[str]) -> str:
    lines = text.splitlines(keepends=True)
    remove = [False] * len(lines)
    i = 0
    while i < len(lines):
        header = table_header(lines[i])
        if header == ("table", target):
            remove[i] = True
            i += 1
            while i < len(lines) and table_header(lines[i]) is None:
                remove[i] = True
                i += 1
            continue
        i += 1
    return "".join(line for idx, line in enumerate(lines) if not remove[idx])


def remove_table_subtree(text: str, target: list[str]) -> str:
    """Remove an owned server together with its env/tools child tables."""
    kept: list[str] = []
    keep = True
    for line in text.splitlines(keepends=True):
        header = table_header(line)
        if header is not None:
            keep = header[1][:len(target)] != target
        if keep:
            kept.append(line)
    return "".join(kept)


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


def ensure_approval_settings() -> None:
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

    def upsert_setting(pattern: re.Pattern[str], replacement: str) -> None:
        local_end = len(lines)
        for idx in range(target_header + 1, len(lines)):
            if table_header(lines[idx]) is not None:
                local_end = idx
                break
        for idx in range(target_header + 1, local_end):
            if pattern.match(lines[idx]):
                lines[idx] = replacement
                return
        lines.insert(local_end, replacement)

    upsert_setting(
        _DEFAULT_TOOLS_APPROVAL_RE,
        f'default_tools_approval_mode = "{DEFAULT_TOOLS_APPROVAL_MODE}"\n',
    )
    upsert_setting(_TOOL_TIMEOUT_RE, f"tool_timeout_sec = {MCP_TOOL_TIMEOUT_SEC}\n")

    new_text = "".join(lines)
    for name in TRUSTED_TOOLS:
        new_text = remove_exact_table(
            new_text,
            ["mcp_servers", SERVER_NAME, "tools", name],
        ).rstrip()

    tool_blocks = "\n\n".join(
        f"[mcp_servers.{SERVER_NAME}.tools.{name}]\n"
        f'approval_mode = "{TRUSTED_TOOL_APPROVAL_MODE}"'
        for name in TRUSTED_TOOLS
    )
    new_text = f"{new_text}\n\n{tool_blocks}\n" if new_text else f"{tool_blocks}\n"
    parse_config(new_text)
    write_config_text(new_text)


def managed_block() -> str:
    server = (
        "[mcp_servers.lean-ctx]\n"
        f"command = {toml_basic_string(str(LEANCTX))}\n"
        "enabled = true\n"
        f'default_tools_approval_mode = "{DEFAULT_TOOLS_APPROVAL_MODE}"\n'
        f"tool_timeout_sec = {MCP_TOOL_TIMEOUT_SEC}"
    )
    tools = "\n\n".join(
        f"[mcp_servers.lean-ctx.tools.{name}]\n"
        f'approval_mode = "{TRUSTED_TOOL_APPROVAL_MODE}"'
        for name in TRUSTED_TOOLS
    )
    return f"{server}\n\n{tools}\n"


def apply_with_fallback() -> None:
    CODEX_HOME.mkdir(parents=True, exist_ok=True)
    old_text = load_config_text()
    old_config = parse_config(old_text)
    base = remove_existing_target_tables(old_text, current_entry(old_config) is not None).rstrip()
    block = managed_block()
    new_text = f"{base}\n\n{block}" if base else block
    data = parse_config(new_text)
    if not entry_is_managed(current_entry(data)):
        raise RuntimeError("generated Codex TOML did not contain the expected Harr LeanCTX MCP entry")
    write_config_text(new_text)
    print(f"Applied Harr Codex MCP registration using validated TOML fallback: {CONFIG}")


WORKSPACE_SERVER_NAME = "harr-workspace"
WORKSPACE_TOOLS = ("workspace_get", "workspace_sync")
WORKSPACE_APP_SERVER_NAME = "harr-workspace-app"


def retire_gigacode_app() -> None:
    """Remove only the exact Harr-owned standalone app registration."""
    app = Path(__file__).resolve().parents[1] / "mcp" / "gigacode_app" / "server.py"
    text = load_config_text()
    servers = parse_config(text).get("mcp_servers", {})
    entry = servers.get("harr-gigacode-app") if isinstance(servers, dict) else None
    # The interpreter may change between installs (system Python, venv, etc.).
    # The Harr-owned namespace plus exact managed script path is sufficient
    # ownership evidence; keep a same-named user server with different args.
    args = entry.get("args") if isinstance(entry, dict) else None
    managed_path = os.path.normcase(os.path.realpath(app))
    configured_path = (
        os.path.normcase(os.path.realpath(args[0]))
        if isinstance(args, list) and len(args) == 1 and isinstance(args[0], str)
        else None
    )
    if configured_path == managed_path:
        text = remove_table_subtree(text, ["mcp_servers", "harr-gigacode-app"]).rstrip()
        parse_config(text)
        write_config_text(text + "\n")


def apply_named_ein_apps() -> None:
    """Reconcile one shared read-only MCP App for all enabled Ein instances."""
    from common.mcp.ein_instances import read

    app = Path(__file__).resolve().parents[1] / "mcp" / "ein_app" / "server.py"
    data = read()
    text = load_config_text()
    existing = parse_config(text).get("mcp_servers", {})
    for name in list(existing):
        if name == "harr-ein-ui" or re.fullmatch(r"harr-ein-[a-z][a-z0-9-]{0,62}-app", name):
            text = remove_table_subtree(text, ["mcp_servers", name])
    if any(item.get("enabled", True) for item in data["instances"]):
        block = (
            "[mcp_servers.harr-ein-ui]\n"
            f"command = {toml_basic_string(sys.executable)}\n"
            f"args = [{toml_basic_string(str(app))}]\n"
            'enabled = true\nstartup_timeout_sec = 60\ntool_timeout_sec = 120\n'
            'default_tools_approval_mode = "auto"\n'
            "[mcp_servers.harr-ein-ui.env]\n"
            f"HARR_CONFIG_DIR = {toml_basic_string(str(Path(os.environ.get('HARR_CONFIG_DIR') or (Path.home() / '.config/harr'))))}\n"
            "[mcp_servers.harr-ein-ui.tools.show_ein_live]\n"
            'approval_mode = "auto"\n'
        )
        text = text.rstrip() + "\n\n" + block
    parse_config(text)
    write_config_text(text.rstrip() + "\n")


def workspace_server_path() -> Path:
    return Path(__file__).resolve().parents[1] / "mcp" / "workspace_control" / "server.py"


def workspace_control_enabled() -> bool:
    platform = os.environ.get("HARR_PLATFORM")
    return platform == "linux" if platform else sys.platform.startswith("linux")


def apply_workspace_control() -> None:
    server = workspace_server_path()
    if not server.is_file():
        raise RuntimeError(f"Harr Workspace MCP missing: {server}")
    text = load_config_text()
    parse_config(text)
    for tool in WORKSPACE_TOOLS:
        text = remove_exact_table(text, ["mcp_servers", WORKSPACE_SERVER_NAME, "tools", tool])
    text = remove_exact_table(text, ["mcp_servers", WORKSPACE_SERVER_NAME]).rstrip()
    if not workspace_control_enabled():
        write_config_text(text + "\n")
        return
    block = (f"[mcp_servers.{WORKSPACE_SERVER_NAME}]\n"
             f"command = {toml_basic_string(sys.executable)}\n"
             f"args = [{toml_basic_string(str(server))}]\n"
             "enabled = true\nstartup_timeout_sec = 30\ntool_timeout_sec = 60\n"
             "default_tools_approval_mode = \"auto\"\n"
             + "\n".join(
                 f"[mcp_servers.{WORKSPACE_SERVER_NAME}.tools.{tool}]\napproval_mode = \"auto\""
                 for tool in WORKSPACE_TOOLS
             ) + "\n")
    text = f"{text}\n\n{block}" if text else block
    parse_config(text)
    write_config_text(text)


def workspace_control_is_managed(config: dict[str, Any]) -> bool:
    servers = config.get("mcp_servers")
    entry = servers.get(WORKSPACE_SERVER_NAME) if isinstance(servers, dict) else None
    if not workspace_control_enabled():
        return entry is None
    if not isinstance(entry, dict):
        return False
    if (entry.get("command") != sys.executable or entry.get("args") != [str(workspace_server_path())]
            or entry.get("enabled") is not True or entry.get("default_tools_approval_mode") != "auto"
            or entry.get("startup_timeout_sec") != 30 or entry.get("tool_timeout_sec") != 60):
        return False
    tools = entry.get("tools")
    return isinstance(tools, dict) and all(tools.get(tool) == {"approval_mode": "auto"} for tool in WORKSPACE_TOOLS)


def workspace_app_path() -> Path:
    return Path(__file__).resolve().parents[1] / "mcp" / "workspace_app" / "server.py"


def apply_workspace_app() -> None:
    app = workspace_app_path()
    text = load_config_text()
    parse_config(text)
    text = remove_exact_table(text, ["mcp_servers", WORKSPACE_APP_SERVER_NAME, "tools", "show_harr_workspace"])
    text = remove_exact_table(text, ["mcp_servers", WORKSPACE_APP_SERVER_NAME]).rstrip()
    if not workspace_control_enabled():
        write_config_text(text + "\n")
        return
    if not app.is_file():
        raise RuntimeError(f"Workspace MCP App missing: {app}")
    block = (f"[mcp_servers.{WORKSPACE_APP_SERVER_NAME}]\n"
             f"command = {toml_basic_string(sys.executable)}\n"
             f"args = [{toml_basic_string(str(app))}]\n"
             "enabled = true\nstartup_timeout_sec = 60\ntool_timeout_sec = 120\n"
             "default_tools_approval_mode = \"auto\"\n"
             f"\n[mcp_servers.{WORKSPACE_APP_SERVER_NAME}.tools.show_harr_workspace]\n"
             "approval_mode = \"auto\"\n")
    text = f"{text}\n\n{block}" if text else block
    parse_config(text)
    write_config_text(text)


def workspace_app_is_managed(config: dict[str, Any]) -> bool:
    servers = config.get("mcp_servers")
    entry = servers.get(WORKSPACE_APP_SERVER_NAME) if isinstance(servers, dict) else None
    if not workspace_control_enabled():
        return entry is None
    if not isinstance(entry, dict):
        return False
    return (
        entry.get("command") == sys.executable
        and entry.get("args") == [str(workspace_app_path())]
        and entry.get("enabled") is True
        and entry.get("default_tools_approval_mode") == "auto"
        and entry.get("startup_timeout_sec") == 60
        and entry.get("tool_timeout_sec") == 120
        and isinstance(entry.get("tools"), dict)
        and entry["tools"].get("show_harr_workspace") == {"approval_mode": "auto"}
    )


def apply() -> None:
    binary = codex_cli()
    apply_with_codex_cli(binary) if binary else apply_with_fallback()
    retire_gigacode_app()
    apply_named_ein_apps()
    apply_workspace_control()
    apply_workspace_app()

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
    if entry_is_managed(entry) and workspace_control_is_managed(config) and workspace_app_is_managed(config):
        print(f"codex-config\tmanaged\t{CONFIG}")
        return 0

    tools = entry.get("tools") if isinstance(entry, dict) else None
    actual_modes: dict[str, Any] = {}
    for name in TRUSTED_TOOLS:
        tool = tools.get(name) if isinstance(tools, dict) else None
        actual_modes[name] = tool.get("approval_mode") if isinstance(tool, dict) else None
    print(
        "codex-config\tstale\t"
        f"expected command={LEANCTX} enabled=true default_tools_approval_mode={DEFAULT_TOOLS_APPROVAL_MODE!r} "
        f"tool_timeout_sec={MCP_TOOL_TIMEOUT_SEC!r} "
        f"trusted_tools={dict.fromkeys(TRUSTED_TOOLS, TRUSTED_TOOL_APPROVAL_MODE)!r}; "
        f"got command={entry.get('command')!r} enabled={entry.get('enabled', True)!r} "
        f"default_tools_approval_mode={entry.get('default_tools_approval_mode')!r} "
        f"tool_timeout_sec={entry.get('tool_timeout_sec')!r} "
        f"trusted_tools={actual_modes!r}"
    )
    return 1


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else "status"
    if command == "apply":
        apply()
        return 0
    if command == "apply-ein-panels":
        retire_gigacode_app()
        apply_named_ein_apps()
        return 0
    if command == "status":
        return status()
    print("usage: codex-config.py {apply|apply-ein-panels|status}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
