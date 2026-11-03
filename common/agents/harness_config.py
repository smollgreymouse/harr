#!/usr/bin/env python3
"""Persistent top-level switch for Harr's agent-facing harness surface."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

DEFAULT_ENABLED = True


def config_dir() -> Path:
    explicit = os.environ.get("HARR_CONFIG_DIR")
    if explicit:
        return Path(explicit)
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "harr"


def state_path() -> Path:
    return config_dir() / "agent-harness.json"


def load_state() -> dict[str, bool]:
    path = state_path()
    if not path.exists():
        return {"enabled": DEFAULT_ENABLED}
    data = json.loads(path.read_text(encoding="utf-8"))
    enabled = data.get("enabled", DEFAULT_ENABLED)
    if not isinstance(enabled, bool):
        raise SystemExit("invalid agent harness enabled flag in config")
    return {"enabled": enabled}


def save_state(state: dict[str, bool]) -> None:
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)


def is_enabled() -> bool:
    return bool(load_state()["enabled"])


def main() -> int:
    parser = argparse.ArgumentParser(prog="harr agents harness")
    parser.add_argument("command", choices=("status", "enabled", "enable", "disable"))
    args = parser.parse_args()

    state = load_state()
    if args.command == "enabled":
        return 0 if state["enabled"] else 1
    if args.command in {"enable", "disable"}:
        state["enabled"] = args.command == "enable"
        save_state(state)
    print(f"Agent harness: {'enabled' if state['enabled'] else 'disabled'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
