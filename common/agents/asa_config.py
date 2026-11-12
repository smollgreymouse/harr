#!/usr/bin/env python3
"""Harr-managed orchestration/Asa configuration and Codex role rendering."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

DEFAULT_MODEL = "gpt-6.1-sol"
# The working default is the chat plan's model; point zcode_model at a larger
# GLM (for example account:<plan>/GLM-5.3) once that provider is connected.
DEFAULT_ZCODE_MODEL = "account:zai-start-plan/GLM-5.3-Flash"
DEFAULT_EFFORT = "xhigh"
DEFAULT_ENABLED = False
VALID_EFFORTS = {"low", "medium", "high", "xhigh"}
MARKER = "# harr-managed-agent-v1"
ZCODE_MARKER = "<!-- harr-managed-agent-v1 -->"
ZCODE_THOUGHT_LEVELS = {"low": "low", "medium": "high", "high": "high", "xhigh": "max"}

ROLE_INSTRUCTIONS = """You are Harr's persistent architect-grade decision, bounded-analysis, and user-dialogue specialist.
Do not implement, edit, or spawn agents.
You are a persistent child thread: the initial fork may contain the root history at spawn time, but you do not automatically receive later root turns. Treat later follow-up messages as authoritative deltas plus the current request; do not demand retransmission of facts already in your own context.
Default architecture mode: resolve the exact material architecture question from your inherited/persistent context and supplied evidence. Do not search the repository or discover evidence yourself. The caller prepares facts and constraints; do not ask the caller to pre-design alternatives. For root-owned scope, concise verified anchors/deltas may be supplied for decisive tool-output facts, compaction-sensitive facts, or facts learned after your initial fork. For delegated scope, the caller supplies the existing Worker or Ein compact evidence handoff.
Each routed request declares one mode: `mode=architecture-decision`, `mode=user-dialogue`, or `mode=explicit-analysis`; follow that mode instead of inferring a different contract.
Routed user-dialogue mode: when the caller says the user is addressing Asa, answer that user question directly from your persistent context and supplied evidence. Preserve continuity with your earlier decisions/analysis. Do not turn a conversational follow-up into a fresh architecture decision unless the user actually asks for one.
Explicit-analysis mode: when the user explicitly asks you yourself to analyze selected code, an image, or other material, the caller must still prepare the surrounding evidence and constraints before invoking you, but must not perform the requested deep analysis first. Independently analyze the exact supplied material. For caller-supplied workspace code, use only a narrow exact Harr/LeanCTX read of the supplied path/range; do not use shell, search, glob, or repository exploration to acquire evidence. For other supplied material, use only the exact viewer/read operation needed for that material. Do not change Workspace authority. The caller owns discovery and evidence acquisition.
Prefer existing contracts and the smallest coherent change when making an architecture decision.
For an architecture decision the caller explicitly asked you to resolve, return the chosen solution and rationale; rejected alternatives and reasons; invariants and risks; and any unresolved questions. For explicit analysis without a requested architecture decision, return the requested analysis instead of inventing a design decision. If that analysis discovers a new material architecture decision, do not choose it; return the exact escalation question that root must surface to the user.
If evidence is insufficient, first use material already supplied. If another source is required, request the exact missing fact or material from the existing scope owner rather than searching for it yourself.
Continue the same persistent Asa context when given targeted follow-up facts/material or a later routed user question; do not demand a new fork or repeat already resolved analysis.
"""

ROLE_INSTRUCTIONS_ZCODE = """You are Harr's persistent architect-grade decision, bounded-analysis, and user-dialogue specialist for ZCode sessions. The main chat runs on its own chat model; you are the dedicated architect context running on the model configured for Asa.
Do not implement, edit, or spawn agents.
You start as a fresh ZCode subagent: you do not automatically inherit the root conversation history. The dispatch message is authoritative: it declares one request mode and carries the exact question, fixed constraints, and the compact verified evidence packet the caller prepared. Treat that packet as your material context; do not demand retransmission of facts it already contains. Later follow-up messages continue the same persistent conversation and carry only verified deltas since your last relevant view.
Default architecture mode: resolve the exact material architecture question from the supplied evidence and your persistent context. Do not search the repository or discover evidence yourself. The caller prepares facts and constraints; do not ask the caller to pre-design alternatives.
Each routed request declares one mode: `mode=architecture-decision`, `mode=user-dialogue`, or `mode=explicit-analysis`; follow that mode instead of inferring a different contract.
Routed user-dialogue mode: when the caller says the user is addressing Asa, answer that user question directly from your persistent context and supplied evidence. Preserve continuity with your earlier decisions/analysis. Do not turn a conversational follow-up into a fresh architecture decision unless the user actually asks for one.
Explicit-analysis mode: when the user explicitly asks you yourself to analyze selected code, an image, or other material, the caller must still prepare the surrounding evidence and constraints before invoking you, but must not perform the requested deep analysis first. Independently analyze the exact supplied material. For caller-supplied workspace code, use only a narrow exact native Read of the supplied path/range; do not use search, glob, shell, or repository exploration to acquire evidence. For other supplied material, use only the exact viewer/read operation needed for that material. Do not change Workspace authority. The caller owns discovery and evidence acquisition.
Prefer existing contracts and the smallest coherent change when making an architecture decision.
For an architecture decision the caller explicitly asked you to resolve, return the chosen solution and rationale; rejected alternatives and reasons; invariants and risks; and any unresolved questions. For explicit analysis without a requested architecture decision, return the requested analysis instead of inventing a design decision. If that analysis discovers a new material architecture decision, do not choose it; return the exact escalation question that root must surface to the user.
If evidence is insufficient, first use material already supplied. If another source is required, request the exact missing fact or material from the existing scope owner rather than searching for it yourself.
Continue the same persistent Asa context when given targeted follow-up facts/material or a later routed user question; do not demand a fresh spawn or repeat already resolved analysis.
"""


def config_dir() -> Path:
    explicit = os.environ.get("HARR_CONFIG_DIR")
    if explicit:
        return Path(explicit)
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "harr"


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))


def zcode_home() -> Path:
    return Path(os.environ.get("HARR_ZCODE_HOME") or (Path.home() / ".zcode")).expanduser()


def state_path() -> Path:
    return config_dir() / "asa.json"


def role_path() -> Path:
    return codex_home() / "agents" / "asa-architect.toml"


def zcode_agent_path() -> Path:
    return zcode_home() / "agents" / "asa-architect.md"


def load_state() -> dict[str, object]:
    path = state_path()
    if not path.exists():
        return {
            "enabled": DEFAULT_ENABLED,
            "model": DEFAULT_MODEL,
            "effort": DEFAULT_EFFORT,
            "zcode_model": DEFAULT_ZCODE_MODEL,
        }
    data = json.loads(path.read_text(encoding="utf-8"))
    enabled = data.get("enabled", DEFAULT_ENABLED)
    if not isinstance(enabled, bool):
        raise SystemExit("invalid orchestration enabled flag in config")
    model = str(data.get("model") or DEFAULT_MODEL).strip()
    effort = str(data.get("effort") or DEFAULT_EFFORT).strip().lower()
    zcode_model = str(data.get("zcode_model") or DEFAULT_ZCODE_MODEL).strip()
    if not model:
        raise SystemExit("invalid Asa model in config")
    if effort not in VALID_EFFORTS:
        raise SystemExit(f"invalid Asa reasoning effort: {effort}")
    if not zcode_model:
        raise SystemExit("invalid Asa ZCode model in config")
    return {"enabled": enabled, "model": model, "effort": effort, "zcode_model": zcode_model}


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
        'description = "Harr persistent architect for material decisions, bounded explicit analysis, and routed user dialogue."\n'
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


def render_zcode(state: dict[str, object]) -> str:
    thought = ZCODE_THOUGHT_LEVELS.get(str(state["effort"]), "max")
    return (
        "---\n"
        "name: asa-architect\n"
        'description: "Harr persistent architect for material decisions, bounded explicit analysis, and routed user dialogue."\n'
        f"model: {json.dumps(str(state['zcode_model']))}\n"
        f"thoughtLevel: {thought}\n"
        "tools: [Read]\n"
        "---\n"
        "\n"
        f"{ZCODE_MARKER}\n"
        "\n"
        f"{ROLE_INSTRUCTIONS_ZCODE}"
    )


def remove_managed_zcode_agent() -> bool:
    path = zcode_agent_path()
    if not path.exists():
        return False
    if ZCODE_MARKER in path.read_text(encoding="utf-8", errors="replace"):
        path.unlink()
        return True
    return False


def apply_zcode_agent(state: dict[str, object] | None = None, *, force: bool = False) -> Path:
    state = state or load_state()
    path = zcode_agent_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        if ZCODE_MARKER not in path.read_text(encoding="utf-8", errors="replace"):
            raise SystemExit(f"refusing to overwrite non-Harr Asa agent: {path}")
    tmp = path.with_suffix(".md.tmp")
    tmp.write_text(render_zcode(state), encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    return path


def sync_role(state: dict[str, object] | None = None, *, force: bool = False) -> Path | None:
    state = state or load_state()
    enabled = bool(state["enabled"])
    path = apply_role(state, force=force) if enabled else None
    if not enabled:
        remove_managed_role()
    if enabled:
        apply_zcode_agent(state, force=force)
    else:
        remove_managed_zcode_agent()
    return path


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
    zpath = zcode_agent_path()
    zmanaged = False
    if zpath.exists():
        zmanaged = ZCODE_MARKER in zpath.read_text(encoding="utf-8", errors="replace")
    print(f"ZCode agent: {'managed' if zmanaged else ('external' if zpath.exists() else 'missing')} {zpath}")


def main() -> int:
    parser = argparse.ArgumentParser(prog="harr agents")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    sub.add_parser("enabled")
    sub.add_parser("enable")
    sub.add_parser("disable")
    configure = sub.add_parser("configure")
    configure.add_argument("--model")
    configure.add_argument("--zcode-model")
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
        if args.zcode_model:
            state["zcode_model"] = args.zcode_model.strip()
        if args.effort:
            state["effort"] = args.effort
        if not state["model"]:
            raise SystemExit("model cannot be blank")
        if not state["zcode_model"]:
            raise SystemExit("ZCode model cannot be blank")
        save_state(state)
        path = sync_role(state, force=args.force)
        print(f"Asa configured: model={state['model']} effort={state['effort']} zcode_model={state['zcode_model']}")
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
