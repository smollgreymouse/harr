#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import select
import sys
from pathlib import Path


def load_catalog(path: Path) -> dict:
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


def required_names(data: dict) -> list[str]:
    return [str(item["name"]) for item in data["servers"] if item.get("required") is True]


def normalize(data: dict, names: list[str]) -> list[str]:
    known = [str(item["name"]) for item in data["servers"]]
    requested = set(names)
    unknown = sorted(requested.difference(known))
    if unknown:
        raise SystemExit(f"unknown Harr MCP choice(s): {', '.join(unknown)}")
    requested.update(required_names(data))
    return [name for name in known if name in requested]


def read_selection(path: Path, data: dict, default: str) -> list[str]:
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema") != 1 or not isinstance(payload.get("enabled"), list):
            raise SystemExit(f"unsupported Harr MCP selection: {path}")
        return normalize(data, [str(item) for item in payload["enabled"]])
    if default == "all":
        return [str(item["name"]) for item in data["servers"]]
    return required_names(data)


def parse_spec(spec: str, data: dict) -> list[str]:
    value = spec.strip().lower()
    if not value or value == "none":
        return required_names(data)
    if value == "all":
        return [str(item["name"]) for item in data["servers"]]
    return normalize(data, [part.strip().lower() for part in value.split(",") if part.strip()])


def save_json(path: Path, payload: dict, private: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if private and os.name != "nt":
        try:
            path.chmod(0o600)
        except OSError:
            pass


def save_selection(path: Path, selected: list[str]) -> None:
    save_json(path, {"schema": 1, "enabled": selected}, private=True)


def write_effective(path: Path, data: dict, selected: list[str]) -> None:
    enabled = set(selected)
    save_json(path, {"schema": 1, "servers": [item for item in data["servers"] if item["name"] in enabled]}, private=True)


def is_interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def clear_screen() -> None:
    if os.name == "nt":
        os.system("cls")
    else:
        sys.stdout.write("\x1b[2J\x1b[H")
        sys.stdout.flush()


def read_key() -> str:
    if os.name == "nt":
        import msvcrt

        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            return {"H": "up", "P": "down"}.get(msvcrt.getwch(), "other")
        return {" ": "space", "\r": "enter", "\x1b": "escape"}.get(ch, "other")

    import termios
    import tty

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            tail = ""
            while select.select([sys.stdin], [], [], 0.01)[0]:
                tail += sys.stdin.read(1)
            if tail.startswith("[A"):
                return "up"
            if tail.startswith("[B"):
                return "down"
            return "escape"
        return {" ": "space", "\r": "enter", "\n": "enter"}.get(ch, "other")
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def label(server: dict) -> str:
    return str(server.get("label") or server["name"])


def description(server: dict) -> str:
    return str(server.get("description") or "")


def interactive_select(data: dict, initial: list[str]) -> list[str]:
    required = [item for item in data["servers"] if item.get("required") is True]
    optional = [item for item in data["servers"] if item.get("required") is not True]
    selected = set(initial)
    selected.update(str(item["name"]) for item in required)
    cursor = 0
    while True:
        clear_screen()
        print("Harr components\n")
        print("  [x] LeanCTX      required  compact MCP gateway")
        for server in required:
            print(f"  [x] {label(server):<12} required  {description(server)}")
        for index, server in enumerate(optional):
            name = str(server["name"])
            print(f"{'>' if index == cursor else ' '} [{'x' if name in selected else ' '}] {label(server):<12} optional  {description(server)}")
        print("\nUp/Down move   Space toggle   Enter apply   Esc cancel")
        key = read_key()
        if key == "up" and optional:
            cursor = (cursor - 1) % len(optional)
        elif key == "down" and optional:
            cursor = (cursor + 1) % len(optional)
        elif key == "space" and optional:
            name = str(optional[cursor]["name"])
            selected.symmetric_difference_update({name})
        elif key == "enter":
            clear_screen()
            return normalize(data, list(selected))
        elif key == "escape":
            raise SystemExit("Harr MCP selection cancelled")


def print_selection(data: dict, selected: list[str]) -> None:
    enabled = set(selected)
    print("Harr MCP selection:")
    print(f"  {'LeanCTX':<12} {'enabled':<8} required")
    for server in data["servers"]:
        name = str(server["name"])
        state = "enabled" if name in enabled else "disabled"
        kind = "required" if server.get("required") is True else "optional"
        print(f"  {label(server):<12} {state:<8} {kind}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Harr cross-platform MCP selection")
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--effective", type=Path, required=True)
    parser.add_argument("--spec", help="none, all, or comma-separated MCP names")
    parser.add_argument("--configure", action="store_true")
    parser.add_argument("--default", choices=["required", "all"], default="required")
    args = parser.parse_args()

    data = load_catalog(args.catalog)
    current = read_selection(args.selection, data, args.default)
    if args.spec is not None:
        selected = parse_spec(args.spec, data)
    elif args.configure and is_interactive():
        selected = interactive_select(data, current)
    else:
        selected = current
        if args.configure and not is_interactive():
            print("Interactive MCP selection unavailable; keeping the default/current selection.", file=sys.stderr)
            print("Use --all/-All, --mcp/-Mcp, or `harr mcp configure SPEC`.", file=sys.stderr)
    selected = normalize(data, selected)
    save_selection(args.selection, selected)
    write_effective(args.effective, data, selected)
    print_selection(data, selected)


if __name__ == "__main__":
    main()
