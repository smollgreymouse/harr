#!/usr/bin/env python3
"""Opt-in instructions survive zero/one/many instances on every host surface."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
ASSETS = ROOT / "common/mcp/assets.py"
CATALOG = ROOT / "common/mcp/registry.json"
POLICY = ROOT / "common/policy/tool-routing.template.md"
HARR_SKILL = ROOT / "common/skills/harr"
EIN_SKILL = ROOT / "common/skills/einherjar-worker/SKILL.md"
ADAPTERS = ("gigacode", "opencode", "codex", "custom")
HOST_SURFACES = ("codex", "opencode", "windows", "macos", "linux")


def server(name):
    return {
        "name": name,
        "label": name,
        "description": f"Named Ein {name} worker. Use only after direct user instruction.",
        "required": False,
        "transport": "stdio",
        "lifecycle": "on-demand",
        "ein_instance": name,
        "runtime": {"kind": "bundled-python", "script": "einherjar_server.py", "version": "0.1.0", "args": []},
        "skill_reference": "einherjar.md",
    }


def render(tmp, registry, platform):
    root = tmp / platform
    root.mkdir()
    registry_path = root / "registry.json"
    registry_path.write_text(json.dumps({"schema": 1, "servers": registry}))
    policy = root / "AGENTS.md"
    subprocess.run([
        PYTHON, str(ASSETS), "filter-text", "--catalog", str(CATALOG),
        "--registry", str(registry_path), "--input", str(POLICY),
        "--output", str(policy),
    ], check=True)
    skill = root / "skill"
    subprocess.run([
        PYTHON, str(ASSETS), "filter-skill", "--catalog", str(CATALOG),
        "--registry", str(registry_path), "--source", str(HARR_SKILL),
        "--output", str(skill),
    ], check=True)
    return policy.read_text(), (skill / "SKILL.md").read_text(), skill


with tempfile.TemporaryDirectory(prefix="harr-ein-policy-matrix-") as tmp_raw:
    tmp = Path(tmp_raw)
    cases = [("none", [])]
    cases += [(f"sole-{adapter}", [server(f"only-{adapter}")]) for adapter in ADAPTERS]
    cases += [("multiple-mixed", [server("gigacode"), server("opencode"), server("codex"), server("custom")])]
    for platform in HOST_SURFACES:
        for case, registry in cases:
            policy, harr_skill, skill_dir = render(tmp, registry, f"{platform}-{case}")
            for instructions in (policy, harr_skill):
                assert "direct user instruction to delegate" in instructions, (platform, case)
                assert "sole" in instructions and "not authorization" in instructions, (platform, case)
                assert "Never select an executor" in instructions, (platform, case)
            available = sorted(f"{item['name']}::ein" for item in registry)
            if available:
                assert all(tool in policy and tool in harr_skill for tool in available), (platform, case)
                assert "backend" not in policy.lower().split("available ein tools:", 1)[-1]
                assert "gigacode-executor" not in harr_skill
                assert (skill_dir / "references/einherjar.md").exists()
            else:
                assert "Available Ein tools:" not in policy
                assert "Available Ein tools:" not in policy and "Available MCP tools:" not in harr_skill
                assert not (skill_dir / "references/einherjar.md").exists()
            assert "gigacode::gigacode" not in policy + harr_skill
            shared = EIN_SKILL.read_text()
            assert "directly instructs executor delegation" in shared
            assert "DONE" in shared and "proof" in shared
            assert "gigacode-executor" not in shared

print(f"Ein instruction matrix: PASS ({len(HOST_SURFACES)} host surfaces x {len(cases)} instance/backend cases)")
