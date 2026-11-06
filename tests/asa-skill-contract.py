#!/usr/bin/env python3
"""Orchestration/Asa feature stays opt-in, reversible, and configurable."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "common/skills/asa/SKILL.md"
META = ROOT / "common/skills/asa/agents/openai.yaml"
HOST = ROOT / "common/hosts/codex.env"
HELPER = ROOT / "common/agents/asa_config.py"

skill = SKILL.read_text(encoding="utf-8")
assert "material architecture decision" in skill
assert "unresolved material architecture decision" in skill
assert "already fixed the decision" in skill
assert "merely because work is large" in skill
assert "one persistent architectural interlocutor" in skill
assert "automatic material-decision escalation" in skill
assert "explicit user dialogue/analysis" in skill
assert "Every Asa invocation, automatic or explicit, must be evidence-ready first." in skill
assert "normal Harr Workspace/tool-routing policy" in skill
assert "registered through the normal Harr Workspace flow" in skill
assert "must not invent, rank, compare, or choose architecture alternatives" in skill
assert "Worker's compact evidence handoff" in skill
assert "Root must not independently reread" in skill
assert "SAME Worker for narrowly missing facts" in skill
assert "does not inherit the Worker's private history" in skill
assert 'fork_turns: "all"' in skill
assert 'fork_turns: "none"' not in skill
assert "do not retransmit a second full root evidence packet" in skill
assert "do not assume she sees root turns that happened after the initial fork" in skill
assert "verified delta she has not already received" in skill
assert "new root-owned facts/material/constraints" in skill
assert 'task_name="asa"' in skill
assert 'agent_type="asa-architect"' in skill
assert 'followup_task(target="asa"' in skill
assert "normal cold-resume path for a persisted V2 child" in skill
assert "list_agents" in skill
assert "before spawning anything" in skill
assert "canonical target exists but cannot be resumed" in skill
assert "do not silently create a second Asa" in skill
assert "Wait for Asa's completion notification" in skill
assert "wait_agent" in skill
assert "never synthesize Asa's answer yourself" in skill
assert "exact question to resolve" in skill
assert "Include alternatives only when they were already supplied" in skill
assert "must not manufacture or evaluate alternatives before Asa" in skill
assert "chosen solution and rationale" in skill
assert "rejected alternatives" in skill
assert "invariants and risks" in skill
assert "unresolved questions" in skill
assert "existing implementation owner" in skill
assert "SAME owner" in skill
assert "Explicit invocation does not waive evidence preparation" in skill
assert "Evidence preparation may be a no-op" in skill
assert "root is a transparent router after evidence preparation" in skill
assert "Preserve the user's intent and relevant wording" in skill
assert "root must not answer for Asa" in skill
assert "Relay Asa's answer faithfully" in skill
assert "exact read/view operation" in skill
assert "must not broaden the task into repository discovery" in skill
assert "Discovery and evidence acquisition remain with the scope owner" in skill
assert "discovers a new material architecture decision" in skill
assert "exact escalation question for the user" in skill
assert "Root surfaces that question to the user" in skill
assert "Do not re-fork the parent history" in skill
assert "Prompt-cache reuse is opportunistic, not guaranteed." in skill
assert "gpt-6.1-sol" not in skill
assert "xhigh" not in skill.lower()

host = HOST.read_text(encoding="utf-8")
assert "normal Harr Workspace/tool-routing policy" in host
assert 'task_name="asa"' in host
assert 'agent_type="asa-architect"' in host
assert 'followup_task(target="asa")' in host
assert "one persistent architect child per root conversation" in host
assert "full inherited root history only at spawn time" in host
assert "verified new root-owned facts/material/constraints" in host
assert "compact handoff" in host
assert "absence from list_agents is not proof" in host
assert "wait for the Asa completion notification" in host
assert "transparently routes the user request to the SAME Asa" in host
assert "faithfully relays the Asa answer instead of answering for Asa" in host
assert "does not perform the requested deep analysis first" in host
assert "without broadening into repository discovery" in host
assert "root asks the user before continuing the SAME Asa" in host
assert "explicit project path" not in host

meta = META.read_text(encoding="utf-8")
assert "allow_implicit_invocation: true" in meta

with tempfile.TemporaryDirectory(prefix="harr-asa-contract-") as raw:
    tmp = Path(raw)
    env = os.environ.copy()
    env["HARR_CONFIG_DIR"] = str(tmp / "config")
    env["CODEX_HOME"] = str(tmp / "codex")

    def run(*args, check=True):
        return subprocess.run(
            [sys.executable, str(HELPER), *args],
            env=env, text=True, capture_output=True, check=check,
        )

    role = tmp / "codex/agents/asa-architect.toml"
    state_path = tmp / "config/asa.json"

    # Default is opt-out and sync must not install the role.
    status = run("status").stdout
    assert "Orchestration: disabled" in status
    assert run("enabled", check=False).returncode == 1
    run("sync")
    assert not role.exists()

    # Model/effort can be prepared while disabled without activating anything.
    run("configure", "--model", "gpt-6-luna", "--effort", "high")
    assert not role.exists()
    assert json.loads(state_path.read_text()) == {
        "enabled": False,
        "model": "gpt-6-luna",
        "effort": "high",
    }

    # Explicit enable + sync installs the configured role.
    run("enable")
    assert run("enabled", check=False).returncode == 0
    run("sync")
    parsed = tomllib.loads(role.read_text(encoding="utf-8"))
    assert role.read_text(encoding="utf-8").startswith("# harr-managed-agent-v1\n")
    assert parsed["name"] == "asa-architect"
    assert parsed["model"] == "gpt-6-luna"
    assert parsed["model_reasoning_effort"] == "high"
    assert parsed["skills"]["include_instructions"] is False
    assert "compact decision packets" not in parsed["description"]
    assert "persistent architect" in parsed["description"]
    assert "routed user dialogue" in parsed["description"]

    instructions = parsed["developer_instructions"]
    for needle in (
        "persistent architect-grade decision, bounded-analysis, and user-dialogue specialist",
        "Do not implement, edit, or spawn agents",
        "do not automatically receive later root turns",
        "authoritative deltas plus the current request",
        "Default architecture mode",
        "facts learned after your initial fork",
        "Worker's compact evidence handoff",
        "Routed user-dialogue mode",
        "answer that user question directly",
        "Preserve continuity with your earlier decisions/analysis",
        "Explicit-analysis mode",
        "caller must still prepare the surrounding evidence and constraints",
        "must not perform the requested deep analysis first",
        "narrow exact Harr/LeanCTX read",
        "do not use shell, search, glob, or repository exploration",
        "Do not change Workspace authority",
        "caller owns discovery and evidence acquisition",
        "instead of inventing a design decision",
        "do not choose it; return the exact escalation question",
        "request the exact missing fact or material",
        "same persistent Asa context",
        "later routed user question",
    ):
        assert needle in instructions

    # Non-Harr role remains fail-closed unless an owning caller explicitly forces takeover.
    role.write_text('name = "external"\n', encoding="utf-8")
    failed = run("sync", check=False)
    assert failed.returncode != 0
    assert "refusing to overwrite non-Harr Asa role" in failed.stderr + failed.stdout
    run("sync", "--force")
    assert role.read_text(encoding="utf-8").startswith("# harr-managed-agent-v1\n")

    # Explicit disable removes only the Harr-managed role and remains disabled after sync.
    run("disable")
    run("sync")
    assert not role.exists()
    status = run("status").stdout
    assert "Orchestration: disabled" in status
    assert "Asa model: gpt-6-luna" in status
    assert "Asa effort: high" in status
    assert run("enabled", check=False).returncode == 1

print("Orchestration/Asa opt-in contract: PASS")
