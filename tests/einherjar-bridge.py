#!/usr/bin/env python3
"""Deterministic Einherjar bridge/adapter conformance tests. No real agent calls."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = ROOT / "common" / "mcp" / "einherjar_server.py"

tmp = tempfile.TemporaryDirectory(prefix="einherjar-test-")
sandbox = Path(tmp.name)
config_dir = sandbox / "config" / "harr"
config_dir.mkdir(parents=True)
os.environ["HARR_CONFIG_DIR"] = str(config_dir)
os.environ["XDG_CACHE_HOME"] = str(sandbox / "cache")

spec = importlib.util.spec_from_file_location("harr_einherjar_server", SERVER_PATH)
assert spec and spec.loader
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)

from common.executor.backends import (
    BackendResumeRequest,
    BackendStartRequest,
    load_einherjar_config,
    text_candidates_from_jsonl,
)
from common.executor.adapters.gigacode import GigaCodeAdapter
from common.executor.adapters.opencode import OpenCodeAdapter
from common.executor.adapters.codex import CodexAdapter
from common.executor.protocol import parse_worker_handoff

# Tool contract.
assert server.SERVER_NAME == "einherjar"
assert server.TOOLS[0]["name"] == "worker"
assert server.TOOLS[0]["inputSchema"]["properties"]["action"]["enum"] == [
    "start", "resume", "status", "messages", "wait", "cancel", "backends"
]

server_source = SERVER_PATH.read_text(encoding="utf-8")
assert "shell=True" not in server_source
for vendor in ("gigacode", "opencode", "codex"):
    assert f'backend == "{vendor}"' not in server_source
if sys.platform.startswith("linux"):
    owner = {"pid": os.getpid(), "start_ticks": server._owner_identity(os.getpid())}
    assert owner["start_ticks"] is not None and server._owner_alive(owner)

# Shared handoff validation is backend-neutral.
done = {
    "status": "DONE",
    "summary": "done",
    "changed": [{"path": "x", "what": "changed"}],
    "verified": [{"criterion": "C1", "check": "fake", "result": "PASS", "evidence": "exit=0"}],
    "self_review": {"criteria_complete": True, "diff_scope_clean": True, "unverified": []},
    "escalation": None,
    "blockers": [],
}
parsed, bad = parse_worker_handoff(json.dumps(done), 0, "")
assert not bad and parsed["status"] == "DONE"
failed, bad = parse_worker_handoff("", 2, "boom")
assert bad and failed["status"] == "FAILED"
assert "GigaCode" not in json.dumps(failed)

# Built-in command construction matches the installed CLI help semantics.
workspace = ROOT
start = BackendStartRequest("task", workspace, harr_session_id="550e8400-e29b-41d4-a716-446655440000")
resume = BackendResumeRequest("delta", workspace, "vendor-session")

with patch("common.executor.adapters.gigacode.shutil.which", return_value="/bin/gigacode"):
    argv = GigaCodeAdapter().start_command(start)
    assert argv[:4] == ["/bin/gigacode", "--chat-recording", "--session-id", start.harr_session_id]
    assert "--approval-mode" in argv and "auto-edit" in argv
    rargv = GigaCodeAdapter().resume_command(resume)
    assert rargv[:4] == ["/bin/gigacode", "--chat-recording", "--resume", "vendor-session"]

with patch("common.executor.adapters.opencode.shutil.which", return_value="/bin/opencode"):
    argv = OpenCodeAdapter().start_command(start)
    assert argv[:3] == ["/bin/opencode", "run", "--format"]
    assert "--pure" in argv and "--auto" in argv and "--dir" in argv
    rargv = OpenCodeAdapter().resume_command(resume)
    assert rargv[1] == "run"
    assert "resume" not in rargv[1:2]
    assert "--session" in rargv and "vendor-session" in rargv

with patch("common.executor.adapters.codex.shutil.which", return_value="/bin/codex"):
    adapter = CodexAdapter()
    argv = adapter.start_command(start)
    assert argv[:5] == ["/bin/codex", "--ask-for-approval", "never", "--sandbox", "workspace-write"]
    assert "exec" in argv and "--json" in argv and argv[-1] == "-"
    assert adapter.stdin_text("abc") == "abc"
    rargv = adapter.resume_command(resume)
    assert rargv[rargv.index("exec") + 1] == "resume"
    assert "vendor-session" in rargv

# Structured vendor-session parsing.
assert CodexAdapter().extract_vendor_session_id(
    '{"type":"thread.started","thread_id":"thread-42"}\n', ""
) == "thread-42"
assert OpenCodeAdapter().extract_vendor_session_id(
    '{"event":{"sessionID":"ses-42"}}\n', ""
) == "ses-42"

visible = text_candidates_from_jsonl("\n".join([
    json.dumps({"role": "user", "text": "do not echo user prompt"}),
    json.dumps({"type": "reasoning", "text": "private reasoning"}),
    json.dumps({"type": "tool_result", "text": "tool noise"}),
    json.dumps({"role": "assistant", "text": "visible progress"}),
]))
assert visible == ["visible progress"]

# Config validation.
assert load_einherjar_config(config_dir / "missing.json")["default_backend"] == "gigacode"

bad_shell = config_dir / "bad-shell.json"
bad_shell.write_text(json.dumps({
    "schema": 1, "default_backend": "x",
    "backends": {"x": {"adapter": "command-template", "start": "x --prompt {prompt}"}},
}))
try:
    load_einherjar_config(bad_shell)
    raise AssertionError("shell string accepted")
except ValueError as exc:
    assert "argv array" in str(exc)

bad_placeholder = config_dir / "bad-placeholder.json"
bad_placeholder.write_text(json.dumps({
    "schema": 1, "default_backend": "x",
    "backends": {"x": {"adapter": "command-template", "start": ["x", "{mystery}"]}},
}))
try:
    load_einherjar_config(bad_placeholder)
    raise AssertionError("unknown placeholder accepted")
except ValueError as exc:
    assert "unknown placeholders" in str(exc)

bad_transport = config_dir / "bad-transport.json"
bad_transport.write_text(json.dumps({
    "schema": 1, "default_backend": "x",
    "backends": {"x": {"adapter": "command-template", "start": ["x", "run"]}},
}))
try:
    load_einherjar_config(bad_transport)
    raise AssertionError("missing prompt transport accepted")
except ValueError as exc:
    assert "transport the prompt" in str(exc)

bad_default = config_dir / "bad-default.json"
bad_default.write_text(json.dumps({
    "schema": 1, "default_backend": "missing", "backends": {}
}))
try:
    load_einherjar_config(bad_default)
    raise AssertionError("unknown default backend accepted")
except ValueError as exc:
    assert "default_backend is not configured" in str(exc)

bad_resume = config_dir / "bad-resume.json"
bad_resume.write_text(json.dumps({
    "schema": 1, "default_backend": "x",
    "backends": {"x": {
        "adapter": "command-template",
        "start": ["x", "{prompt}"],
        "resume": ["x", "resume", "{session_id}", "{prompt}"]
    }},
}))
try:
    load_einherjar_config(bad_resume)
    raise AssertionError("resumable backend without session-id source accepted")
except ValueError as exc:
    assert "extract a session id or assign one" in str(exc)

bad_secret = config_dir / "bad-secret.json"
bad_secret.write_text(json.dumps({
    "schema": 1, "default_backend": "x",
    "backends": {"x": {"adapter": "command-template", "start": ["x", "{prompt}"], "api_key": "secret"}},
}))
try:
    load_einherjar_config(bad_secret)
    raise AssertionError("unsupported secret-bearing field accepted")
except ValueError as exc:
    assert "unsupported fields" in str(exc)

# Fake CLI: start escalates and returns vendor session; resume requires the same
# vendor session and finishes; SLEEP mode permits process-tree cancellation.
fake = sandbox / "fake_agent.py"
log = sandbox / "fake.log"
fake.write_text(r'''#!/usr/bin/env python3
import json, pathlib, sys, time
log = pathlib.Path(sys.argv[1])
mode = sys.argv[2]
args = sys.argv[3:]
with log.open("a", encoding="utf-8") as f:
    f.write(json.dumps({"mode": mode, "args": args}) + "\n")
prompt = args[-1] if args else ""
if "SLEEP" in prompt:
    print(json.dumps({"session_id": "vendor-123", "text": "sleeping"}), flush=True)
    time.sleep(30)
    sys.exit(0)
if mode == "start":
    handoff = {
        "status": "ESCALATE",
        "summary": "need decision",
        "changed": [],
        "verified": [],
        "self_review": {"criteria_complete": False, "diff_scope_clean": True, "unverified": ["C1"]},
        "escalation": {
            "kind": "ambiguous_design",
            "expected": "fixed choice",
            "observed": "two choices",
            "evidence": [{"path": "x", "symbol": None, "lines": None, "fact": "fixture", "snippet": None}],
            "impact": "planner decision required",
            "decision_needed": "choose A or B",
            "options": [{"option": "A", "consequence": "A"}, {"option": "B", "consequence": "B"}],
        },
        "blockers": [],
    }
else:
    assert args[0] == "vendor-123", args
    handoff = {
        "status": "DONE",
        "summary": "finished",
        "changed": [{"path": "x", "what": "fixture"}],
        "verified": [{"criterion": "C1", "check": "fake", "result": "PASS", "evidence": "exit=0"}],
        "self_review": {"criteria_complete": True, "diff_scope_clean": True, "unverified": []},
        "escalation": None,
        "blockers": [],
    }
print(json.dumps({"session_id": "vendor-123", "text": "working"}), flush=True)
print(json.dumps({"text": json.dumps(handoff)}), flush=True)
''', encoding="utf-8")
fake.chmod(0o755)

cfg = {
    "schema": 1,
    "default_backend": "fake",
    "backends": {
        "fake": {
            "adapter": "command-template",
            "start": [sys.executable, str(fake), str(log), "start", "{prompt}"],
            "resume": [sys.executable, str(fake), str(log), "resume", "{session_id}", "{prompt}"],
            "session_id": {"source": "stdout-json", "keys": ["session_id"]},
            "events": {"mode": "jsonl"},
        }
    },
}
(config_dir / "einherjar.json").write_text(json.dumps(cfg), encoding="utf-8")

# Safe backend discovery exposes no resolved executable path.
backend_payload = json.loads(server.backends_tool()["content"][0]["text"])
fake_row = next(x for x in backend_payload["backends"] if x["name"] == "fake")
assert fake_row["found"] is True
assert fake_row["resumable"] is True
assert fake_row["progress_messages"] is True
assert "executable" not in fake_row

started = json.loads(server.start_tool({"action": "start", "prompt": "fixture task"})["content"][0]["text"])
sid = started["session_id"]
deadline = time.time() + 5
while True:
    state = json.loads(server.status_tool({"session_id": sid})["content"][0]["text"])
    if state["status"] != "RUNNING":
        break
    assert time.time() < deadline
    time.sleep(0.05)
assert state["status"] == "ESCALATE", state
internal = server._load_state(sid)
assert internal and internal["backend"] == "fake"
assert internal["vendor_session_id"] == "vendor-123"

progress = json.loads(server.messages_tool({"session_id": sid})["content"][0]["text"])
assert any(x["text"] == "working" for x in progress["messages"])
assert "vendor-123" not in json.dumps(state)  # public status never exposes vendor id

resumed = json.loads(server.resume_tool({"session_id": sid, "prompt": "choose A"})["content"][0]["text"])
deadline = time.time() + 5
while True:
    state = json.loads(server.status_tool({"session_id": sid})["content"][0]["text"])
    if state["status"] != "RUNNING":
        break
    assert time.time() < deadline
    time.sleep(0.05)
assert state["status"] == "DONE", state
rows = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]
assert rows[0]["mode"] == "start"
assert "You are an implementation worker" in rows[0]["args"][-1]
assert rows[1]["mode"] == "resume"
assert rows[1]["args"][0] == "vendor-123"
assert "You are an implementation worker" in rows[1]["args"][-1]

# Cancellation of a detached sleeping CLI.
sleeping = json.loads(server.start_tool({"action": "start", "prompt": "SLEEP fixture"})["content"][0]["text"])
sleep_sid = sleeping["session_id"]
deadline = time.time() + 5
while True:
    st = server._load_state(sleep_sid) or {}
    if st.get("phase") == "running":
        break
    assert time.time() < deadline
    time.sleep(0.05)
cancelled = json.loads(server.cancel_tool({"session_id": sleep_sid})["content"][0]["text"])
assert cancelled["status"] == "CANCEL_REQUESTED"
deadline = time.time() + 7
while True:
    final = json.loads(server.status_tool({"session_id": sleep_sid})["content"][0]["text"])
    if final["status"] != "RUNNING":
        break
    assert time.time() < deadline
    time.sleep(0.05)
assert final["status"] == "FAILED"
assert "cancel" in final["summary"].lower()

print("Einherjar bridge/adapters: PASS")
