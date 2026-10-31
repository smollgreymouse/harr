#!/usr/bin/env python3
"""Ein discoverability stays generated while action semantics remain in the MCP schema."""
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
EIN_SKILL = ROOT / "common/skills/ein/SKILL.md"
EIN_META = ROOT / "common/skills/ein/agents/openai.yaml"
SCHEMA = ROOT / "common/mcp/ein_tool_schema.json"
CODEX_ENV = ROOT / "common/hosts/codex.env"
OPENCODE_ENV = ROOT / "common/hosts/opencode.env"
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


shared = EIN_SKILL.read_text(encoding="utf-8")
assert "session owns its delegated scope" in shared
assert "SAME Ein session" in shared
assert "Action arguments" in shared and "MCP tool" in shared
assert "plan_path" not in shared
assert "einherjar-worker" not in shared
meta = EIN_META.read_text(encoding="utf-8")
assert "allow_implicit_invocation: false" in meta

schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
assert "explicitly instructs" in schema["description"]
actions = schema["inputSchema"]["properties"]["action"]["enum"]
assert actions == ["start", "resume", "status", "messages", "wait", "cancel"]
assert "No automatic wait/poll" in schema["inputSchema"]["properties"]["action"]["description"]

with tempfile.TemporaryDirectory(prefix="harr-ein-policy-matrix-") as tmp_raw:
    tmp = Path(tmp_raw)
    cases = [("none", [])]
    cases += [(f"sole-{adapter}", [server(f"only-{adapter}")]) for adapter in ADAPTERS]
    cases += [("multiple-mixed", [server("gigacode"), server("opencode"), server("codex"), server("custom")])]
    for platform in HOST_SURFACES:
        for case, registry in cases:
            policy, harr_skill, skill_dir = render(tmp, registry, f"{platform}-{case}")
            available = sorted(f"{item['name']}::ein" for item in registry)
            if available:
                assert "$ein" in policy and "$ein" in harr_skill, (platform, case)
                assert all(tool in policy and tool in harr_skill for tool in available), (platform, case)
                assert "start|resume|status|messages|wait|cancel" not in policy
                assert "not authorization" not in policy
                assert (skill_dir / "references/einherjar.md").exists()
            else:
                assert "Named Ein workflow:" not in policy
                assert "Available Ein tools:" not in policy
                assert not (skill_dir / "references/einherjar.md").exists()
            assert "gigacode-executor" not in policy + harr_skill

codex_policy = CODEX_ENV.read_text()
opencode_policy = OPENCODE_ENV.read_text()
ein_reference = (HARR_SKILL / "references/einherjar.md").read_text()
assert "Codex Desktop Ein app routing" in codex_policy
assert "OpenCode and other hosts keep Harr-managed MCP calls behind LeanCTX" in codex_policy
assert "Codex Desktop Ein app routing" not in opencode_policy
assert "use it for user-authorized `start` and `resume` calls" in ein_reference
assert "LeanCTX gateway for status, messages, wait, cancel" in ein_reference

print(f"Ein instruction matrix: PASS ({len(HOST_SURFACES)} host surfaces x {len(cases)} instance/backend cases)")
