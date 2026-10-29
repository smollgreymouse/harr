#!/usr/bin/env python3
"""Named Ein MCP setup and effective registry expansion.

Setup never runs an agent. Every enabled instance receives one MCP namespace,
with a fixed adapter and a common `ein` tool contract.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

# Running from an installed libexec directory does not put its parent on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

SLUG = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")
SECRET_NAME = re.compile(r"^[a-zA-Z0-9_-]+$")
ADAPTERS = frozenset({"gigacode", "opencode", "codex", "custom"})


def config_dir() -> Path:
    home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return Path(os.environ.get("HARR_CONFIG_DIR", home / "harr"))


def path() -> Path:
    return config_dir() / "einherjar" / "instances.json"


def validate(data: object) -> dict:
    if not isinstance(data, dict) or data.get("schema") != 2:
        raise ValueError("Ein instances must use schema 2")
    instances = data.get("instances")
    if not isinstance(instances, list):
        raise ValueError("Ein instances must be a list")

    ids: set[str] = set()
    for item in instances:
        if not isinstance(item, dict):
            raise ValueError("each Ein instance must be an object")
        name = item.get("id")
        adapter = item.get("adapter")
        if not isinstance(name, str) or not SLUG.fullmatch(name) or name in ids:
            raise ValueError("invalid or duplicate Ein MCP name")
        ids.add(name)
        if adapter not in ADAPTERS:
            raise ValueError(f"Ein {name}: invalid adapter")
        if not isinstance(item.get("enabled", True), bool):
            raise ValueError(f"Ein {name}: enabled must be boolean")
        codex_home = item.get("codex_home")
        if adapter == "codex" and codex_home is None:
            raise ValueError(f"Ein {name}: codex adapter requires explicit codex_home")
        if codex_home is not None:
            if adapter != "codex":
                raise ValueError(f"Ein {name}: codex_home requires adapter=codex")
            if (not isinstance(codex_home,str) or not Path(codex_home).is_absolute()
                or any(char in codex_home for char in "\n\r\x00")):
                raise ValueError(f"Ein {name}: codex_home must be an absolute directory path")
        executable = item.get("executable")
        if executable is not None and (
            not isinstance(executable, str)
            or not executable
            or any(char in executable for char in "\n\r\x00")
        ):
            raise ValueError(f"Ein {name}: invalid executable")
        refs = item.get("secret_env", {})
        if not isinstance(refs, dict) or any(
            not isinstance(key, str)
            or not ENV_NAME.fullmatch(key)
            or not isinstance(filename, str)
            or not SECRET_NAME.fullmatch(filename)
            for key, filename in refs.items()
        ):
            raise ValueError(f"Ein {name}: invalid secret environment references")
        if adapter == "custom":
            from common.executor.backends import validate_custom_backend
            errors = validate_custom_backend(name, item.get("definition"))
            if errors:
                raise ValueError("; ".join(errors))
        elif item.get("definition") is not None:
            raise ValueError(f"Ein {name}: built-in adapter cannot have custom definition")
    return data


def read() -> dict:
    source = path()
    if not source.exists():
        return {"schema": 2, "instances": []}
    try:
        return validate(json.loads(source.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid Ein instances file {source}: {exc}") from exc


def write(data: dict) -> None:
    validate(data)
    target = path()
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".instances-", dir=target.parent)
    try:
        os.chmod(tmp, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(data, out, ensure_ascii=False, indent=2)
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def config_for_instance(name: str) -> dict:
    for instance in read()["instances"]:
        if instance["id"] == name and instance.get("enabled", True):
            return instance
    raise ValueError("disabled or unknown Ein instance")


def expanded_servers(base: list[dict], config: dict | None = None) -> list[dict]:
    configured = (config if config is not None else read())["instances"]
    # Legacy standalone registrations are intentionally never emitted. The
    # literal name "gigacode" remains available to a named Ein instance.
    base = [server for server in base if server["name"] not in {"einherjar", "gigacode"}]

    known = {server["name"] for server in base}
    for item in configured:
        if not item.get("enabled", True):
            continue
        name = item["id"]
        if name in known:
            raise ValueError(f"Ein MCP name collision: {name}")
        known.add(name)
        base.append({
            "name": name,
            "label": item.get("display_name", name),
            "description": f"Named Ein {item['adapter']} worker. Use only after the user explicitly instructs you to delegate; never choose an executor automatically.",
            "required": False,
            "transport": "stdio",
            "lifecycle": "on-demand",
            "ein_instance": name,
            "runtime": {"kind": "bundled-python", "script": "einherjar_server.py", "version": "0.1.0", "args": []},
            "skill_reference": "einherjar.md",
        })
    return base


def refresh_effective() -> None:
    root = config_dir()
    selection = root / "mcp-selection.json"
    if not selection.exists():
        return
    command = [
        sys.executable, str(Path(__file__).with_name("selector.py")),
        "--catalog", str(Path(__file__).with_name("registry.json")),
        "--selection", str(selection),
        "--effective", str(root / "mcp-registry.json"),
        "--default", "required",
    ]
    subprocess.run(command, check=True)


def persist(data: dict) -> None:
    validate(data)
    catalog = json.loads(Path(__file__).with_name("registry.json").read_text(encoding="utf-8"))
    expanded_servers(list(catalog["servers"]), data)  # fail before altering persisted settings
    previous = read()
    write(data)
    try:
        refresh_effective()
    except Exception:
        write(previous)
        refresh_effective()
        raise


def parse_secret_env(items: list[str]) -> dict[str, str]:
    refs: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise ValueError("--secret-env must be ENV=SECRET_FILE")
        key, filename = item.split("=", 1)
        if not ENV_NAME.fullmatch(key) or not SECRET_NAME.fullmatch(filename):
            raise ValueError("invalid secret environment reference")
        refs[key] = filename
    return refs


def configure_wizard() -> None:
    script = str(Path(__file__).resolve())
    while True:
        print("\nHarr Ein workers (MCP names are chosen by you)")
        for item in read()["instances"]:
            state = "enabled" if item.get("enabled", True) else "disabled"
            print(f"  {item['id']:<24} {item['adapter']:<12} {state}")
        action = input("[A]dd [E]dit [D]isable [N] Enable [R]emove [Q]uit: ").strip().lower()
        if action in {"q", ""}:
            return
        if action == "a":
            name = input("MCP server name (unique, required): ").strip()
            adapter = input("Adapter (gigacode/opencode/codex/custom): ").strip()
            command = [sys.executable, script, "add", "--id", name, "--adapter", adapter]
            if adapter == "custom":
                command += ["--definition-file", input("Adapter JSON path: ").strip()]
        elif action in {"e", "d", "n", "r"}:
            name = input("Existing MCP server name: ").strip()
            operation = {"e": "edit", "d": "disable", "n": "enable", "r": "remove"}[action]
            command = [sys.executable, script, operation, name]
        else:
            print("Unknown action")
            continue
        if subprocess.run(command, check=False).returncode:
            print("Configuration unchanged; please correct the input")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="harr ein")
    commands = root.add_subparsers(dest="cmd", required=True)
    commands.add_parser("list")
    commands.add_parser("configure")
    add = commands.add_parser("add")
    add.add_argument("--id", help="unique user-chosen MCP server name")
    add.add_argument("--adapter", choices=sorted(ADAPTERS))
    add.add_argument("--display-name")
    add.add_argument("--definition-file")
    add.add_argument("--executable")
    add.add_argument("--codex-home", help="absolute local Codex profile path (codex adapter only)")
    add.add_argument("--secret-env", action="append", default=[], metavar="ENV=SECRET_FILE")
    for command in ("show", "enable", "disable", "remove", "test"):
        commands.add_parser(command).add_argument("name")
    edit = commands.add_parser("edit")
    edit.add_argument("name")
    edit.add_argument("--adapter", choices=sorted(ADAPTERS))
    edit.add_argument("--display-name")
    edit.add_argument("--definition-file")
    edit.add_argument("--executable")
    edit.add_argument("--codex-home", help="absolute local Codex profile path (codex adapter only)")
    edit.add_argument("--secret-env", action="append", default=[], metavar="ENV=SECRET_FILE")
    return root


def main() -> None:
    cli = parser()
    args = cli.parse_args()
    data = read()

    if args.cmd == "configure":
        configure_wizard()
        return
    if args.cmd == "list":
        for item in data["instances"]:
            state = "enabled" if item.get("enabled", True) else "disabled"
            print(item["id"], item["adapter"], state)
        return

    if args.cmd == "add":
        name = args.id or (input("MCP server name: ").strip() if sys.stdin.isatty() else "")
        backend = args.adapter or (
            input("Adapter [gigacode/opencode/codex/custom]: ").strip() if sys.stdin.isatty() else ""
        )
        if not SLUG.fullmatch(name):
            cli.error("MCP server name is required and must be a lowercase slug")
        if backend not in ADAPTERS:
            cli.error("select one of the supported adapters")
        if any(item["id"] == name for item in data["instances"]):
            cli.error("MCP name already exists")
        value = {"id": name, "adapter": backend, "enabled": True, "display_name": args.display_name or name}
        if args.executable:
            value["executable"] = args.executable
        if args.codex_home:
            value["codex_home"] = args.codex_home
        if args.secret_env:
            try:
                value["secret_env"] = parse_secret_env(args.secret_env)
            except ValueError as exc:
                cli.error(str(exc))
        if backend == "custom":
            if not args.definition_file:
                cli.error("custom adapter requires --definition-file")
            value["definition"] = json.loads(Path(args.definition_file).read_text(encoding="utf-8"))
        data["instances"].append(value)
        persist(data)
        print("Added Ein MCP:", name)
        return

    instance = next((item for item in data["instances"] if item["id"] == args.name), None)
    if instance is None:
        cli.error("unknown Ein MCP")
    if args.cmd == "show":
        print(json.dumps(instance, ensure_ascii=False, indent=2))
        return
    if args.cmd == "test":
        executable = instance.get("executable") or (
            instance["adapter"] if instance["adapter"] != "custom" else instance["definition"]["start"][0]
        )
        found = shutil.which(executable) is not None
        print("Config valid:", instance["id"], instance["adapter"], "| executable:",
              "found" if found else "missing", "(no model calls)")
        if not found:
            raise SystemExit(1)
        return
    if args.cmd == "edit":
        adapter = args.adapter or instance["adapter"]
        if sys.stdin.isatty() and not any((args.adapter, args.display_name, args.definition_file, args.executable, args.secret_env)):
            adapter = input(f"Adapter [{adapter}]: ").strip() or adapter
        instance["adapter"] = adapter
        if args.display_name:
            instance["display_name"] = args.display_name
        if args.executable:
            instance["executable"] = args.executable
        if args.codex_home:
            instance["codex_home"] = args.codex_home
        if args.secret_env:
            try:
                instance.setdefault("secret_env", {}).update(parse_secret_env(args.secret_env))
            except ValueError as exc:
                cli.error(str(exc))
        if args.definition_file:
            instance["definition"] = json.loads(Path(args.definition_file).read_text(encoding="utf-8"))
        if adapter != "custom":
            instance.pop("definition", None)
        if adapter != "codex":
            instance.pop("codex_home", None)
        persist(data)
    elif args.cmd == "remove":
        data["instances"].remove(instance)
        persist(data)
    else:
        instance["enabled"] = args.cmd == "enable"
        persist(data)
    print("Updated Ein MCP:", args.name)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, json.JSONDecodeError, OSError) as exc:
        raise SystemExit(f"Ein setup error: {exc}") from exc
