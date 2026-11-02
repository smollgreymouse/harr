#!/usr/bin/env python3
"""Harr-managed orchestration/Asa configuration and Codex role rendering."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

DEFAULT_MODEL = "gpt-6.1-sol"
DEFAULT_EFFORT = "xhigh"
DEFAULT_ENABLED = False
VALID_EFFORTS = {"low", "medium", "high", "xhigh"}
MARKER = "# harr-managed-agent-v1"

ROLE_INSTRUCTIONS = """You are Harr's material-decision specialist.
Do not implement, edit, spawn agents, or broadly inspect the repository.
Answer only the decision requested from the supplied evidence.
Prefer existing contracts and the smallest coherent change.
If evidence is insufficient, request the exact missing facts.
Return the decision plus the invariants/risks the implementation owner must keep.
"""


def config_dir() -> Path:
    explicit = os.environ.get("HARR_CONFIG_DIR")
    if explicit:
        return Path(explicit)
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "harr"


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))


def state_path() -> Path:
    return config_dir() / "asa.json"


def role_path() -> Path:
    return codex_home() / "agents" / "asa-architect.toml"


def load_state() -> dict[str, object]:
    path = state_path()
    if not path.exists():
        return {"enabled": DEFAULT_ENABLED, "model": DEFAULT_MODEL, "effort": DEFAULT_EFFORT}
    data = json.loads(path.read_text(encoding="utf-8"))
    enabled = data.get("enabled", DEFAULT_ENABLED)
    if not isinstance(enabled, bool):
        raise SystemExit("invalid orchestration enabled flag in config")
    model = str(data.get("model") or DEFAULT_MODEL).strip()
    effort = str(data.get("effort") or DEFAULT_EFFORT).strip().lower()
    if not model:
        raise SystemExit("invalid Asa model in config")
    if effort not in VALID_EFFORTS:
        raise SystemExit(f"invalid Asa reasoning effort: {effort}")
    return {"enabled": enabled, "model": model, "effort": effort}


def save_state(state: dict[str, object]) -> None:
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)


def toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def render(state: dict[str, object]) -> str:
    return (
        f"{MARKER}\n"
        'name = "asa-architect"\n'
        'description = "Harr material architecture specialist for compact decision packets."\n'
        f"model = {toml_string(str(state['model']))}\n"
        f"model_reasoning_effort = {toml_string(str(state['effort']))}\n"
        f"developer_instructions = {toml_string(ROLE_INSTRUCTIONS)}\n\n"
        "[skills]\n"
        "include_instructions = false\n"
    )


def remove_managed_role() -> bool:
    path = role_path()
    if not path.exists():
        return False
    first = path.read_text(encoding="utf-8", errors="replace").splitlines()[:1]
    if first and first[0] == MARKER:
        path.unlink()
        return True
    return False


def apply_role(state: dict[str, object] | None = None, *, force: bool = False) -> Path:
    state = state or load_state()
    path = role_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        first = path.read_text(encoding="utf-8", errors="replace").splitlines()[:1]
        if first and first[0] != MARKER:
            raise SystemExit(f"refusing to overwrite non-Harr Asa role: {path}")
    tmp = path.with_suffix(".toml.tmp")
    tmp.write_text(render(state), encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    return path


def sync_role(state: dict[str, object] | None = None, *, force: bool = False) -> Path | None:
    state = state or load_state()
    if bool(state["enabled"]):
        return apply_role(state, force=force)
    remove_managed_role()
    return None


def print_status(state: dict[str, object]) -> None:
    path = role_path()
    managed = False
    if path.exists():
        first = path.read_text(encoding="utf-8", errors="replace").splitlines()[:1]
        managed = bool(first and first[0] == MARKER)
    print(f"Orchestration: {'enabled' if state['enabled'] else 'disabled'}")
    print(f"Asa model: {state['model']}")
    print(f"Asa effort: {state['effort']}")
    print(f"Codex role: {'managed' if managed else ('external' if path.exists() else 'missing')} {path}")


def main() -> int:
    parser = argparse.ArgumentParser(prog="harr agents")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    sub.add_parser("enabled")
    sub.add_parser("enable")
    sub.add_parser("disable")
    configure = sub.add_parser("configure")
    configure.add_argument("--model")
    configure.add_argument("--effort", choices=sorted(VALID_EFFORTS))
    configure.add_argument("--force", action="store_true", help=argparse.SUPPRESS)
    sync = sub.add_parser("sync")
    sync.add_argument("--force", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    state = load_state()
    if args.command == "enabled":
        return 0 if state["enabled"] else 1

    if args.command in {"enable", "disable"}:
        state["enabled"] = args.command == "enable"
        save_state(state)
        print(f"Orchestration: {'enabled' if state['enabled'] else 'disabled'}")
        return 0

    if args.command == "configure":
        if args.model:
            state["model"] = args.model.strip()
        if args.effort:
            state["effort"] = args.effort
        if not state["model"]:
            raise SystemExit("model cannot be blank")
        save_state(state)
        path = sync_role(state, force=args.force)
        print(f"Asa configured: model={state['model']} effort={state['effort']}")
        if path:
            print(f"Codex role: {path}")
        else:
            print("Orchestration disabled; Asa role not installed")
        return 0

    if args.command == "sync":
        path = sync_role(state, force=args.force)
        if path:
            print(f"Asa role applied: {path}")
        else:
            print("Orchestration disabled; Harr-managed Asa role absent")
        return 0

    print_status(state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
