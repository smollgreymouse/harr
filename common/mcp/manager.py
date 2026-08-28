#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
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
        return shutil.which(command)
    raise SystemExit(f"unsupported runtime kind for MCP {server['name']}: {kind}")


def runtime_command(server: dict) -> list[str]:
    runtime = server.get("runtime", {})
    executable = path_runtime_executable(server)
    if not executable:
        command = runtime.get("command", "")
        hint = runtime.get("install_hint") or f"required command not found: {command}"
        raise SystemExit(hint)
    return [executable, *[str(item) for item in runtime.get("args", [])]]


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
    env.update(service_secret_env(server))
    cmd = runtime_command(server)
    if os.name == "nt":
        raise SystemExit(subprocess.call(cmd, env=env))
    os.execvpe(cmd[0], cmd, env)


def memento_var(secret_id: str) -> str:
    return "LEAN_CTX_SECRET_" + secret_id.encode("utf-8").hex().upper()


def exec_leanctx(args: argparse.Namespace, data: dict) -> None:
    env = os.environ.copy()
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
        elif kind in {"path", "uvx"}:
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
    elif args.command == "components":
        component_rows(args, data)


if __name__ == "__main__":
    main()
