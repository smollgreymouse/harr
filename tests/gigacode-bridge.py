#!/usr/bin/env python3
"""Black-box structural tests for the GigaCode MCP bridge.

Tests schema, constants, validation, and helper functions in isolation.
Never spawns real subprocesses or touches real CACHE_ROOT.
"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = ROOT / "common" / "mcp" / "gigacode_server.py"

spec = importlib.util.spec_from_file_location("harr_gigacode_server", SERVER_PATH)
assert spec and spec.loader
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)

# -------------------------------------------------------------------
# 1. Version and constants
# -------------------------------------------------------------------
assert server.SERVER_VERSION == "1.10.0", f"got {server.SERVER_VERSION}"
assert server.DEFAULT_HARD_TIMEOUT_SEC == 0, f"got {server.DEFAULT_HARD_TIMEOUT_SEC}"
assert server.DEFAULT_STALL_TIMEOUT_SEC == 0, f"got {server.DEFAULT_STALL_TIMEOUT_SEC}"
assert server.DEFAULT_WAIT_TIMEOUT_SEC == 1500
assert server.MAX_WAIT_TIMEOUT_SEC == 1500
assert server.STARTUP_CONFIRM_TIMEOUT_SEC == 20.0

# -------------------------------------------------------------------
# 2. Tool schema
# -------------------------------------------------------------------
assert len(server.TOOLS) == 1
tool = server.TOOLS[0]
assert tool["name"] == "gigacode"
assert tool["inputSchema"]["properties"]["action"]["enum"] == ["start", "resume", "status", "messages", "wait", "cancel"]
assert tool["inputSchema"]["properties"]["after_revision"]["minimum"] == 0
assert tool["inputSchema"]["properties"]["message_limit"]["maximum"] == 50
assert tool["inputSchema"]["properties"]["wait_timeout_sec"]["maximum"] == 1500
assert tool["inputSchema"]["properties"]["timeout_sec"]["minimum"] == 0
assert "cancel" in tool["description"]
assert "unlimited" in tool["description"] or "0=unlimited" in tool["description"]

# -------------------------------------------------------------------
# 3. _validate_session_id
# -------------------------------------------------------------------
# Valid UUIDs
assert server._validate_session_id("550e8400-e29b-41d4-a716-446655440000") == "550e8400-e29b-41d4-a716-446655440000"
assert server._validate_session_id(str(server.uuid.uuid4())) is not None
# Rejects
assert server._validate_session_id(None) is None
assert server._validate_session_id("") is None
assert server._validate_session_id("../etc") is None
assert server._validate_session_id("a/b") is None
assert server._validate_session_id("C:\\windows") is None
assert server._validate_session_id("..") is None
assert server._validate_session_id("simple") is None
assert server._validate_session_id(123) is None
# Rejects UUID with trailing newline
assert server._validate_session_id("550e8400-e29b-41d4-a716-446655440000\n") is None

# -------------------------------------------------------------------
# 4. Runtime helpers
# -------------------------------------------------------------------
assert server._pid_alive(os.getpid()) is True
group_kwargs = server._new_process_group_kwargs()
if os.name == "nt":
    assert "creationflags" in group_kwargs
    assert "start_new_session" not in group_kwargs
else:
    assert group_kwargs == {"start_new_session": True}

# -------------------------------------------------------------------
# 5. Harr coupling invariants
# -------------------------------------------------------------------
source = SERVER_PATH.read_text(encoding="utf-8")
for forbidden in (
    "--allowed-tools",
    "mcp__lean-ctx__ctx_shell",
    "run_shell_command",
    "Use the allowed LeanCTX",
):
    assert forbidden not in source, f"forbidden string found: {forbidden}"
assert "The bridge does not prescribe or" in server.WORKER_CONTRACT
assert "internal tools, MCP servers, shell implementation, or editor" in server.WORKER_CONTRACT

# -------------------------------------------------------------------
# 6. tools/list
# -------------------------------------------------------------------
listed = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
assert listed is not None
assert [item["name"] for item in listed["result"]["tools"]] == ["gigacode"]

# -------------------------------------------------------------------
# 7. extract_json_object / parse_worker_handoff
# -------------------------------------------------------------------
sample = """worker note
```json
{"status":"DONE","summary":"ok","changed":[{"path":"x.cpp","what":"implemented"}],"verified":[{"criterion":"C1","check":"unit","result":"PASS","evidence":"exit=0; 1 test passed"}],"self_review":{"criteria_complete":true,"diff_scope_clean":true,"unverified":[]},"escalation":null,"blockers":[]}
```
"""
handoff = server.extract_json_object(sample)
assert handoff is not None
assert handoff["status"] == "DONE"

parsed, is_error = server.parse_worker_handoff(json.dumps(handoff), 0, "")
assert parsed["summary"] == "ok"
assert parsed["self_review"]["criteria_complete"] is True
assert is_error is False

invalid_done = {
    "status": "DONE",
    "summary": "claims success without acceptance evidence",
    "changed": [],
    "verified": [],
    "escalation": None,
    "blockers": [],
}
invalid_parsed, invalid_is_error = server.parse_worker_handoff(json.dumps(invalid_done), 0, "")
assert invalid_is_error is True
assert invalid_parsed["status"] == "FAILED"
assert "self-verification" in invalid_parsed["summary"]

# -------------------------------------------------------------------
# 8. Cancel control helper round-trip (sandboxed CACHE_ROOT)
# -------------------------------------------------------------------
_original_cache_root = server.CACHE_ROOT
_sandbox = tempfile.TemporaryDirectory(prefix="gigacode-bridge-")
server.CACHE_ROOT = Path(_sandbox.name) / "cache"
server.CACHE_ROOT.mkdir(parents=True, exist_ok=True)
fake_sid = str(server.uuid.uuid4())
fake_jid = server.uuid.uuid4().hex[:12]
assert server._check_cancel_request(fake_sid, fake_jid) is False

# Public RUNNING status is deliberately compact: never leak executor event history
# or bridge-internal log/process metadata into the expensive parent context.
server._write_state(fake_sid, {
    "phase": "running",
    "session_id": fake_sid,
    "job_id": fake_jid,
    "pid": os.getpid(),
    "elapsed_sec": 42.0,
    "timeout_sec": 0,
})
running_status = server.status_tool({"session_id": fake_sid})
running_data = json.loads(running_status["content"][0]["text"])
assert running_data["status"] == "RUNNING"
assert running_data["runtime"]["elapsed_sec"] == 42.0
assert "last_events" not in running_data
assert "polling" not in running_data
assert "runtime_log" not in running_data["runtime"]
assert "chat" not in running_data["runtime"]
assert "worker_pid" not in running_data["runtime"]
assert "gigacode_pid" not in running_data["runtime"]

# wait is a bridge-local blocking primitive: terminal state returns immediately,
# while a bounded timeout returns RUNNING without cancelling the detached worker.
terminal_payload = {
    "session_id": fake_sid,
    "status": "DONE",
    "summary": "terminal",
}
with patch.object(server, "status_tool", return_value=server.text_result(terminal_payload)):
    waited = server.wait_tool({"session_id": fake_sid, "wait_timeout_sec": 10})
    waited_data = json.loads(waited["content"][0]["text"])
assert waited_data["status"] == "DONE"

running_payload = {
    "session_id": fake_sid,
    "status": "RUNNING",
    "summary": "still running",
    "runtime": {"phase": "running"},
}
with patch.object(server, "status_tool", return_value=server.text_result(running_payload)), \
     patch.object(server.time, "monotonic", side_effect=[0.0, 0.0, 2.0, 2.0]):
    wait_timeout = server.wait_tool({"session_id": fake_sid, "wait_timeout_sec": 1})
wait_timeout_data = json.loads(wait_timeout["content"][0]["text"])
assert wait_timeout_data["status"] == "RUNNING"
assert wait_timeout_data["wait"]["timed_out"] is True
assert "continues in the background" in wait_timeout_data["summary"]

# messages exposes only assistant prose and supports monotonic revisions.
chat_path = Path(_sandbox.name) / "chat.jsonl"
chat_rows = [
    {"timestamp": "t0", "type": "system", "systemPayload": {"uiEvent": {"event.name": "gigacode.tool_call"}}},
    {"timestamp": "t1", "type": "assistant", "message": {"parts": [
        {"text": "First visible message."},
        {"functionCall": {"name": "read_file", "args": {"path": "x"}}},
    ]}},
    {"timestamp": "t2", "type": "tool_result", "message": {"parts": [
        {"functionResponse": {"name": "read_file", "response": {"output": "secret tool output"}}},
    ]}},
    {"timestamp": "t3", "type": "assistant", "message": {"parts": [
        {"text": "Second visible message.\nWith detail."},
    ]}},
    {"timestamp": "t4", "type": "assistant", "message": {"parts": [
        {"functionCall": {"name": "grep_search", "args": {}}},
    ]}},
    {"timestamp": "t5", "type": "assistant", "message": {"parts": [
        {"text": "Third visible message."},
    ]}},
]
chat_path.write_text("\n".join(json.dumps(row) for row in chat_rows) + "\n", encoding="utf-8")
with patch.object(server, "_find_chat_path", return_value=chat_path):
    all_messages = server._assistant_messages(fake_sid)
    assert [m["revision"] for m in all_messages] == [1, 2, 3]
    assert [m["text"] for m in all_messages] == [
        "First visible message.",
        "Second visible message.\nWith detail.",
        "Third visible message.",
    ]

    latest = server.messages_tool({"session_id": fake_sid, "message_limit": 2})
    latest_data = json.loads(latest["content"][0]["text"])
    assert [m["revision"] for m in latest_data["messages"]] == [2, 3]
    assert latest_data["revision"] == 3
    assert latest_data["latest_revision"] == 3
    assert latest_data["has_more"] is False
    assert "secret tool output" not in latest["content"][0]["text"]
    assert "read_file" not in latest["content"][0]["text"]

    incremental = server.messages_tool({
        "session_id": fake_sid,
        "after_revision": 1,
        "message_limit": 1,
    })
    incremental_data = json.loads(incremental["content"][0]["text"])
    assert [m["revision"] for m in incremental_data["messages"]] == [2]
    assert incremental_data["revision"] == 2
    assert incremental_data["latest_revision"] == 3
    assert incremental_data["has_more"] is True

    remainder = server.messages_tool({
        "session_id": fake_sid,
        "after_revision": incremental_data["revision"],
        "message_limit": 10,
    })
    remainder_data = json.loads(remainder["content"][0]["text"])
    assert [m["revision"] for m in remainder_data["messages"]] == [3]
    assert remainder_data["revision"] == 3
    assert remainder_data["has_more"] is False

assert server._request_cancel(fake_sid, fake_jid) is True
assert server._check_cancel_request(fake_sid, fake_jid) is True
server._cleanup_control(fake_sid, fake_jid)
assert server._check_cancel_request(fake_sid, fake_jid) is False

# -------------------------------------------------------------------
# 9. cancel_tool on unknown/non-UUID session
# -------------------------------------------------------------------
# Non-UUID rejected before state lookup
cancel_bad_sid = server.cancel_tool({"session_id": "../evil"})
cancel_bad_result = json.loads(cancel_bad_sid["content"][0]["text"])
assert cancel_bad_result["status"] == "FAILED"

# Valid UUID but unknown — reaches state lookup
cancel_unknown = server.cancel_tool({"session_id": "00000000-0000-0000-0000-000000000000"})
cancel_unknown_result = json.loads(cancel_unknown["content"][0]["text"])
assert cancel_unknown_result["status"] == "UNKNOWN"

# -------------------------------------------------------------------
# 10. handle() timeout validation (mocked so start_tool doesn't run)
# -------------------------------------------------------------------
def _fake_start_result(arguments: dict) -> dict:
    return server.text_result({"session_id": str(server.uuid.uuid4()), "status": "MOCKED"})

# Mock start_tool in the server module
original_start_tool = server.start_tool
server.start_tool = _fake_start_result

# Rejects boolean
bad_bool = server.handle({
    "jsonrpc": "2.0", "id": 10, "method": "tools/call",
    "params": {"name": "gigacode", "arguments": {"action": "start", "prompt": "x", "timeout_sec": True}},
})
assert bad_bool is not None
assert bad_bool.get("result", {}).get("isError") is True

# Rejects negative
bad_neg = server.handle({
    "jsonrpc": "2.0", "id": 11, "method": "tools/call",
    "params": {"name": "gigacode", "arguments": {"action": "start", "prompt": "x", "timeout_sec": -1}},
})
assert bad_neg is not None
assert bad_neg.get("result", {}).get("isError") is True

# Accepts 0
ok_zero = server.handle({
    "jsonrpc": "2.0", "id": 12, "method": "tools/call",
    "params": {"name": "gigacode", "arguments": {"action": "start", "prompt": "x", "timeout_sec": 0}},
})
assert ok_zero is not None
result_text = json.loads(ok_zero["result"]["content"][0]["text"])
assert result_text["status"] == "MOCKED"

# Accepts large positive
ok_large = server.handle({
    "jsonrpc": "2.0", "id": 13, "method": "tools/call",
    "params": {"name": "gigacode", "arguments": {"action": "start", "prompt": "x", "timeout_sec": 9999}},
})
assert ok_large is not None

# Rejects float
bad_float = server.handle({
    "jsonrpc": "2.0", "id": 14, "method": "tools/call",
    "params": {"name": "gigacode", "arguments": {"action": "start", "prompt": "x", "timeout_sec": 10.5}},
})
assert bad_float is not None
assert bad_float.get("result", {}).get("isError") is True

# Rejects string
bad_str = server.handle({
    "jsonrpc": "2.0", "id": 15, "method": "tools/call",
    "params": {"name": "gigacode", "arguments": {"action": "start", "prompt": "x", "timeout_sec": "30"}},
})
assert bad_str is not None
assert bad_str.get("result", {}).get("isError") is True

# Restore
server.start_tool = original_start_tool

# -------------------------------------------------------------------
# 11. status_tool with bad session_id
# -------------------------------------------------------------------
bad_status = server.handle({
    "jsonrpc": "2.0", "id": 16, "method": "tools/call",
    "params": {"name": "gigacode", "arguments": {"action": "status", "session_id": "../etc"}},
})
assert bad_status is not None
result_text = json.loads(bad_status["result"]["content"][0]["text"])
assert result_text["status"] == "FAILED"

# -------------------------------------------------------------------
# 12. messages dispatch validates cursor and limit
# -------------------------------------------------------------------
bad_messages_cursor = server.handle({
    "jsonrpc": "2.0", "id": 17, "method": "tools/call",
    "params": {"name": "gigacode", "arguments": {
        "action": "messages", "session_id": fake_sid, "after_revision": True,
    }},
})
assert bad_messages_cursor is not None
assert bad_messages_cursor.get("result", {}).get("isError") is True

bad_messages_limit = server.handle({
    "jsonrpc": "2.0", "id": 18, "method": "tools/call",
    "params": {"name": "gigacode", "arguments": {
        "action": "messages", "session_id": fake_sid, "message_limit": 51,
    }},
})
assert bad_messages_limit is not None
assert bad_messages_limit.get("result", {}).get("isError") is True

# -------------------------------------------------------------------
# 13. cancel dispatch also rejects non-UUID
# -------------------------------------------------------------------
bad_cancel = server.handle({
    "jsonrpc": "2.0", "id": 17, "method": "tools/call",
    "params": {"name": "gigacode", "arguments": {"action": "cancel", "session_id": "simple"}},
})
assert bad_cancel is not None
result_text = json.loads(bad_cancel["result"]["content"][0]["text"])
assert result_text["status"] == "FAILED"

# -------------------------------------------------------------------
# 13. cancel_tool on a finished session (needs a state file)
# -------------------------------------------------------------------
finished_sid = str(server.uuid.uuid4())
server._write_state(finished_sid, {"phase": "finished", "session_id": finished_sid, "handoff": {"status": "DONE"}})
cancel_finished = server.cancel_tool({"session_id": finished_sid})
cancel_finished_data = json.loads(cancel_finished["content"][0]["text"])
assert cancel_finished_data["status"] == "ALREADY_FINISHED"
# Cleanup
server._state_path(finished_sid).unlink(missing_ok=True)

# Restore original CACHE_ROOT and clean sandbox
server.CACHE_ROOT = _original_cache_root
_sandbox.cleanup()

print("GigaCode black-box bridge: PASS")