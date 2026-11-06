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
assert 'asa-architect' in skill
assert 'fork_turns: "all"' in skill
assert 'fork_turns: "none"' not in skill
assert "Make the decision evidence-ready" in skill
assert "normal Harr Workspace/tool-routing policy" in skill
assert "registered through the normal Harr Workspace flow" in skill
assert "do not create a second packet" in skill
assert "Worker's compact evidence handoff" in skill
assert "Root must not independently reread" in skill
assert "SAME Worker for delegated scope" in skill
assert "concise fact anchors" in skill
assert "does not inherit the Worker's private history" in skill
assert "Explicit user-directed analysis" in skill
assert "manual override" in skill
assert "does not require the analysis step itself to be an architecture decision" in skill
assert "exact read/view operation" in skill
assert "must not broaden the task into repository discovery or search" in skill
assert "returns the analysis the user requested" in skill
assert "exact question to resolve" in skill
assert "competing alternatives or constraints" in skill
assert "chosen solution and rationale" in skill
assert "rejected alternatives" in skill
assert "invariants and risks" in skill
assert "unresolved questions" in skill
assert "existing implementation owner" in skill
assert "SAME owner" in skill
assert "SAME architect" in skill
assert "reuse its existing" in skill
assert "Do not spawn a second Asa for the same decision." in skill
assert "followup_task" in skill
assert "do not re-fork the parent history" in skill.lower()
assert "Do not compact the parent conversation" in skill
assert "Prompt-cache reuse is opportunistic, not guaranteed." in skill
assert "independent new architecture question" in skill
assert "gpt-6.1-sol" not in skill
assert "xhigh" not in skill.lower()

host = HOST.read_text(encoding="utf-8")
assert "normal Harr Workspace/tool-routing policy" in host
assert "full inherited history" in host
assert "do not create a second packet" in host
assert "compact handoff" in host
assert "explicitly asks Asa herself to analyze" in host
assert "locates/identifies the exact material" in host
assert "without broadening into repository discovery" in host
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
    assert "full-history architecture decisions" in parsed["description"]

    instructions = parsed["developer_instructions"]
    for needle in (
        "architect-grade decision and bounded-analysis specialist",
        "Do not implement, edit, or spawn agents",
        "Default architecture mode",
        "do not demand a duplicate packet",
        "Worker's compact evidence handoff",
        "Explicit-analysis mode",
        "exact read/view operation",
        "caller owns discovery",
        "instead of inventing a design decision",
        "request the exact missing fact or material",
        "targeted follow-up facts/material",
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
