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
HELPER = ROOT / "common/agents/asa_config.py"

skill = SKILL.read_text(encoding="utf-8")
assert "material architecture decision" in skill
assert "unresolved material architecture decision" in skill
assert "already fixed the decision" in skill
assert "merely because work is large" in skill
assert 'asa-architect' in skill
assert 'fork_turns: "none"' in skill
assert "SAME architect" in skill
assert "gpt-6.1-sol" not in skill
assert "xhigh" not in skill.lower()

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

    instructions = parsed["developer_instructions"]
    for needle in ("Do not implement", "Do not implement, edit, spawn agents", "exact missing facts"):
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
