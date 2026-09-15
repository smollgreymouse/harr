#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
import stat
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "common" / "executor" / "codex_cli.py"
spec = importlib.util.spec_from_file_location("harr_codex_cli", MODULE)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def make_fake(path: Path) -> None:
    path.write_text(
        r'''#!/usr/bin/env python3
import json, os, pathlib, sys
args = sys.argv[1:]
if args == ["--version"]:
    print("codex-cli 9.9.9")
    raise SystemExit(0)
last = pathlib.Path(args[args.index("--output-last-message") + 1])
model = args[args.index("--model") + 1]
assert model == "gpt-5.6-luna"
assert args[args.index("--sandbox") + 1] == "workspace-write"
assert "agents.enabled=false" in args
assert "features.multi_agent=false" in args
assert "features.multi_agent_v2.enabled=false" in args
assert "sandbox_workspace_write.network_access=false" in args
assert 'web_search="disabled"' in args
assert os.environ.get("HARR_EXECUTOR_CHILD") == "1"
prompt = sys.stdin.read()
resume = "resume" in args
session = args[args.index("resume") + 1] if resume else "0199-test-session"
print(json.dumps({"type": "thread.started", "thread_id": session}))
if not resume:
    assert "executor, not a planner" in prompt
    packet = {
        "protocol": "harr.executor.v1",
        "state": "BLOCKED",
        "current_step": "B002",
        "completed_steps": ["B001"],
        "summary": "blocked on missing decision",
        "changed_files": ["src/a.cpp"],
        "validation": [{"check": "unit", "status": "NOT_RUN", "detail": "blocked first"}],
        "blocker": {
            "class": "UNSPECIFIED_DESIGN_DECISION",
            "step": "B002",
            "fact": "two APIs are possible",
            "decision_needed": "choose API",
            "evidence": ["src/a.cpp:10"],
        },
    }
else:
    assert "planner resolution delta" in prompt.lower()
    packet = {
        "protocol": "harr.executor.v1",
        "state": "DONE",
        "current_step": None,
        "completed_steps": ["B001", "B002"],
        "summary": "done",
        "changed_files": ["src/a.cpp"],
        "validation": [{"check": "unit", "status": "PASS", "detail": "ok"}],
        "blocker": None,
    }
last.write_text(json.dumps(packet), encoding="utf-8")
print(json.dumps({"type": "turn.completed", "usage": {"input_tokens": 120, "cached_input_tokens": 20, "cache_write_input_tokens": 0, "output_tokens": 30, "reasoning_output_tokens": 7}}))
''',
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


with tempfile.TemporaryDirectory() as tmp_raw:
    tmp = Path(tmp_raw)
    repo = tmp / "repo"
    repo.mkdir()
    fake = tmp / "codex"
    make_fake(fake)
    old_path = os.environ.get("PATH", "")
    os.environ["PATH"] = f"{tmp}{os.pathsep}{old_path}"
    try:
        adapter = mod.CodexCliAdapter(command="codex", model="gpt-5.6-luna", reasoning_effort="low")
        probe = adapter.probe()
        assert probe["available"] is True
        assert "9.9.9" in probe["version"]
        first = adapter.start(repo_root=repo, execution_contract="# HARR EXECUTOR CONTRACT v1\n## Step B001\n...")
        assert first.session_id == "0199-test-session"
        assert first.packet["state"] == "BLOCKED"
        assert first.packet["blocker"]["class"] == "UNSPECIFIED_DESIGN_DECISION"
        assert first.usage["input_tokens"] == 120
        assert first.usage["reasoning_output_tokens"] == 7
        second = adapter.resume(repo_root=repo, session_id=first.session_id, resolution_delta="# HARR PLANNER RESOLUTION v1\nDecision: use API A")
        assert second.session_id == first.session_id
        assert second.packet["state"] == "DONE"
        assert second.packet["validation"][0]["status"] == "PASS"
    finally:
        os.environ["PATH"] = old_path

print("codex CLI executor adapter: PASS")
