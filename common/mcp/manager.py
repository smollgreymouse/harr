#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_REGISTRY = HERE / "registry.json"
DEFAULT_TEMPLATE_DIR = HERE


def load_registry(path: Path = DEFAULT_REGISTRY) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != 1 or not isinstance(data.get("servers"), list):
        raise SystemExit(f"unsupported Harr MCP registry: {path}")
    names: set[str] = set()
    for server in data["servers"]:
        name = server.get("name")
        if not isinstance(name, str) or not name or name in names:
            raise SystemExit(f"invalid or duplicate Harr MCP name: {name!r}")
        names.add(name)
        doctor = server.get("doctor")
        if doctor is not None:
            if not isinstance(doctor, dict):
                raise SystemExit(f"invalid doctor metadata for MCP {name}: doctor must be an object")
            unknown = set(doctor).difference({"required_tools", "probe", "repair"})
            if unknown:
                raise SystemExit(f"invalid doctor metadata for MCP {name}: unknown fields {sorted(unknown)}")
            required = doctor.get("required_tools", [])
            if not isinstance(required, list) or not all(isinstance(item, str) and item for item in required):
                raise SystemExit(f"invalid doctor metadata for MCP {name}: required_tools must be non-empty strings")
            probe = doctor.get("probe")
            if probe is not None:
                if not isinstance(probe, dict):
                    raise SystemExit(f"invalid doctor metadata for MCP {name}: probe must be an object")
                unknown_probe = set(probe).difference({"kind", "tool", "arguments", "timeout_sec", "success"})
                if unknown_probe:
                    raise SystemExit(f"invalid doctor metadata for MCP {name}: unknown probe fields {sorted(unknown_probe)}")
                kind = probe.get("kind")
                if kind not in {"catalog-only", "mcp-ping", "tool"}:
                    raise SystemExit(f"invalid doctor metadata for MCP {name}: invalid probe kind {kind!r}")
                if kind == "tool" and (not isinstance(probe.get("tool"), str) or not probe.get("tool")):
                    raise SystemExit(f"invalid doctor metadata for MCP {name}: tool probe requires a tool")
                if "arguments" in probe and not isinstance(probe.get("arguments"), dict):
                    raise SystemExit(f"invalid doctor metadata for MCP {name}: probe arguments must be an object")
                timeout = probe.get("timeout_sec", 10)
                if not isinstance(timeout, int) or timeout < 1 or timeout > 30:
                    raise SystemExit(f"invalid doctor metadata for MCP {name}: probe timeout must be 1..30")
                success = probe.get("success", {})
                if not isinstance(success, dict) or set(success).difference({"json_content"}):
                    raise SystemExit(f"invalid doctor metadata for MCP {name}: invalid probe success")
                if "json_content" in success and not isinstance(success.get("json_content"), dict):
                    raise SystemExit(f"invalid doctor metadata for MCP {name}: success.json_content must be an object")
            repair = doctor.get("repair")
            if repair is not None:
                if not isinstance(repair, dict) or set(repair).difference({"runtime_reinstall", "credential_auto_repair"}):
                    raise SystemExit(f"invalid doctor metadata for MCP {name}: invalid repair metadata")
                if not all(isinstance(value, bool) for value in repair.values()):
                    raise SystemExit(f"invalid doctor metadata for MCP {name}: repair fields must be booleans")
    return data


def servers(data: dict, lifecycle: str | None = None) -> list[dict]:
    result = data["servers"]
    if lifecycle is not None:
        result = [item for item in result if item.get("lifecycle") == lifecycle]
    return result


def server_by_name(data: dict, name: str) -> dict:
    for item in data["servers"]:
        if item["name"] == name:
            return item
    raise SystemExit(f"unknown Harr MCP: {name}")


def secret_records(data: dict) -> list[tuple[dict, dict]]:
    out: list[tuple[dict, dict]] = []
    for server in data["servers"]:
        for secret in server.get("secrets", []):
            out.append((server, secret))
    return out


def secret_by_name(data: dict, name: str) -> tuple[dict, dict]:
    found = [(server, secret) for server, secret in secret_records(data) if secret.get("name") == name]
    if len(found) != 1:
        raise SystemExit(f"unknown or ambiguous Harr secret: {name}")
    return found[0]


def toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def render_gateway(data: dict, runner_command: str) -> str:
    chunks: list[str] = []
    for server in data["servers"]:
        name = server["name"]
        transport = server.get("transport")
        lines = ["[[gateway.servers]]", f"name = {toml_string(name)}", f"transport = {toml_string(transport)}", "enabled = true"]
        if transport == "stdio":
            lines += [f"command = {toml_string(runner_command)}", f"args = [{toml_string(name)}]", 'url = ""', "", "[gateway.servers.env]", "", "[gateway.servers.headers]"]
        elif transport == "http":
            url = server.get("url")
            if not url:
                raise SystemExit(f"HTTP MCP {name} has no url")
            lines += [f"url = {toml_string(url)}", "", "[gateway.servers.headers]"]
        else:
            raise SystemExit(f"unsupported MCP transport for {name}: {transport}")

        secret_env: list[tuple[str, str]] = []
        secret_headers: list[tuple[str, str]] = []
        for secret in server.get("secrets", []):
            target = secret.get("target", {})
            item = (target.get("name"), secret.get("memento_id"))
            if not all(item):
                raise SystemExit(f"invalid secret target for MCP {name}")
            if target.get("kind") == "env":
                secret_env.append(item)  # type: ignore[arg-type]
            elif target.get("kind") == "header":
                secret_headers.append(item)  # type: ignore[arg-type]
            else:
                raise SystemExit(f"unsupported secret target for MCP {name}: {target.get('kind')}")
        if secret_env and transport == "stdio":
            lines += ["", "[gateway.servers.secret_env]"]
            lines += [f"{key} = {{ id = {toml_string(secret_id)} }}" for key, secret_id in secret_env]
        if secret_headers and transport == "http":
            lines += ["", "[gateway.servers.secret_headers]"]
            lines += [f"{toml_string(key)} = {{ id = {toml_string(secret_id)} }}" for key, secret_id in secret_headers]
        chunks.append("\n".join(lines))
    return "\n\n".join(chunks) + ("\n" if chunks else "")


def shell_allowlist(platform: str) -> list[str]:
    common = ["clang-format"]
    if platform == "linux":
        return ["adb", "harr", "sudo", "apt-get", "openssl", *common]
    if platform == "windows":
        return ["adb", "harr", "openssl", *common]
    if platform == "macos":
        return ["adb", "harr", "sudo", "brew", "openssl", *common]
    raise SystemExit(f"unsupported Harr platform: {platform}")


def render_leanctx(args: argparse.Namespace, data: dict) -> None:
    text = Path(args.base).read_text(encoding="utf-8")
    allow = ",\n".join(f"    {toml_string(item)}" for item in shell_allowlist(args.platform))
    text = text.replace("{{HARR_SHELL_ALLOWLIST_EXTRA}}", allow)

    allow_paths: list[str] = []
    for raw in getattr(args, "allow_path", []):
        path = Path(raw).expanduser()
        if not path.is_absolute():
            raise SystemExit(f"LeanCTX allow path must be absolute: {raw}")
        value = str(path)
        if value not in allow_paths:
            allow_paths.append(value)
    rendered_paths = ",\n".join(f"    {toml_string(item)}" for item in allow_paths)
    text = text.replace("{{HARR_ALLOW_PATHS}}", rendered_paths)

    marker = "# {{HARR_GATEWAY_SERVERS}}"
    if marker not in text:
        raise SystemExit(f"LeanCTX base config has no marker: {marker}")
    text = text.replace(marker, render_gateway(data, args.runner_command).rstrip())
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(text.rstrip() + "\n", encoding="utf-8")


def npm_package_json(data: dict) -> None:
    deps: dict[str, str] = {}
    for server in data["servers"]:
        runtime = server.get("runtime", {})
        if runtime.get("kind") == "npm":
            package = runtime.get("package")
            version = runtime.get("version")
            if not package or not version:
                raise SystemExit(f"invalid npm runtime for MCP {server['name']}")
            deps[package] = version
    print(json.dumps({"name": "harr-mcp-runtime", "private": True, "dependencies": deps}, indent=2))


def install_configs(args: argparse.Namespace, data: dict) -> None:
    target_dir = Path(args.config_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    for server in data["servers"]:
        template_name = server.get("env_template")
        if not template_name:
            continue
        source = DEFAULT_TEMPLATE_DIR / template_name
        target = target_dir / f"{server['name']}.env"
        if not source.is_file():
            raise SystemExit(f"missing MCP env template for {server['name']}: {source}")
        if target.exists():
            print(f"preserve\t{server['name']}\t{target}")
            continue
        shutil.copyfile(source, target)
        try:
            target.chmod(0o600)
        except OSError:
            pass
        print(f"create\t{server['name']}\t{target}")


def config_home() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg)
    return Path.home() / ".config"


def harr_config_dir() -> Path:
    return Path(os.environ.get("HARR_CONFIG_DIR", config_home() / "harr"))


def workspace_root(cwd: Path | None = None) -> Path:
    current = (cwd or Path.cwd()).expanduser().resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return current


def workspace_store_dir() -> Path:
    root = harr_config_dir() / "workspaces"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        root.chmod(0o700)
    except OSError:
        pass
    return root


def workspace_store_path(primary: Path) -> Path:
    canonical = primary.expanduser().resolve()
    digest = hashlib.sha256(str(canonical).encode("utf-8")).hexdigest()[:24]
    return workspace_store_dir() / f"{digest}.json"


def workspace_admin(real: str | Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["LEAN_CTX_HEADLESS"] = "1"
    return subprocess.run(
        [str(real), "workspace-admin", *args],
        env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=30,
    )


def git_checkout_admin_dir(root: Path) -> Path | None:
    env = os.environ.copy()
    env.update({
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_OPTIONAL_LOCKS": "0",
    })
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE"):
        env.pop(key, None)
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--absolute-git-dir"],
        env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        check=False, timeout=10,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return Path(result.stdout.strip()).expanduser().resolve(strict=False)


def workspace_primary_binding(state: dict) -> dict | None:
    primary = state.get("primary")
    bindings = state.get("checkout_bindings")
    if not isinstance(primary, str) or not isinstance(bindings, dict):
        return None
    binding = bindings.get(primary)
    return binding if isinstance(binding, dict) else None


def git_admin_generation(git_dir: Path) -> str | None:
    if os.name != "posix":
        return None
    try:
        stat = git_dir.stat()
    except OSError:
        return None
    return f"unix:{stat.st_dev}:{stat.st_ino}"


def binding_matches_checkout(binding: dict, primary: Path) -> bool:
    current_git_dir = git_checkout_admin_dir(primary)
    if current_git_dir is None:
        return False
    stored_git_dir = binding.get("git_dir")
    if (
        not isinstance(stored_git_dir, str)
        or Path(stored_git_dir).expanduser().resolve(strict=False) != current_git_dir
    ):
        return False
    stored_generation = binding.get("checkout_generation")
    current_generation = git_admin_generation(current_git_dir)
    if isinstance(stored_generation, str) and current_generation is not None:
        return stored_generation == current_generation
    return True


def workspace_state_matches_primary(state: dict, primary: Path) -> bool:
    binding = workspace_primary_binding(state)
    if binding is not None:
        return binding_matches_checkout(binding, primary)
    configured = state.get("primary")
    return (
        isinstance(configured, str)
        and Path(configured).expanduser().resolve(strict=False) == primary
    )


def find_workspace_store_by_checkout(real: str | Path, primary: Path) -> Path | None:
    current_git_dir = git_checkout_admin_dir(primary)
    if current_git_dir is None:
        return None
    matches: list[Path] = []
    for candidate in sorted(workspace_store_dir().glob("*.json")):
        shown = workspace_admin(real, "show", str(candidate))
        if shown.returncode != 0:
            # Store discovery is intentionally read-only. Repair/reconciliation
            # is allowed only after a store has been selected explicitly.
            continue
        try:
            state = json.loads(shown.stdout)
        except json.JSONDecodeError:
            continue
        binding = workspace_primary_binding(state)
        if binding is None:
            continue
        if binding_matches_checkout(binding, primary):
            matches.append(candidate)
    if len(matches) > 1:
        raise SystemExit(
            "ambiguous Harr Workspace checkout binding: "
            + ", ".join(str(path) for path in matches)
        )
    return matches[0] if matches else None


def ensure_workspace_store(real: str | Path, primary: Path) -> Path:
    primary = primary.expanduser().resolve()
    store = workspace_store_path(primary)
    if not store.exists():
        matched = find_workspace_store_by_checkout(real, primary)
        if matched is not None:
            store = matched
        else:
            result = workspace_admin(real, "create", str(store), str(primary))
            if result.returncode != 0:
                raise SystemExit(f"cannot create Harr Workspace store: {result.stderr.strip() or result.stdout.strip()}")
    reconciled = workspace_admin(real, "reconcile", str(store))
    if reconciled.returncode != 0:
        raise SystemExit(
            "cannot reconcile Harr Workspace checkout identity: "
            + (reconciled.stderr.strip() or reconciled.stdout.strip())
        )
    shown = workspace_admin(real, "show", str(store))
    if shown.returncode != 0:
        raise SystemExit(f"cannot read Harr Workspace store: {shown.stderr.strip() or shown.stdout.strip()}")
    try:
        state = json.loads(shown.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid Harr Workspace store output: {exc}") from exc
    if not workspace_state_matches_primary(state, primary):
        raise SystemExit(f"Harr Workspace store primary mismatch: expected {primary}, got {state.get('primary')}")
    return store


def leanctx_is_mcp(rest: list[str]) -> bool:
    return not rest or rest[0] == "mcp"


def npm_bin_dir() -> Path:
    override = os.environ.get("HARR_NPM_BIN_DIR")
    if override:
        return Path(override)
    if os.name == "nt":
        local = os.environ.get("HARR_LOCALAPPDATA") or os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(local) / "Harr" / "share" / "npm" / "node_modules" / ".bin"
    return Path.home() / ".local" / "share" / "harr" / "npm" / "node_modules" / ".bin"


def load_env_file(path: Path, forbidden: set[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    if not path.exists():
        return result
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise SystemExit(f"invalid Harr MCP env line in {path}: {raw}")
        key, value = line.split("=", 1)
        key = key.strip()
        if key in forbidden:
            raise SystemExit(f"secret {key} must not be stored in {path}")
        result[key] = value
    return result


def path_runtime_executable(server: dict) -> str | None:
    runtime = server.get("runtime", {})
    kind = runtime.get("kind")
    if kind == "bundled-python":
        script = runtime.get("script")
        if not script:
            raise SystemExit(f"MCP {server['name']} bundled runtime has no script")
        candidate = DEFAULT_TEMPLATE_DIR / str(script)
        if not candidate.is_file():
            raise SystemExit(f"MCP {server['name']} bundled runtime is missing: {candidate}")
        return sys.executable

    command = runtime.get("command")
    if not command:
        raise SystemExit(f"MCP {server['name']} has no runtime command")
    if kind == "npm":
        candidate = npm_bin_dir() / command
        if os.name == "nt" and not candidate.exists() and (candidate.with_suffix(".cmd")).exists():
            candidate = candidate.with_suffix(".cmd")
        if not candidate.exists():
            raise SystemExit(f"MCP {server['name']} runtime is not installed: {candidate}")
        return str(candidate)
    if kind in {"path", "uvx"}:
        found = shutil.which(command)
        if found:
            return found
        candidates: list[Path] = []
        if os.name == "nt":
            candidates.extend([
                Path.home() / ".local" / "bin" / f"{command}.exe",
                Path.home() / ".local" / "bin" / f"{command}.cmd",
            ])
        else:
            candidates.extend([
                Path.home() / ".local" / "bin" / command,
                Path.home() / ".cargo" / "bin" / command,
                Path("/opt/homebrew/bin") / command,
                Path("/usr/local/bin") / command,
            ])
        return next((str(candidate) for candidate in candidates if candidate.is_file()), None)
    raise SystemExit(f"unsupported runtime kind for MCP {server['name']}: {kind}")


def runtime_command(server: dict) -> list[str]:
    runtime = server.get("runtime", {})
    executable = path_runtime_executable(server)
    if not executable:
        command = runtime.get("command", "")
        hint = runtime.get("install_hint") or f"required command not found: {command}"
        raise SystemExit(hint)

    requires_command = runtime.get("requires_command")
    if requires_command and not shutil.which(str(requires_command)):
        hint = runtime.get("install_hint") or f"required command not found: {requires_command}"
        raise SystemExit(hint)

    args = [str(item) for item in runtime.get("args", [])]
    if runtime.get("kind") == "bundled-python":
        script = DEFAULT_TEMPLATE_DIR / str(runtime["script"])
        return [executable, str(script), *args]
    if runtime.get("readonly_proxy"):
        proxy = DEFAULT_TEMPLATE_DIR / str(runtime["readonly_proxy"])
        if not proxy.is_file() or proxy.parent != DEFAULT_TEMPLATE_DIR:
            raise SystemExit(f"MCP {server['name']} read-only proxy missing")
        return [sys.executable, str(proxy), executable, *args]
    return [executable, *args]


def runtime_maintenance_command(server: dict, field: str) -> list[str] | None:
    runtime = server.get("runtime", {})
    args = runtime.get(field)
    if args is None:
        return None
    executable = path_runtime_executable(server)
    if not executable:
        command = runtime.get("command", "")
        hint = runtime.get("install_hint") or f"required command not found: {command}"
        raise SystemExit(hint)
    if not isinstance(args, list) or not all(isinstance(item, str) for item in args):
        raise SystemExit(f"invalid {field} for MCP {server['name']}")
    return [executable, *args]


def service_secret_env(server: dict) -> dict[str, str]:
    secret_root = harr_config_dir() / "secrets"
    result: dict[str, str] = {}
    for secret in server.get("secrets", []):
        target = secret.get("target", {})
        if target.get("kind") != "env":
            continue
        name = target.get("name")
        filename = secret.get("file")
        if not name or not filename:
            raise SystemExit(f"invalid env secret target for MCP {server['name']}")
        path = secret_root / filename
        if not path.is_file():
            continue
        value = path.read_text(encoding="utf-8").strip()
        if value:
            result[str(name)] = value
    return result


def prefetch_runtimes(data: dict) -> None:
    for server in data["servers"]:
        cmd = runtime_maintenance_command(server, "prefetch_args")
        if not cmd:
            continue
        print(f"Preparing {server['label']} MCP runtime...")
        subprocess.run(cmd, check=True)


def runtime_env(server: dict) -> dict[str, str]:
    runtime = server.get("runtime", {})
    env = runtime.get("env")
    if env is None:
        return {}
    if not isinstance(env, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in env.items()):
        raise SystemExit(f"invalid runtime.env for MCP {server['name']}")
    forbidden = {
        secret.get("target", {}).get("name")
        for secret in server.get("secrets", [])
        if secret.get("target", {}).get("kind") == "env"
    }
    forbidden.discard(None)
    for key in env:
        if key in forbidden:
            raise SystemExit(f"secret {key} must not be stored in runtime.env for MCP {server['name']}")
    return dict(env)


def system_trust_bundle() -> Path | None:
    """Combine system OpenSSL CAs with explicitly TLS-trusted user NSS CAs.

    Never use arbitrary certificates from a directory or server handshake as roots.
    """
    if sys.platform != "linux":
        return None
    system = Path("/etc/ssl/certs/ca-certificates.crt")
    nss = Path.home() / ".pki" / "nssdb"
    certutil = shutil.which("certutil")
    if not system.is_file() or not (nss / "cert9.db").is_file():
        return system if system.is_file() else None
    if not certutil:
        return system

    listing = subprocess.run(
        [certutil, "-L", "-d", f"sql:{nss}"],
        capture_output=True, text=True, check=False, timeout=12,
    )
    if listing.returncode != 0:
        return system

    anchors = []
    for line in listing.stdout.splitlines():
        parts = line.rsplit(None, 1)
        if len(parts) != 2:
            continue
        nickname, flags = parts
        # NSS certutil marks trust for TLS in the first comma-separated column.
        tls_trust = flags.split(",", 1)[0]
        if "C" not in tls_trust:
            continue
        cert = subprocess.run(
            [certutil, "-L", "-d", f"sql:{nss}", "-n", nickname, "-a"],
            capture_output=True, check=False, timeout=12,
        )
        if cert.returncode == 0 and b"-----BEGIN CERTIFICATE-----" in cert.stdout:
            anchors.append(cert.stdout)
    if not anchors:
        return system

    destination = harr_config_dir() / "ca" / "system-nss-bundle.pem"
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".ca-", dir=destination.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(system.read_bytes())
            for anchor in anchors:
                output.write(b"\n" + anchor)
        os.chmod(temporary, 0o600)
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return destination


def prepare_jira_env(env: dict[str, str]) -> dict[str, str]:
    """Validate Jira authentication settings without logging secrets."""
    from urllib.parse import urlsplit

    result = dict(env)
    endpoint = result.get("JIRA_URL", "")
    parsed = urlsplit(endpoint)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise SystemExit("Jira URL must be an HTTPS endpoint without embedded credentials")
    host = result.get("JIRA_HOST", "").strip()
    if host:
        if any(ch in host for ch in "/:@ \t\r\n") or host.lower() != parsed.hostname.lower():
            raise SystemExit("JIRA_HOST differs from Jira URL host; upstream MCP cannot safely override Host (requires separate reverse-proxy adapter)")
    mode = result.get("JIRA_AUTH_MODE", "pat").strip().lower()
    if mode == "basic":
        user = result.pop("JIRA_USER_NAME", "")
        password = result.pop("JIRA_USER_PASS", "")
        if not user or not password:
            raise SystemExit("Jira basic auth requires JIRA_USER_NAME and the Harr jira secret")
        result["JIRA_USERNAME"] = user
        result["JIRA_API_TOKEN"] = password
        result.pop("JIRA_PERSONAL_TOKEN", None)
    elif mode == "pat":
        if not result.get("JIRA_PERSONAL_TOKEN"):
            raise SystemExit("Jira PAT auth requires harr secret set jira-pat")
        result.pop("JIRA_USER_PASS", None)
        result.pop("JIRA_USER_NAME", None)
    else:
        raise SystemExit("JIRA_AUTH_MODE must be basic or pat")
    return result


def materialize_jira_nss_client_cert(env: dict[str, str]) -> tuple[dict[str, str], Path | None]:
    """Export a selected NSS client identity into a private runtime directory.

    The private key is never written to repository/config files and is removed
    when the Jira MCP child exits.
    """
    nickname = env.get("JIRA_CLIENT_CERT_NSS", "").strip()
    if not nickname:
        return env, None
    if env.get("JIRA_CLIENT_CERT") or env.get("JIRA_CLIENT_KEY"):
        raise SystemExit("Configure either JIRA_CLIENT_CERT_NSS or PEM client certificate paths, not both")
    if sys.platform != "linux":
        raise SystemExit("JIRA_CLIENT_CERT_NSS is currently supported only on Linux")

    nss_dir = Path(env.get("JIRA_CLIENT_CERT_NSS_DB", str(Path.home() / ".pki" / "nssdb"))).expanduser()
    if not (nss_dir / "cert9.db").is_file():
        raise SystemExit(f"Jira NSS certificate database is missing: {nss_dir}")

    pk12util = shutil.which("pk12util")
    openssl = shutil.which("openssl")
    if not pk12util or not openssl:
        raise SystemExit("Jira NSS client certificate support requires pk12util and openssl")

    runtime_base = Path(os.environ.get("XDG_RUNTIME_DIR", tempfile.gettempdir())) / "harr"
    runtime_base.mkdir(parents=True, exist_ok=True)
    os.chmod(runtime_base, 0o700)
    runtime_dir = Path(tempfile.mkdtemp(prefix="jira-client-", dir=runtime_base))
    os.chmod(runtime_dir, 0o700)

    password_file = runtime_dir / ".p12-password"
    p12_file = runtime_dir / "client.p12"
    cert_file = runtime_dir / "client-cert.pem"
    key_file = runtime_dir / "client-key.pem"
    password_file.write_text(os.urandom(24).hex(), encoding="ascii")
    os.chmod(password_file, 0o600)

    try:
        exported = subprocess.run(
            [pk12util, "-o", str(p12_file), "-n", nickname, "-d", f"sql:{nss_dir}", "-w", str(password_file)],
            stdin=subprocess.DEVNULL, capture_output=True, check=False, timeout=15,
        )
        if exported.returncode != 0:
            raise SystemExit(f"Failed to export Jira client certificate {nickname!r} from NSS")

        for output, args in (
            (cert_file, ["-clcerts", "-nokeys"]),
            (key_file, ["-nocerts", "-nodes"]),
        ):
            converted = subprocess.run(
                [openssl, "pkcs12", "-in", str(p12_file), "-passin", f"file:{password_file}", *args, "-out", str(output)],
                stdin=subprocess.DEVNULL, capture_output=True, check=False, timeout=15,
            )
            if converted.returncode != 0:
                raise SystemExit(f"Failed to prepare Jira client certificate {nickname!r} for TLS")
            os.chmod(output, 0o600)
    except BaseException:
        shutil.rmtree(runtime_dir, ignore_errors=True)
        raise
    finally:
        p12_file.unlink(missing_ok=True)
        password_file.unlink(missing_ok=True)

    result = dict(env)
    result.pop("JIRA_CLIENT_CERT_NSS", None)
    result.pop("JIRA_CLIENT_CERT_NSS_DB", None)
    result["JIRA_CLIENT_CERT"] = str(cert_file)
    result["JIRA_CLIENT_KEY"] = str(key_file)
    return result, runtime_dir


def jira_preflight(env: dict[str, str]) -> int:
    """Probe Jira identity with verified TLS; return status without credential disclosure."""
    import base64
    import ssl
    import urllib.error
    import urllib.request

    url = env["JIRA_URL"].rstrip("/") + "/rest/api/2/myself"
    if env.get("JIRA_AUTH_MODE", "pat").lower() == "basic":
        raw = (env["JIRA_USERNAME"] + ":" + env["JIRA_API_TOKEN"]).encode()
        authorization = "Basic " + base64.b64encode(raw).decode("ascii")
    else:
        authorization = "Bearer " + env["JIRA_PERSONAL_TOKEN"]
    context = ssl.create_default_context(cafile=env.get("SSL_CERT_FILE") or None)
    client_cert = env.get("JIRA_CLIENT_CERT")
    if client_cert:
        context.load_cert_chain(
            certfile=client_cert,
            keyfile=env.get("JIRA_CLIENT_KEY") or None,
            password=env.get("JIRA_CLIENT_KEY_PASSWORD") or None,
        )
    request = urllib.request.Request(url, headers={"Authorization": authorization, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, context=context, timeout=12) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


def run_server(args: argparse.Namespace, data: dict) -> None:
    server = server_by_name(data, args.name)
    env = os.environ.copy()
    forbidden = {
        secret.get("target", {}).get("name")
        for secret in server.get("secrets", [])
        if secret.get("target", {}).get("kind") == "env"
    }
    forbidden.discard(None)
    env_path = harr_config_dir() / "mcp" / f"{server['name']}.env"
    if server.get("env_template") and not env_path.exists():
        raise SystemExit(f"MCP {server['name']} configuration is missing: {env_path}")
    env.update(load_env_file(env_path, forbidden))
    env.update(runtime_env(server))
    # Instance identity must be supplied by Harr, not inherited from callers.
    env.pop("HARR_EIN_INSTANCE", None)
    env.pop("HARR_EIN_EXECUTABLE", None)
    if server.get("ein_instance"):
        from ein_instances import prepare_instance_runtime_env
        try:
            env = prepare_instance_runtime_env(str(server["ein_instance"]), env)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
    env.update(service_secret_env(server))
    if server.get("trust_store") == "system":
        bundle = system_trust_bundle()
        if bundle:
            env["SSL_CERT_FILE"] = str(bundle)
            env["REQUESTS_CA_BUNDLE"] = str(bundle)
    jira_runtime_dir: Path | None = None
    if server["name"] == "jira":
        env = prepare_jira_env(env)
        env, jira_runtime_dir = materialize_jira_nss_client_cert(env)
        try:
            status = jira_preflight(env)
            if status != 200:
                raise SystemExit(f"Jira credential preflight failed (HTTP {status}); MCP was not started")
        except BaseException:
            if jira_runtime_dir:
                shutil.rmtree(jira_runtime_dir, ignore_errors=True)
            raise
    cmd = runtime_command(server)
    if os.name == "nt" or jira_runtime_dir is not None:
        try:
            raise SystemExit(subprocess.call(cmd, env=env))
        finally:
            if jira_runtime_dir:
                shutil.rmtree(jira_runtime_dir, ignore_errors=True)
    os.execvpe(cmd[0], cmd, env)


def memento_var(secret_id: str) -> str:
    return "LEAN_CTX_SECRET_" + secret_id.encode("utf-8").hex().upper()


def read_workspace_state(real: str | Path, store: Path) -> dict:
    result = workspace_admin(real, "show", str(store))
    if result.returncode != 0:
        raise SystemExit(result.stderr.strip() or result.stdout.strip() or f"cannot read Workspace {store}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid Workspace JSON from LeanCTX: {exc}") from exc


def workspace_command(args: argparse.Namespace) -> None:
    real = Path(args.real).expanduser().resolve()
    if not real.is_file():
        raise SystemExit(f"LeanCTX binary not found: {real}")
    if args.action == "list":
        rows: list[dict] = []
        for store in sorted(workspace_store_dir().glob("*.json")):
            try:
                state = read_workspace_state(real, store)
            except SystemExit as exc:
                rows.append({
                    "store": str(store),
                    "status": "error",
                    "error": str(exc),
                })
                continue
            rows.append({"store": str(store), "status": "ok", **state})
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return

    primary = workspace_root(Path(args.project).expanduser() if args.project else None)
    store = ensure_workspace_store(real, primary)
    state = read_workspace_state(real, store)
    if args.action == "show":
        payload = {"store": str(store), **state}
        configured_primary = state.get("primary")
        if isinstance(configured_primary, str) and Path(configured_primary).resolve(strict=False) != primary:
            payload["activePrimary"] = str(primary)
            payload["primaryStatus"] = "moved"
        else:
            payload["activePrimary"] = str(primary)
            payload["primaryStatus"] = "active"
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    def resolve_target(raw: str, *, require_directory: bool = True) -> Path:
        target = Path(raw).expanduser()
        if not target.is_absolute():
            target = Path.cwd() / target
        target = target.resolve(strict=False)
        if require_directory and not target.is_dir():
            raise SystemExit(f"Workspace root is not a directory: {target}")
        return target

    if args.action == "sync":
        if not args.paths:
            raise SystemExit("workspace sync requires at least one path")
        primary_path = primary
        existing = {str(Path(path).resolve()) for path in state.get("additional", [])}
        seen: set[str] = set()
        added: list[str] = []
        skipped: list[dict[str, str]] = []
        for raw in args.paths:
            target = resolve_target(raw)
            target_text = str(target)
            if target == primary_path:
                skipped.append({"path": target_text, "reason": "primary"})
                continue
            if target_text in seen:
                skipped.append({"path": target_text, "reason": "duplicate-input"})
                continue
            seen.add(target_text)
            if target_text in existing:
                skipped.append({"path": target_text, "reason": "already-present"})
                continue
            result = workspace_admin(real, "add", str(store), target_text, str(state["revision"]))
            if result.returncode != 0:
                message = result.stderr.strip() or result.stdout.strip() or f"workspace add failed: {target_text}"
                lowered = message.lower()
                if (
                    "sibling worktree" in lowered
                    or "worktree topology" in lowered
                    or "same local git" in lowered
                ):
                    skipped.append({"path": target_text, "reason": "same-repository-worktree"})
                    continue
                raise SystemExit(message)
            state = json.loads(result.stdout)
            existing.add(target_text)
            added.append(target_text)
        print(json.dumps({"store": str(store), **state, "sync": {"added": added, "skipped": skipped}}, ensure_ascii=False, indent=2))
        return

    if len(args.paths) != 1:
        raise SystemExit(f"workspace {args.action} requires exactly one path")
    operation = "add" if args.action == "add" else "remove"
    target = resolve_target(args.paths[0], require_directory=operation == "add")
    expected_revision = args.expected_revision if args.expected_revision is not None else int(state["revision"])
    result = workspace_admin(real, operation, str(store), str(target), str(expected_revision))
    if result.returncode != 0:
        raise SystemExit(result.stderr.strip() or result.stdout.strip() or f"workspace {operation} failed")
    updated = json.loads(result.stdout)
    print(json.dumps({"store": str(store), **updated}, ensure_ascii=False, indent=2))


def exec_leanctx(args: argparse.Namespace, data: dict) -> None:
    env = os.environ.copy()
    if leanctx_is_mcp(args.rest):
        # rmcp logs whole initialize payloads at info, including base64 icons.
        # These can overflow a host's nonblocking stderr and panic discovery.
        # Keep normal server logs while allowing an explicit LeanCTX override.
        env.setdefault("LEAN_CTX_LOG", f"{env.get('RUST_LOG') or 'info'},rmcp=warn")
        # The managed server-info icon lives beside the installed MCP runtime.
        # Keep the source checkout fallback useful for direct development runs.
        icon = HERE / "assets" / "harr.png"
        if not icon.is_file():
            checkout_icon = HERE.parents[1] / "harr.png"
            if checkout_icon.is_file():
                icon = checkout_icon
        if icon.is_file():
            env["HARR_MCP_ICON_PATH"] = str(icon)
    if leanctx_is_mcp(args.rest) and env.get("HARR_WORKSPACE_MODE", "strict") != "legacy":
        primary = workspace_root()
        store = ensure_workspace_store(args.real, primary)
        env["LEAN_CTX_STRICT_WORKSPACE"] = "1"
        # Workspace changes root authority, not the familiar Harr tool surface.
        # Preserve the pre-Workspace Codex/OpenCode tools in every Harr-managed
        # strict session; LeanCTX still enforces request-scoped Workspace roots.
        env["LEAN_CTX_STRICT_WORKSPACE_LEGACY_TOOLS"] = "1"
        env["LEAN_CTX_WORKSPACE_FILE"] = str(store)
    secret_root = harr_config_dir() / "secrets"
    for _, secret in secret_records(data):
        path = secret_root / secret["file"]
        if not path.is_file():
            continue
        value = path.read_text(encoding="utf-8").strip()
        if value:
            env[memento_var(secret["memento_id"])] = value
    cmd = [args.real, *args.rest]
    if os.name == "nt":
        raise SystemExit(subprocess.call(cmd, env=env))
    os.execvpe(cmd[0], cmd, env)


def component_rows(args: argparse.Namespace, data: dict) -> None:
    prefix = Path(args.npm_prefix) if args.npm_prefix else None
    for server in data["servers"]:
        runtime = server.get("runtime", {})
        kind = runtime.get("kind")
        expected = runtime.get("version") or runtime.get("package") or runtime.get("command") or "-"
        installed = "-"
        state = "missing"
        if kind == "npm" and prefix is not None:
            package = runtime.get("package")
            package_json = prefix / "node_modules" / Path(*str(package).split("/")) / "package.json"
            if package_json.is_file():
                try:
                    installed = json.loads(package_json.read_text(encoding="utf-8")).get("version", "-")
                except Exception:
                    installed = "invalid"
                state = "ok" if installed == expected else "version-mismatch"
        elif kind in {"path", "uvx", "bundled-python"}:
            resolved = path_runtime_executable(server)
            if resolved:
                installed = resolved
                if kind == "uvx":
                    probe = runtime_maintenance_command(server, "probe_args")
                    try:
                        result = subprocess.run(probe or [], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False, timeout=15)
                    except (OSError, subprocess.TimeoutExpired):
                        state = "not-ready"
                    else:
                        if result.returncode == 0:
                            version = next((line.strip() for line in result.stdout.splitlines() if line.strip()), "cached")
                            installed = version
                            state = "ready"
                        else:
                            state = "not-cached"
                elif kind == "bundled-python":
                    requires_command = runtime.get("requires_command")
                    if requires_command and not shutil.which(str(requires_command)):
                        state = "dependency-missing"
                        installed = f"{resolved} (missing {requires_command})"
                    else:
                        state = "available"
                else:
                    state = "available"
        print(f"{server['name']}\t{expected}\t{state}\t{installed}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Harr platform-independent MCP registry manager")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    sub = parser.add_subparsers(dest="command", required=True)

    p_names = sub.add_parser("names")
    p_names.add_argument("--lifecycle")

    sub.add_parser("npm-package-json")
    sub.add_parser("prefetch-runtimes")

    p_render = sub.add_parser("render-leanctx")
    p_render.add_argument("--base", required=True)
    p_render.add_argument("--output", required=True)
    p_render.add_argument("--platform", required=True, choices=["linux", "windows", "macos"])
    p_render.add_argument("--runner-command", default="harr-mcp-run")
    p_render.add_argument("--allow-path", action="append", default=[])

    p_install = sub.add_parser("install-configs")
    p_install.add_argument("--config-dir", required=True)

    p_secret = sub.add_parser("secret")
    p_secret.add_argument("name")

    sub.add_parser("secrets")

    p_field = sub.add_parser("server-field")
    p_field.add_argument("name")
    p_field.add_argument("field")

    p_run = sub.add_parser("run")
    p_run.add_argument("name")

    p_exec = sub.add_parser("exec-leanctx")
    p_exec.add_argument("real")
    p_exec.add_argument("rest", nargs=argparse.REMAINDER)

    p_workspace = sub.add_parser("workspace")
    p_workspace.add_argument("action", choices=["show", "list", "add", "remove", "sync"])
    p_workspace.add_argument("paths", nargs="*")
    p_workspace.add_argument("--real", required=True)
    p_workspace.add_argument("--project")
    p_workspace.add_argument("--expected-revision", type=int)

    p_components = sub.add_parser("components")
    p_components.add_argument("--npm-prefix")

    args = parser.parse_args()
    data = load_registry(args.registry)

    if args.command == "names":
        for item in servers(data, args.lifecycle):
            print(item["name"])
    elif args.command == "npm-package-json":
        npm_package_json(data)
    elif args.command == "prefetch-runtimes":
        prefetch_runtimes(data)
    elif args.command == "render-leanctx":
        render_leanctx(args, data)
    elif args.command == "install-configs":
        install_configs(args, data)
    elif args.command == "secret":
        server, secret = secret_by_name(data, args.name)
        print(json.dumps({"server": server["name"], **secret}, ensure_ascii=False))
    elif args.command == "secrets":
        for server, secret in secret_records(data):
            print(json.dumps({"server": server["name"], **secret}, ensure_ascii=False))
    elif args.command == "server-field":
        value = server_by_name(data, args.name).get(args.field, "")
        if isinstance(value, (dict, list)):
            print(json.dumps(value, ensure_ascii=False))
        else:
            print(value)
    elif args.command == "run":
        run_server(args, data)
    elif args.command == "exec-leanctx":
        if args.rest and args.rest[0] == "--":
            args.rest = args.rest[1:]
        exec_leanctx(args, data)
    elif args.command == "workspace":
        workspace_command(args)
    elif args.command == "components":
        component_rows(args, data)


if __name__ == "__main__":
    main()
