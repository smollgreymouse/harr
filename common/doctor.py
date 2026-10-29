#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import dataclasses
import datetime as dt
import hashlib
import json
import os
import queue
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Iterable

STATUSES = {"PASS", "WARN", "FAIL", "SKIP"}
REPAIR_STATUSES = {"NOT_NEEDED", "PLANNED", "REPAIRED", "BLOCKED", "FAILED", "ROLLED_BACK"}
PROBE_KINDS = {"catalog-only", "mcp-ping", "tool"}
DOCTOR_FIELDS = {"required_tools", "probe", "repair"}
PROBE_FIELDS = {"kind", "tool", "arguments", "timeout_sec", "success"}
SUCCESS_FIELDS = {"json_content"}
REPAIR_FIELDS = {"runtime_reinstall", "credential_auto_repair"}
MAX_PROBE_TIMEOUT = 30


@dataclasses.dataclass
class Check:
    id: str
    scope: str
    status: str
    summary: str
    evidence: dict[str, Any] = dataclasses.field(default_factory=dict)
    hint: str | None = None
    repair: str | None = None

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(f"invalid check status: {self.status}")

    def as_dict(self) -> dict[str, Any]:
        value = dataclasses.asdict(self)
        return {k: v for k, v in value.items() if v not in (None, {}, [])}


@dataclasses.dataclass
class RepairAction:
    id: str
    check_ids: list[str]
    risk: str
    summary: str
    status: str = "PLANNED"
    rollback: str = ""
    evidence: dict[str, Any] = dataclasses.field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in REPAIR_STATUSES:
            raise ValueError(f"invalid repair status: {self.status}")

    def as_dict(self) -> dict[str, Any]:
        value = dataclasses.asdict(self)
        return {k: v for k, v in value.items() if v not in ("", {}, [])}


@dataclasses.dataclass
class Paths:
    platform: str
    home: Path
    config_home: Path
    harr_config: Path
    libexec: Path
    common: Path
    bin_dir: Path
    leanctx: Path
    lean_config: Path
    effective: Path
    catalog: Path
    secrets: Path
    npm_prefix: Path
    runner: Path
    manifest: Path
    repair_root: Path
    codex_home: Path
    opencode_home: Path
    harr_command: Path

    @classmethod
    def detect(cls) -> "Paths":
        plat = os.environ.get("HARR_PLATFORM")
        if not plat:
            plat = "windows" if os.name == "nt" else ("macos" if sys.platform == "darwin" else "linux")
        home = Path(os.environ.get("HARR_HOME") or Path.home()).expanduser()
        config_home = Path(os.environ.get("XDG_CONFIG_HOME") or (home / ".config")).expanduser()
        harr_config = Path(os.environ.get("HARR_CONFIG_DIR") or (config_home / "harr")).expanduser()
        codex_home = Path(os.environ.get("CODEX_HOME") or (home / ".codex")).expanduser()
        opencode_home = config_home / "opencode"

        if plat == "windows":
            local = Path(os.environ.get("HARR_LOCALAPPDATA") or os.environ.get("LOCALAPPDATA") or (home / "AppData" / "Local"))
            root = local / "Harr"
            libexec = Path(os.environ.get("HARR_LIBEXEC_DIR") or (root / "libexec"))
            bin_dir = root / "bin"
            leanctx = Path(os.environ.get("HARR_LEANCTX_COMMAND") or (bin_dir / "lean-ctx.cmd"))
            runner = Path(os.environ.get("HARR_MCP_RUNNER") or (bin_dir / "harr-mcp-run.cmd"))
            npm_prefix = root / "share" / "npm"
            repair_root = local / "HarrState" / "doctor-repairs"
            harr_default = bin_dir / "harr.cmd"
        else:
            libexec = Path(os.environ.get("HARR_LIBEXEC_DIR") or (home / ".local" / "libexec" / "harr"))
            bin_dir = home / ".local" / "bin"
            leanctx = Path(os.environ.get("HARR_LEANCTX_COMMAND") or (bin_dir / "lean-ctx"))
            runner = Path(os.environ.get("HARR_MCP_RUNNER") or (bin_dir / "harr-mcp-run"))
            npm_prefix = home / ".local" / "share" / "harr" / "npm"
            repair_root = home / ".local" / "share" / "harr" / "doctor-repairs"
            harr_default = bin_dir / "harr"

        # Diagnose the installed harness, never whichever source checkout happens to invoke doctor.
        # Tests may redirect the whole installed root with HARR_LIBEXEC_DIR.
        common = libexec / "common"
        harr_command = Path(os.environ.get("HARR_COMMAND") or shutil.which("harr") or harr_default)
        return cls(
            platform=plat,
            home=home,
            config_home=config_home,
            harr_config=harr_config,
            libexec=libexec,
            common=common,
            bin_dir=bin_dir,
            leanctx=leanctx,
            lean_config=Path(os.environ.get("HARR_LEANCTX_CONFIG") or (config_home / "lean-ctx" / "config.toml")),
            effective=Path(os.environ.get("HARR_MCP_EFFECTIVE") or (harr_config / "mcp-registry.json")),
            catalog=Path(os.environ.get("HARR_MCP_CATALOG") or (common / "mcp" / "registry.json")),
            secrets=harr_config / "secrets",
            npm_prefix=npm_prefix,
            runner=runner,
            manifest=libexec / "install-manifest.json",
            repair_root=repair_root,
            codex_home=codex_home,
            opencode_home=opencode_home,
            harr_command=harr_command,
        )


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def command_prefix(path: Path) -> list[str]:
    if os.name == "nt" and path.suffix.lower() in {".cmd", ".bat"}:
        return ["cmd.exe", "/d", "/c", str(path)]
    return [str(path)]


def safe_run(argv: list[str], *, env: dict[str, str] | None = None, timeout: float = 20, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            argv,
            env=env,
            cwd=str(cwd) if cwd else None,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(argv, 124, exc.stdout or "", (exc.stderr or "") + f"\ntimeout after {timeout}s")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be object: {path}")
    return value


def validate_doctor_metadata(server: dict[str, Any]) -> None:
    doctor = server.get("doctor")
    if doctor is None:
        return
    if not isinstance(doctor, dict):
        raise ValueError(f"{server.get('name')}: doctor must be an object")
    unknown = set(doctor) - DOCTOR_FIELDS
    if unknown:
        raise ValueError(f"{server.get('name')}: unknown doctor fields: {sorted(unknown)}")
    required = doctor.get("required_tools", [])
    if not isinstance(required, list) or not all(isinstance(x, str) and x for x in required):
        raise ValueError(f"{server.get('name')}: doctor.required_tools must contain strings")
    probe = doctor.get("probe")
    if probe is not None:
        if not isinstance(probe, dict):
            raise ValueError(f"{server.get('name')}: doctor.probe must be an object")
        unknown_probe = set(probe) - PROBE_FIELDS
        if unknown_probe:
            raise ValueError(f"{server.get('name')}: unknown doctor.probe fields: {sorted(unknown_probe)}")
        kind = probe.get("kind")
        if kind not in PROBE_KINDS:
            raise ValueError(f"{server.get('name')}: invalid doctor probe kind: {kind!r}")
        if kind == "tool" and (not isinstance(probe.get("tool"), str) or not probe["tool"]):
            raise ValueError(f"{server.get('name')}: tool probe requires a tool")
        if "arguments" in probe and not isinstance(probe["arguments"], dict):
            raise ValueError(f"{server.get('name')}: doctor.probe.arguments must be an object")
        timeout = probe.get("timeout_sec", 10)
        if not isinstance(timeout, int) or timeout < 1 or timeout > MAX_PROBE_TIMEOUT:
            raise ValueError(f"{server.get('name')}: doctor probe timeout must be 1..{MAX_PROBE_TIMEOUT}")
        success = probe.get("success", {})
        if not isinstance(success, dict) or set(success) - SUCCESS_FIELDS:
            raise ValueError(f"{server.get('name')}: invalid doctor.probe.success")
        if "json_content" in success and not isinstance(success["json_content"], dict):
            raise ValueError(f"{server.get('name')}: success.json_content must be an object")
    repair = doctor.get("repair")
    if repair is not None:
        if not isinstance(repair, dict) or set(repair) - REPAIR_FIELDS:
            raise ValueError(f"{server.get('name')}: invalid doctor.repair")
        if not all(isinstance(v, bool) for v in repair.values()):
            raise ValueError(f"{server.get('name')}: doctor.repair values must be booleans")


def redact_value(value: Any, secrets: Iterable[str]) -> Any:
    secret_values = [s for s in secrets if s]
    if isinstance(value, str):
        out = value
        for secret in secret_values:
            out = out.replace(secret, "<redacted>")
        out = re.sub(r"(?i)(token|password|secret|authorization)([=:]\s*)([^\s,;]+)", r"\1\2<redacted>", out)
        return out
    if isinstance(value, list):
        return [redact_value(x, secret_values) for x in value]
    if isinstance(value, dict):
        return {str(k): redact_value(v, secret_values) for k, v in value.items()}
    return value


class McpSession:
    def __init__(self, argv: list[str], *, env: dict[str, str] | None = None, cwd: Path | None = None):
        self.proc = subprocess.Popen(
            argv,
            env=env,
            cwd=str(cwd) if cwd else None,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        if self.proc.stdin is None or self.proc.stdout is None or self.proc.stderr is None:
            raise RuntimeError("failed to open MCP stdio")
        self._queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self._stderr: deque[str] = deque(maxlen=80)
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()

    def _read_stdout(self) -> None:
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                self._queue.put(value)

    def _read_stderr(self) -> None:
        assert self.proc.stderr is not None
        for line in self.proc.stderr:
            self._stderr.append(line.rstrip())

    def send(self, value: dict[str, Any]) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps(value, separators=(",", ":")) + "\n")
        self.proc.stdin.flush()

    def request(self, req_id: int, method: str, params: dict[str, Any], timeout: float) -> dict[str, Any]:
        self.send({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(f"MCP exited {self.proc.returncode}: {' | '.join(self._stderr)}")
            try:
                item = self._queue.get(timeout=min(0.25, max(0.01, deadline - time.monotonic())))
            except queue.Empty:
                continue
            if item.get("id") == req_id:
                return item
        raise TimeoutError(f"MCP timeout waiting for {method}; stderr={' | '.join(self._stderr)}")

    def initialize(self, timeout: float = 10) -> dict[str, Any]:
        response = self.request(
            1,
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "harr-doctor", "version": "1"},
            },
            timeout,
        )
        if "error" in response:
            raise RuntimeError(f"initialize error: {response['error']}")
        self.send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        return response

    def close(self) -> None:
        if self.proc.poll() is None:
            with contextlib.suppress(Exception):
                self.proc.terminate()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                with contextlib.suppress(Exception):
                    self.proc.kill()

    @property
    def stderr_tail(self) -> list[str]:
        return list(self._stderr)


def parse_outer_tool_text(response: dict[str, Any]) -> tuple[str, bool]:
    if "error" in response:
        return json.dumps(response["error"], ensure_ascii=False), True
    result = response.get("result")
    if not isinstance(result, dict):
        return "missing result", True
    content = result.get("content")
    texts = [item.get("text", "") for item in content or [] if isinstance(item, dict) and isinstance(item.get("text"), str)]
    return "\n".join(texts), bool(result.get("isError"))


def collect_secret_values(paths: Paths, effective: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for server in effective.get("servers", []):
        for secret in server.get("secrets", []):
            filename = secret.get("file")
            if not isinstance(filename, str):
                continue
            try:
                value = (paths.secrets / filename).read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if value:
                values.append(value)
    return values


def locate_runtime_command(command: str, paths: Paths) -> str | None:
    found = shutil.which(command)
    if found:
        return found
    candidates: list[Path] = []
    if paths.platform != "windows":
        candidates += [paths.home / ".local" / "bin" / command, paths.home / ".cargo" / "bin" / command]
    else:
        candidates += [paths.bin_dir / command, paths.bin_dir / f"{command}.exe", paths.bin_dir / f"{command}.cmd"]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def overlay_doctor_metadata(effective_servers: list[dict[str, Any]], catalog: dict[str, Any]) -> list[dict[str, Any]]:
    """Overlay non-runtime doctor policy from the installed catalog.

    Older effective registries predate doctor metadata. Doctor must still be
    useful immediately after a package upgrade, before the user re-runs setup.
    Only the doctor field is overlaid; transport/runtime/secret configuration
    remains authoritative from the effective registry.
    """
    catalog_by_name = {
        str(server["name"]): server
        for server in catalog.get("servers", [])
        if isinstance(server, dict) and isinstance(server.get("name"), str)
    }
    out: list[dict[str, Any]] = []
    for server in effective_servers:
        merged = dict(server)
        source = catalog_by_name.get(str(server.get("name")))
        if isinstance(source, dict) and isinstance(source.get("doctor"), dict):
            merged["doctor"] = source["doctor"]
        out.append(merged)
    return out


def runtime_check(server: dict[str, Any], paths: Paths) -> Check:
    name = str(server["name"])
    runtime = server.get("runtime", {})
    kind = runtime.get("kind")
    if server.get("ein_instance"):
        script = paths.common / "mcp" / "ein_instances.py"
        env = os.environ.copy()
        if paths.platform != "windows":
            env["PATH"] = f"{paths.home / '.local/bin'}:{paths.home / '.cargo/bin'}:{env.get('PATH','')}"
        result = safe_run([sys.executable, str(script), "test", name], env=env, timeout=15)
        if result.returncode == 0:
            return Check(f"runtime.{name}", name, "PASS", "named Ein instance runtime is available", {"detail": result.stdout.strip()})
        return Check(f"runtime.{name}", name, "FAIL", "named Ein instance runtime is unavailable", {"detail": (result.stderr or result.stdout).strip()}, "Fix the configured executor CLI/profile; doctor does not install or authenticate model providers.")

    if kind == "npm":
        package = runtime.get("package")
        expected = runtime.get("version")
        if not isinstance(package, str) or not isinstance(expected, str):
            return Check(f"runtime.{name}", name, "FAIL", "invalid npm runtime metadata")
        package_json = paths.npm_prefix / "node_modules" / Path(*package.split("/")) / "package.json"
        if not package_json.is_file():
            return Check(f"runtime.{name}", name, "FAIL", f"npm runtime is missing: {package}@{expected}", {"package_json": str(package_json)}, "Run harr doctor --repair or harr install mcp.", "install_mcp")
        try:
            actual = load_json(package_json).get("version")
        except Exception as exc:
            return Check(f"runtime.{name}", name, "FAIL", "npm runtime package metadata is invalid", {"error": str(exc)}, repair="install_mcp")
        if actual != expected:
            return Check(f"runtime.{name}", name, "FAIL", f"npm runtime version mismatch: expected {expected}, got {actual}", repair="install_mcp")
        return Check(f"runtime.{name}", name, "PASS", f"npm runtime {package}@{actual} is installed")

    if kind == "uvx":
        uvx = locate_runtime_command(str(runtime.get("command") or "uvx"), paths)
        if not uvx:
            return Check(f"runtime.{name}", name, "FAIL", "uvx runtime command is not available", hint="Install uv/uvx in the user environment; doctor does not install third-party package managers.")
        args = runtime.get("probe_args")
        if not isinstance(args, list) or not all(isinstance(x, str) for x in args):
            return Check(f"runtime.{name}", name, "FAIL", "invalid uvx probe metadata")
        result = safe_run([uvx, *args], timeout=20)
        if result.returncode != 0:
            return Check(f"runtime.{name}", name, "FAIL", "uvx runtime cache/probe failed", {"uvx": uvx, "detail": (result.stderr or result.stdout).strip()}, "Run harr doctor --repair or harr install mcp.", "install_mcp")
        first = next((line.strip() for line in result.stdout.splitlines() if line.strip()), "ready")
        return Check(f"runtime.{name}", name, "PASS", "uvx runtime is ready", {"uvx": uvx, "probe": first})

    if kind == "bundled-python":
        script_name = runtime.get("script")
        if not isinstance(script_name, str):
            return Check(f"runtime.{name}", name, "FAIL", "invalid bundled Python runtime metadata")
        script = paths.common / "mcp" / script_name
        if not script.is_file():
            return Check(f"runtime.{name}", name, "FAIL", "bundled Python MCP script is missing", {"path": str(script)})
        return Check(f"runtime.{name}", name, "PASS", "bundled Python MCP runtime is present")

    command = runtime.get("command")
    if isinstance(command, str):
        resolved = locate_runtime_command(command, paths)
        if resolved:
            return Check(f"runtime.{name}", name, "PASS", "runtime command is available", {"command": resolved})
        return Check(f"runtime.{name}", name, "FAIL", f"runtime command is missing: {command}")
    return Check(f"runtime.{name}", name, "WARN", f"runtime kind {kind!r} has no doctor implementation")


def source_wrapper(paths: Paths) -> Path | None:
    path = paths.libexec / "windows" / "files" / "leanctx" / "lean-ctx-wrapper.ps1" if paths.platform == "windows" else paths.libexec / "leanctx" / "lean-ctx-wrapper"
    return path if path.is_file() else None


def launcher_marker_ok(paths: Paths) -> bool:
    try:
        text = paths.leanctx.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return ("lean-ctx-wrapper.ps1" in text and "powershell" in text.lower()) if paths.platform == "windows" else "HARR_LEANCTX_WRAPPER=1" in text


def config_managed(path: Path) -> bool:
    try:
        return "# Managed by Harr." in path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False


def load_manifest(paths: Paths) -> tuple[dict[str, Any] | None, Check]:
    if not paths.manifest.is_file():
        return None, Check("installation.manifest", "core", "WARN", "install provenance manifest is missing (legacy installation)", {"path": str(paths.manifest)}, "A doctor-enabled Harr setup will write the provenance manifest.")
    try:
        data = load_json(paths.manifest)
    except Exception as exc:
        return None, Check("installation.manifest", "core", "FAIL", "install provenance manifest is invalid", {"error": str(exc)})
    if data.get("schema") != 1:
        return None, Check("installation.manifest", "core", "FAIL", "unsupported install provenance manifest schema")
    return data, Check("installation.manifest", "core", "PASS", "install provenance manifest is valid", {"path": str(paths.manifest)})


def manifest_expected_real(paths: Paths, manifest: dict[str, Any] | None) -> Path | None:
    if manifest:
        lean = manifest.get("leanctx")
        if isinstance(lean, dict) and isinstance(lean.get("real_path"), str):
            return Path(lean["real_path"])
    build = os.environ.get("HARR_LEANCTX_BUILD")
    if build:
        exe = "lean-ctx.exe" if paths.platform == "windows" else "lean-ctx"
        return paths.libexec / "vendor" / "lean-ctx" / build / exe
    return None


def host_check(paths: Paths, host: str) -> Check:
    result = safe_run([*command_prefix(paths.harr_command), "hosts", "status"], env=repair_env(paths), timeout=15)
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    detail = next((line for line in lines if line.split()[0] == host), "")
    if result.returncode == 0 and detail and "managed" in detail:
        return Check(f"host.{host}", host, "PASS", f"{host} routes LeanCTX through Harr", {"detail": detail})
    combined = detail or (result.stderr or result.stdout).strip()
    return Check(f"host.{host}", host, "FAIL", f"{host} global Harr routing is stale or invalid", {"detail": combined}, "Run harr doctor --repair to re-apply Harr-owned host routing.", "apply_hosts")


def secret_checks(server: dict[str, Any], paths: Paths) -> list[Check]:
    out: list[Check] = []
    name = str(server["name"])
    for secret in server.get("secrets", []):
        secret_name = str(secret.get("name") or secret.get("file") or "unknown")
        filename = secret.get("file")
        if not isinstance(filename, str):
            out.append(Check(f"secret.{name}.{secret_name}", name, "FAIL", "invalid secret metadata"))
            continue
        path = paths.secrets / filename
        if not path.is_file():
            out.append(Check(f"secret.{name}.{secret_name}", name, "FAIL", f"required Harr secret is missing: {secret_name}", {"file": filename}, f"Run harr secret set {secret_name}. Doctor never creates or copies credentials."))
            continue
        evidence: dict[str, Any] = {"file": filename}
        status = "PASS"
        summary = f"secret {secret_name} is present"
        if os.name != "nt":
            mode = stat.S_IMODE(path.stat().st_mode)
            evidence["mode"] = oct(mode)
            if mode & 0o077:
                status = "WARN"
                summary = f"secret {secret_name} has broader permissions than 0600"
        out.append(Check(f"secret.{name}.{secret_name}", name, status, summary, evidence))
    return out


def direct_catalog(server: dict[str, Any], paths: Paths, timeout: float = 15) -> Check:
    name = str(server["name"])
    session: McpSession | None = None
    try:
        session = McpSession([*command_prefix(paths.runner), name], env=repair_env(paths))
        session.initialize(timeout=min(timeout, 10))
        response = session.request(2, "tools/list", {}, timeout)
        if "error" in response:
            raise RuntimeError(str(response["error"]))
        tools = response.get("result", {}).get("tools")
        if not isinstance(tools, list):
            raise RuntimeError("tools/list returned no tools array")
        names: list[str] = []
        schemas_ok = True
        for tool in tools:
            if not isinstance(tool, dict) or not isinstance(tool.get("name"), str) or not tool["name"]:
                schemas_ok = False
                continue
            names.append(tool["name"])
            if not isinstance(tool.get("inputSchema", {}), dict):
                schemas_ok = False
        if len(names) != len(set(names)):
            return Check(f"catalog.{name}", name, "FAIL", "downstream MCP exposes duplicate tool names", {"tools": names})
        doctor = server.get("doctor") if isinstance(server.get("doctor"), dict) else {}
        required = doctor.get("required_tools", []) if isinstance(doctor, dict) else []
        if server.get("ein_instance") and not required:
            required = ["ein"]
        missing = [x for x in required if x not in names]
        if missing:
            return Check(f"catalog.{name}", name, "FAIL", "downstream MCP is missing required tools", {"missing": missing, "tool_count": len(names)})
        if not schemas_ok:
            return Check(f"catalog.{name}", name, "FAIL", "downstream MCP has malformed tool schema", {"tool_count": len(names)})
        shown = names if len(names) <= 20 else names[:20] + ["..."]
        return Check(f"catalog.{name}", name, "PASS", f"downstream MCP catalog is valid ({len(names)} tools)", {"tools": shown})
    except TimeoutError as exc:
        return Check(f"catalog.{name}", name, "FAIL", "downstream MCP handshake/catalog timed out", {"error": str(exc)})
    except Exception as exc:
        return Check(f"catalog.{name}", name, "FAIL", "downstream MCP handshake/catalog failed", {"error": str(exc)})
    finally:
        if session:
            session.close()


def render_isolated_config(server: dict[str, Any], paths: Paths, root: Path) -> tuple[Path, Path]:
    registry = root / "registry.json"
    config_dir = root / "lean-ctx"
    config_dir.mkdir(parents=True, exist_ok=True)
    registry.write_text(json.dumps({"schema": 1, "servers": [server]}, indent=2) + "\n", encoding="utf-8")
    manager = paths.common / "mcp" / "manager.py"
    output = config_dir / "config.toml"
    result = safe_run(
        [
            sys.executable,
            str(manager),
            "--registry",
            str(registry),
            "render-leanctx",
            "--base",
            str(paths.common / "leanctx" / "config.base.toml"),
            "--output",
            str(output),
            "--platform",
            paths.platform,
            "--runner-command",
            str(paths.runner),
        ],
        timeout=10,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip())
    return registry, config_dir


def gateway_server_checks(server: dict[str, Any], paths: Paths, local_only: bool) -> list[Check]:
    name = str(server["name"])
    if local_only:
        return [Check(f"gateway.{name}", name, "SKIP", "gateway and external probe skipped by --local")]
    with tempfile.TemporaryDirectory(prefix="harr-doctor-") as temp:
        try:
            registry, config_dir = render_isolated_config(server, paths, Path(temp))
        except Exception as exc:
            return [Check(f"gateway.{name}", name, "FAIL", "could not render isolated LeanCTX diagnostic config", {"error": str(exc)})]
        env = os.environ.copy()
        env["HARR_MCP_EFFECTIVE"] = str(registry)
        env["LEAN_CTX_CONFIG_DIR"] = str(config_dir)
        env["HARR_CONFIG_DIR"] = str(paths.harr_config)
        if paths.platform != "windows":
            env["PATH"] = f"{paths.home / '.local/bin'}:{paths.home / '.cargo/bin'}:{env.get('PATH','')}"
        session: McpSession | None = None
        out: list[Check] = []
        try:
            session = McpSession(command_prefix(paths.leanctx), env=env)
            init = session.initialize(timeout=10)
            info = init.get("result", {}).get("serverInfo", {})
            safe_info = {
                "name": info.get("name") if isinstance(info, dict) else None,
                "version": info.get("version") if isinstance(info, dict) else None,
                "icons_count": len(info.get("icons", [])) if isinstance(info, dict) and isinstance(info.get("icons"), list) else 0,
            }
            out.append(Check(f"gateway.{name}.leanctx", name, "PASS", "fresh Harr LeanCTX initialized", {"serverInfo": safe_info}))
            response = session.request(2, "tools/call", {"name": "ctx_tools", "arguments": {"action": "refresh"}}, 20)
            text, is_error = parse_outer_tool_text(response)
            if is_error:
                out.append(Check(f"gateway.{name}", name, "FAIL", "LeanCTX gateway refresh failed", {"detail": text}))
                return out
            out.append(Check(f"gateway.{name}", name, "PASS", "fresh LeanCTX gateway registered the isolated server", {"detail": text[:2000]}))

            doctor = server.get("doctor") if isinstance(server.get("doctor"), dict) else {}
            probe = doctor.get("probe") if isinstance(doctor, dict) else None
            if server.get("ein_instance"):
                probe = {"kind": "catalog-only"}
            if not probe or probe.get("kind") in {"catalog-only", "mcp-ping"}:
                out.append(Check(f"probe.{name}", name, "PASS", "catalog/handshake probe passed; no external tool call requested"))
                return out
            tool = str(probe["tool"])
            args = probe.get("arguments", {})
            timeout = int(probe.get("timeout_sec", 10))
            response = session.request(3, "tools/call", {"name": "ctx_tools", "arguments": {"action": "call", "tool": f"{name}::{tool}", "arguments": args}}, timeout + 5)
            body, is_error = parse_outer_tool_text(response)
            if is_error:
                out.append(Check(f"probe.{name}", name, "FAIL", f"safe probe {name}::{tool} failed", {"detail": body}))
                return out
            expected = probe.get("success", {}).get("json_content")
            if isinstance(expected, dict):
                try:
                    parsed = json.loads(body)
                except json.JSONDecodeError:
                    out.append(Check(f"probe.{name}", name, "FAIL", f"safe probe {name}::{tool} did not return JSON", {"detail": body}))
                    return out
                mismatch = {k: {"expected": v, "actual": parsed.get(k)} for k, v in expected.items() if parsed.get(k) != v}
                if mismatch:
                    out.append(Check(f"probe.{name}", name, "FAIL", f"safe probe {name}::{tool} returned unexpected state", {"mismatch": mismatch}))
                    return out
            out.append(Check(f"probe.{name}", name, "PASS", f"safe probe {name}::{tool} passed"))
            return out
        except TimeoutError as exc:
            out.append(Check(f"gateway.{name}", name, "FAIL", "fresh LeanCTX gateway timed out", {"error": str(exc)}))
            return out
        except Exception as exc:
            out.append(Check(f"gateway.{name}", name, "FAIL", "fresh LeanCTX gateway failed", {"error": str(exc), "stderr": session.stderr_tail if session else []}))
            return out
        finally:
            if session:
                session.close()


def _linux_process_info(pid: int) -> tuple[int, str, str] | None:
    proc_dir = Path("/proc") / str(pid)
    try:
        cmdline = (proc_dir / "cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace").strip()
        exe = os.readlink(proc_dir / "exe")
        status_text = (proc_dir / "status").read_text(encoding="utf-8", errors="replace")
        match = re.search(r"^PPid:\s+(\d+)", status_text, re.M)
        return (int(match.group(1)) if match else 0, cmdline, exe)
    except (OSError, PermissionError):
        return None


def _supported_host_ancestor(pid: int, max_depth: int = 6) -> tuple[bool, list[str]]:
    chain: list[str] = []
    current = pid
    for _ in range(max_depth):
        info = _linux_process_info(current)
        if not info:
            break
        ppid, cmdline, _ = info
        if ppid <= 1:
            break
        parent = _linux_process_info(ppid)
        if not parent:
            break
        _, parent_cmd, _ = parent
        chain.append(parent_cmd[:240])
        lowered = parent_cmd.lower()
        if "codex" in lowered or "opencode" in lowered:
            return True, chain
        current = ppid
    return False, chain


def _linux_harr_ownership(pid: int, paths: Paths) -> tuple[bool, list[str]]:
    """Prove that a live LeanCTX process was launched through Harr.

    Only marker names are returned for evidence; environment values (which may
    contain secret mementos) are never exposed.
    """
    try:
        raw = (Path("/proc") / str(pid) / "environ").read_bytes()
    except (OSError, PermissionError):
        return False, []
    env: dict[str, str] = {}
    for item in raw.split(b"\0"):
        if not item or b"=" not in item:
            continue
        key, value = item.split(b"=", 1)
        env[key.decode("utf-8", "replace")] = value.decode("utf-8", "replace")

    markers: list[str] = []
    icon = env.get("HARR_MCP_ICON_PATH")
    if icon:
        try:
            if Path(icon).resolve(strict=False).is_relative_to((paths.libexec / "common" / "mcp" / "assets").resolve(strict=False)):
                markers.append("HARR_MCP_ICON_PATH")
        except (OSError, ValueError):
            pass

    workspace = env.get("LEAN_CTX_WORKSPACE_FILE")
    if env.get("LEAN_CTX_STRICT_WORKSPACE") == "1" and workspace:
        try:
            if Path(workspace).resolve(strict=False).is_relative_to((paths.harr_config / "workspaces").resolve(strict=False)):
                markers.extend(["LEAN_CTX_STRICT_WORKSPACE", "LEAN_CTX_WORKSPACE_FILE"])
        except (OSError, ValueError):
            pass

    return bool(markers), sorted(set(markers))


def linux_live_process_checks(paths: Paths, expected_real: Path | None) -> tuple[list[Check], list[int]]:
    if paths.platform != "linux" or not Path("/proc").is_dir():
        return [Check("live.processes", "core", "SKIP", "live LeanCTX process audit is not implemented on this platform")], []
    rows: list[dict[str, Any]] = []
    repairable: list[int] = []
    expected = str(expected_real.resolve()) if expected_real and expected_real.exists() else None
    for proc_dir in Path("/proc").iterdir():
        if not proc_dir.name.isdigit():
            continue
        pid = int(proc_dir.name)
        info = _linux_process_info(pid)
        if not info:
            continue
        ppid, cmdline, exe = info
        if "lean-ctx" not in cmdline:
            continue
        deleted = exe.endswith(" (deleted)")
        normalized = exe.removesuffix(" (deleted)")
        wrong = bool(expected and os.path.realpath(normalized) != os.path.realpath(expected))
        supported_host, ancestors = _supported_host_ancestor(pid)
        harr_owned, harr_markers = _linux_harr_ownership(pid, paths)
        row = {
            "pid": pid,
            "ppid": ppid,
            "exe": exe,
            "cmdline": cmdline[:240],
            "deleted": deleted,
            "wrong_generation": wrong,
            "supported_host_ancestor": supported_host,
            "harr_owned": harr_owned,
            "harr_markers": harr_markers,
            "ancestors": ancestors,
        }
        rows.append(row)
        if (deleted or wrong) and supported_host and harr_owned:
            repairable.append(pid)
    if not rows:
        return [Check("live.processes", "core", "PASS", "no live LeanCTX processes found")], []
    stale_count = sum(1 for row in rows if row["deleted"] or row["wrong_generation"])
    if stale_count:
        repair = "refresh_stale" if repairable else None
        hint = "Explicit repair may target only stale LeanCTX children proven both Harr-owned and attached to Codex/OpenCode." if repairable else "Stale LeanCTX process ownership is ambiguous; doctor will not terminate it."
        return [Check("live.processes", "core", "WARN", f"{stale_count} stale/wrong-generation LeanCTX process(es) detected; {len(repairable)} proven Harr-owned under supported hosts", {"processes": rows}, hint, repair)], repairable
    return [Check("live.processes", "core", "PASS", f"{len(rows)} live LeanCTX process(es) use the expected generation", {"processes": rows})], []


def diagnose(paths: Paths, *, focus: str | None, local_only: bool) -> tuple[list[Check], dict[str, Any], dict[str, Any] | None, list[int]]:
    checks: list[Check] = []
    try:
        effective = load_json(paths.effective)
        if effective.get("schema") != 1 or not isinstance(effective.get("servers"), list):
            raise ValueError("effective registry schema is invalid")
    except Exception as exc:
        return [Check("registry.effective", "core", "FAIL", "effective Harr MCP registry is missing or invalid", {"error": str(exc)})], {"schema": 1, "servers": []}, None, []

    try:
        catalog = load_json(paths.catalog)
        for server in catalog.get("servers", []):
            validate_doctor_metadata(server)
    except Exception as exc:
        checks.append(Check("registry.catalog", "core", "FAIL", "Harr MCP catalog/doctor metadata is invalid", {"error": str(exc)}))
        catalog = {"schema": 1, "servers": []}
    else:
        checks.append(Check("registry.catalog", "core", "PASS", "Harr MCP catalog and doctor metadata are valid"))

    manifest, manifest_check = load_manifest(paths)
    checks.append(manifest_check)

    launcher_hash = None
    expected_launcher_hash = None
    if manifest:
        managed = manifest.get("managed_files")
        launcher_record = managed.get("leanctx_launcher") if isinstance(managed, dict) else None
        if isinstance(launcher_record, dict) and isinstance(launcher_record.get("sha256"), str):
            expected_launcher_hash = launcher_record["sha256"]
    if paths.leanctx.is_file() and launcher_marker_ok(paths):
        launcher_hash = sha256_file(paths.leanctx)
        if expected_launcher_hash and launcher_hash != expected_launcher_hash:
            checks.append(
                Check(
                    "leanctx.launcher",
                    "core",
                    "FAIL",
                    "Harr LeanCTX launcher content differs from installed provenance",
                    {"path": str(paths.leanctx)},
                    "Use harr doctor --repair only with explicit repair intent.",
                    "restore_launcher",
                )
            )
        else:
            checks.append(Check("leanctx.launcher", "core", "PASS", "Harr LeanCTX launcher is managed", {"path": str(paths.leanctx)}))
    elif paths.leanctx.exists():
        checks.append(Check("leanctx.launcher", "core", "FAIL", "LeanCTX launcher exists but is not the Harr-managed wrapper", {"path": str(paths.leanctx)}, "Use harr doctor --repair only with explicit repair intent.", "restore_launcher"))
    else:
        checks.append(Check("leanctx.launcher", "core", "FAIL", "Harr LeanCTX launcher is missing", {"path": str(paths.leanctx)}, repair="restore_launcher"))

    expected_real = manifest_expected_real(paths, manifest)
    if expected_real and expected_real.is_file():
        result = safe_run([str(expected_real), "--version"], timeout=8)
        identity = result.stdout.strip()
        expected_id = (manifest or {}).get("leanctx", {}).get("identity") if manifest else os.environ.get("HARR_LEANCTX_ID")
        ok = result.returncode == 0 and (not expected_id or str(expected_id) in identity)
        checks.append(Check("leanctx.binary", "core", "PASS" if ok else "FAIL", "pinned LeanCTX binary identity is valid" if ok else "pinned LeanCTX identity mismatch", {"identity": identity, "path": str(expected_real)}))
    else:
        checks.append(Check("leanctx.binary", "core", "FAIL", "pinned LeanCTX binary is missing or provenance is unknown", {"path": str(expected_real) if expected_real else None}, "Run harr install leanctx to restore the pinned Harr-managed runtime." if manifest else None))

    if config_managed(paths.lean_config):
        validate = safe_run([*command_prefix(paths.leanctx), "config", "validate"], timeout=12)
        if validate.returncode == 0:
            checks.append(Check("leanctx.config", "core", "PASS", "Harr LeanCTX config is managed and validates", {"path": str(paths.lean_config)}))
        else:
            checks.append(Check("leanctx.config", "core", "FAIL", "Harr LeanCTX config validation failed", {"detail": (validate.stderr or validate.stdout).strip()}, repair="apply_leanctx"))
    else:
        checks.append(Check("leanctx.config", "core", "FAIL", "LeanCTX config is missing or not Harr-managed", {"path": str(paths.lean_config)}, repair="apply_leanctx"))

    checks.extend([host_check(paths, "codex"), host_check(paths, "opencode")])

    catalog_by_name = {s.get("name"): s for s in catalog.get("servers", []) if isinstance(s, dict) and isinstance(s.get("name"), str)}
    selected = overlay_doctor_metadata(
        [s for s in effective["servers"] if isinstance(s, dict) and isinstance(s.get("name"), str)],
        catalog,
    )
    selected_names = {s["name"] for s in selected}
    catalog_names = set(catalog_by_name)
    if focus:
        if focus not in selected_names:
            if focus in catalog_names:
                checks.append(Check(f"selection.{focus}", focus, "SKIP", f"{focus} is available but disabled in the current Harr selection"))
                selected = []
            else:
                checks.append(Check(f"selection.{focus}", focus, "FAIL", f"unknown Harr MCP/Ein instance: {focus}"))
                selected = []
        else:
            selected = [s for s in selected if s["name"] == focus]

    for server in selected:
        name = str(server["name"])
        checks.append(Check(f"selection.{name}", name, "PASS", f"{name} is enabled in the effective Harr registry"))
        checks.extend(secret_checks(server, paths))
        checks.append(runtime_check(server, paths))

    process_checks, stale_pids = linux_live_process_checks(paths, expected_real)
    checks.extend(process_checks)

    for server in selected:
        name = str(server["name"])
        if local_only:
            checks.append(Check(f"catalog.{name}", name, "SKIP", "downstream MCP handshake skipped by --local"))
            checks.extend(gateway_server_checks(server, paths, True))
            continue
        blocked = next((c for c in checks if c.id == f"runtime.{name}" and c.status == "FAIL"), None)
        secret_blocked = any(c.scope == name and c.id.startswith("secret.") and c.status == "FAIL" for c in checks)
        if blocked or secret_blocked:
            checks.append(Check(f"catalog.{name}", name, "SKIP", "downstream catalog skipped because local prerequisites failed"))
            checks.append(Check(f"gateway.{name}", name, "SKIP", "gateway probe skipped because local prerequisites failed"))
            continue
        checks.append(direct_catalog(server, paths))
        checks.extend(gateway_server_checks(server, paths, False))
    return checks, effective, manifest, stale_pids


def plan_repairs(checks: list[Check], *, manifest: dict[str, Any] | None, stale_pids: list[int], effective: dict[str, Any]) -> list[RepairAction]:
    repairable = [c for c in checks if c.status in {"FAIL", "WARN"} and c.repair]
    actions: list[RepairAction] = []

    launcher = [c.id for c in repairable if c.repair == "restore_launcher"]
    if launcher:
        actions.append(RepairAction("restore_launcher", launcher, "R1", "Restore Harr-managed LeanCTX launcher from installed provenance", status="PLANNED" if manifest else "BLOCKED", rollback="restore exact pre-repair launcher snapshot"))

    lean = [c.id for c in repairable if c.repair == "apply_leanctx"]
    if lean:
        actions.append(RepairAction("apply_leanctx", lean, "R1", "Regenerate Harr-owned LeanCTX config from the effective registry", rollback="restore exact pre-repair LeanCTX config"))

    hosts = [c.id for c in repairable if c.repair == "apply_hosts"]
    if hosts:
        actions.append(RepairAction("apply_hosts", hosts, "R1", "Re-apply Harr-owned Codex/OpenCode host routing", rollback="restore exact pre-repair host configs"))

    runtimes = [c.id for c in repairable if c.repair == "install_mcp"]
    if runtimes:
        # A broad `harr install mcp` would reinstall/prefetch every selected
        # runtime, not just the failed component. Until Harr has a targeted
        # per-server primitive, fail closed instead of widening repair scope.
        actions.append(
            RepairAction(
                "install_mcp",
                runtimes,
                "R2",
                "Targeted Harr-managed MCP runtime repair is not implemented yet",
                status="BLOCKED",
                rollback="no mutation performed",
                evidence={"reason": "broad runtime reinstall is intentionally not used by doctor"},
            )
        )

    stale = [c.id for c in repairable if c.repair == "refresh_stale"]
    if stale:
        # R3 is intentionally fail-closed until both supported-host ownership
        # and a successful respawn into the expected generation can be proven.
        # Killing a process merely because its executable looks stale is unsafe.
        actions.append(
            RepairAction(
                "refresh_stale",
                stale,
                "R3",
                f"Stale LeanCTX child refresh requires ownership and respawn proof ({len(stale_pids)} candidate process(es))",
                status="BLOCKED" if stale_pids else "NOT_NEEDED",
                rollback="no mutation performed",
                evidence={
                    "pids": stale_pids,
                    "reason": "automatic child refresh is disabled until supported-host ownership and respawn verification are implemented",
                },
            )
        )
    return actions


def snapshot_paths(paths: Paths, actions: list[RepairAction]) -> tuple[Path, dict[str, Any]]:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = paths.repair_root / f"{stamp}-{os.getpid()}"
    root.mkdir(parents=True, exist_ok=False)
    with contextlib.suppress(OSError):
        root.chmod(0o700)
    ids = {a.id for a in actions if a.status == "PLANNED"}
    candidates: list[Path] = []
    if "restore_launcher" in ids:
        candidates.append(paths.leanctx)
    if "apply_leanctx" in ids:
        candidates.append(paths.lean_config)
    if "apply_hosts" in ids:
        candidates += [paths.codex_home / "config.toml", paths.opencode_home / "opencode.jsonc", paths.opencode_home / "opencode.json"]
    journal: dict[str, Any] = {"schema": 1, "created_at": dt.datetime.now(dt.timezone.utc).isoformat(), "files": []}
    for index, source in enumerate(candidates):
        entry: dict[str, Any] = {"path": str(source), "existed": source.exists()}
        if source.exists() and source.is_file():
            target = root / f"file-{index}"
            shutil.copy2(source, target)
            entry["snapshot"] = target.name
        journal["files"].append(entry)
    journal_path = root / "journal.json"
    journal_path.write_text(json.dumps(journal, indent=2) + "\n", encoding="utf-8")
    with contextlib.suppress(OSError):
        journal_path.chmod(0o600)
    return root, journal


def restore_snapshot(root: Path, journal: dict[str, Any]) -> None:
    for entry in journal.get("files", []):
        path = Path(entry["path"])
        if entry.get("existed"):
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / entry["snapshot"], path)
        elif path.exists() and (path.is_file() or path.is_symlink()):
            path.unlink()


def repair_env(paths: Paths) -> dict[str, str]:
    env = os.environ.copy()
    if paths.platform != "windows":
        env["PATH"] = f"{paths.home / '.local/bin'}:{paths.home / '.cargo/bin'}:{env.get('PATH','')}"
    return env


def execute_repairs(paths: Paths, actions: list[RepairAction], manifest: dict[str, Any] | None) -> tuple[list[RepairAction], Path | None, dict[str, Any] | None]:
    planned = [a for a in actions if a.status == "PLANNED"]
    if not planned:
        return actions, None, None
    snapshot, journal = snapshot_paths(paths, planned)
    env = repair_env(paths)
    wrapper_source = source_wrapper(paths)
    for action in actions:
        if action.status != "PLANNED":
            continue
        try:
            if action.id == "restore_launcher":
                if not manifest or not wrapper_source:
                    action.status = "BLOCKED"
                    continue
                expected_hash = manifest.get("managed_files", {}).get("leanctx_wrapper_source", {}).get("sha256")
                if expected_hash and sha256_file(wrapper_source) != expected_hash:
                    action.status = "BLOCKED"
                    action.evidence["reason"] = "installed wrapper source differs from provenance manifest"
                    continue
                if paths.platform == "windows":
                    result = safe_run([*command_prefix(paths.harr_command), "install", "leanctx"], env=env, timeout=180)
                    if result.returncode != 0:
                        raise RuntimeError((result.stderr or result.stdout).strip())
                else:
                    paths.leanctx.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(wrapper_source, paths.leanctx)
                    paths.leanctx.chmod(0o755)
                action.status = "REPAIRED"
            elif action.id == "apply_leanctx":
                result = safe_run([*command_prefix(paths.harr_command), "leanctx", "apply"], env=env, timeout=90)
                if result.returncode != 0:
                    raise RuntimeError((result.stderr or result.stdout).strip())
                action.status = "REPAIRED"
            elif action.id == "apply_hosts":
                result = safe_run([*command_prefix(paths.harr_command), "hosts", "apply"], env=env, timeout=90)
                if result.returncode != 0:
                    raise RuntimeError((result.stderr or result.stdout).strip())
                action.status = "REPAIRED"
            elif action.id == "install_mcp":
                result = safe_run([*command_prefix(paths.harr_command), "install", "mcp"], env=env, timeout=300)
                if result.returncode != 0:
                    raise RuntimeError((result.stderr or result.stdout).strip())
                action.status = "REPAIRED"
            elif action.id == "refresh_stale":
                expected_real = manifest_expected_real(paths, manifest)
                _, still_repairable = linux_live_process_checks(paths, expected_real)
                allowed = set(still_repairable)
                requested = [int(x) for x in action.evidence.get("pids", [])]
                if any(pid not in allowed for pid in requested):
                    action.status = "BLOCKED"
                    action.evidence["reason"] = "process ownership/generation changed after diagnosis"
                    continue
                for pid in requested:
                    if pid <= 1 or pid == os.getpid():
                        raise RuntimeError(f"refusing unsafe PID {pid}")
                    os.kill(pid, signal.SIGTERM)
                action.status = "REPAIRED"
            else:
                action.status = "BLOCKED"
        except Exception as exc:
            action.status = "FAILED"
            action.evidence["error"] = str(exc)
            break
    return actions, snapshot, journal


def write_manifest(paths: Paths, args: argparse.Namespace) -> int:
    paths.libexec.mkdir(parents=True, exist_ok=True)
    real = manifest_expected_real(paths, None)
    identity_text = ""
    if real and real.is_file():
        identity = safe_run([str(real), "--version"], timeout=8)
        if identity.returncode != 0:
            print("cannot write Harr install manifest: pinned LeanCTX identity probe failed", file=sys.stderr)
            return 2
        identity_text = identity.stdout.strip()
    managed_files: dict[str, Any] = {}
    wrapper_source = source_wrapper(paths)
    for key, path in {
        "leanctx_launcher": paths.leanctx,
        "leanctx_wrapper_source": wrapper_source,
        "doctor": paths.common / "doctor.py",
    }.items():
        if path and path.is_file():
            managed_files[key] = {"path": str(path), "sha256": sha256_file(path)}
    source: dict[str, Any] = {}
    if args.source_root:
        root = Path(args.source_root)
        commit = safe_run(["git", "-C", str(root), "rev-parse", "HEAD"], timeout=5)
        dirty = safe_run(["git", "-C", str(root), "status", "--porcelain"], timeout=5)
        if commit.returncode == 0:
            source = {"repository": str(root), "commit": commit.stdout.strip(), "dirty": bool(dirty.stdout.strip())}
    data = {
        "schema": 1,
        "harr_version": args.harr_version or os.environ.get("HARR_VERSION") or "unknown",
        "install_type": args.install_type,
        "installed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "platform": paths.platform,
        "source": source,
        "leanctx": {
            "version": os.environ.get("HARR_LEANCTX_VERSION") or "",
            "build": os.environ.get("HARR_LEANCTX_BUILD") or "",
            "identity": os.environ.get("HARR_LEANCTX_ID") or identity_text,
            "real_path": str(real) if real else "",
        },
        "managed_files": managed_files,
    }
    paths.manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with contextlib.suppress(OSError):
        paths.manifest.chmod(0o644)
    return 0


def human_output(checks: list[Check], actions: list[RepairAction], *, verbose: bool, final: bool = False) -> None:
    print("Harr doctor" + (" - post-repair verification" if final else ""))
    print()
    for check in checks:
        print(f"[{check.status:<4}] {check.id}: {check.summary}")
        if verbose and check.evidence:
            print("       " + json.dumps(check.evidence, ensure_ascii=False, sort_keys=True))
        if check.hint and check.status in {"WARN", "FAIL"}:
            print(f"       hint: {check.hint}")
    if actions:
        print("\nRepair plan/results")
        for action in actions:
            print(f"[{action.status:<10}] {action.id} ({action.risk}): {action.summary}")
            if verbose and action.evidence:
                print("             " + json.dumps(action.evidence, ensure_ascii=False, sort_keys=True))
    counts = {status: sum(1 for c in checks if c.status == status) for status in ("PASS", "WARN", "FAIL", "SKIP")}
    print(f"\nSummary: PASS={counts['PASS']} WARN={counts['WARN']} FAIL={counts['FAIL']} SKIP={counts['SKIP']}")


def report_json(checks: list[Check], actions: list[RepairAction], final_checks: list[Check] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"schema": 1, "checks": [c.as_dict() for c in checks], "repair": {"actions": [a.as_dict() for a in actions]}}
    if final_checks is not None:
        payload["post_repair_checks"] = [c.as_dict() for c in final_checks]
    return payload


def exit_code(checks: list[Check], strict: bool) -> int:
    if any(c.status == "FAIL" for c in checks):
        return 1
    if strict and any(c.status == "WARN" for c in checks):
        return 1
    return 0


def doctor_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="End-to-end Harr diagnostics and conservative repair")
    parser.add_argument("name", nargs="?", help="focus one enabled MCP or named Ein instance")
    parser.add_argument("--local", action="store_true", help="skip downstream MCP handshakes and external probes")
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--repair", action="store_true", help="apply only proven Harr-owned repairs")
    parser.add_argument("--dry-run", action="store_true", help="with --repair, show the plan without changing state")
    parser.add_argument("--write-manifest", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--install-type", choices=["package", "source"], default="source", help=argparse.SUPPRESS)
    parser.add_argument("--source-root", help=argparse.SUPPRESS)
    parser.add_argument("--harr-version", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    paths = Paths.detect()

    if args.write_manifest:
        return write_manifest(paths, args)
    if args.dry_run and not args.repair:
        parser.error("--dry-run requires --repair")

    checks, effective, manifest, stale_pids = diagnose(paths, focus=args.name, local_only=args.local)
    secrets = collect_secret_values(paths, effective)
    checks = [Check(**redact_value(dataclasses.asdict(check), secrets)) for check in checks]
    actions = plan_repairs(checks, manifest=manifest, stale_pids=stale_pids, effective=effective)

    if args.repair and not args.dry_run:
        actions, snapshot, journal = execute_repairs(paths, actions, manifest)
        if any(action.status == "FAILED" for action in actions):
            if snapshot and journal:
                restore_snapshot(snapshot, journal)
                for action in actions:
                    if action.status == "REPAIRED":
                        action.status = "ROLLED_BACK"
            payload = redact_value(report_json(checks, actions), secrets)
            print(json.dumps(payload, ensure_ascii=False, indent=2)) if args.json_output else human_output(checks, actions, verbose=args.verbose)
            return 3

        final_checks, _, _, _ = diagnose(paths, focus=args.name, local_only=args.local)
        final_checks = [Check(**redact_value(dataclasses.asdict(check), secrets)) for check in final_checks]
        affected = {check_id for action in actions if action.status == "REPAIRED" for check_id in action.check_ids}
        unresolved = [check for check in final_checks if check.id in affected and check.status == "FAIL"]
        if unresolved and snapshot and journal:
            restore_snapshot(snapshot, journal)
            for action in actions:
                if action.status == "REPAIRED":
                    action.status = "ROLLED_BACK"
            payload = redact_value(report_json(checks, actions, final_checks), secrets)
            print(json.dumps(payload, ensure_ascii=False, indent=2)) if args.json_output else human_output(final_checks, actions, verbose=args.verbose, final=True)
            return 3
        payload = redact_value(report_json(checks, actions, final_checks), secrets)
        print(json.dumps(payload, ensure_ascii=False, indent=2)) if args.json_output else human_output(final_checks, actions, verbose=args.verbose, final=True)
        return exit_code(final_checks, args.strict)

    payload = redact_value(report_json(checks, actions), secrets)
    print(json.dumps(payload, ensure_ascii=False, indent=2)) if args.json_output else human_output(checks, actions, verbose=args.verbose)
    return exit_code(checks, args.strict)


if __name__ == "__main__":
    raise SystemExit(doctor_main())
