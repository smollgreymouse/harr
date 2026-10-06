#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = ROOT / "common" / "mcp" / "gigacode_server.py"

spec = importlib.util.spec_from_file_location("harr_gigacode_server", SERVER_PATH)
assert spec and spec.loader
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)

assert server.SERVER_VERSION == "1.7.0"
assert len(server.TOOLS) == 1
tool = server.TOOLS[0]
assert tool["name"] == "gigacode"
assert tool["inputSchema"]["properties"]["action"]["enum"] == ["start", "resume", "status"]
assert server._pid_alive(os.getpid()) is True
group_kwargs = server._new_process_group_kwargs()
if os.name == "nt":
    assert "creationflags" in group_kwargs
    assert "start_new_session" not in group_kwargs
else:
    assert group_kwargs == {"start_new_session": True}

# Harr owns only the process/session/handoff bridge. GigaCode's internal
# execution stack is deliberately opaque and must not be coupled to LeanCTX,
# a native shell tool name, or any GigaCode MCP configuration.
source = SERVER_PATH.read_text(encoding="utf-8")
for forbidden in (
    "--allowed-tools",
    "mcp__lean-ctx__ctx_shell",
    "run_shell_command",
    "Use the allowed LeanCTX",
):
    assert forbidden not in source, forbidden
assert "The bridge does not prescribe or" in server.WORKER_CONTRACT
assert "internal tools, MCP servers, shell implementation, or editor" in server.WORKER_CONTRACT

listed = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
assert listed is not None
assert [item["name"] for item in listed["result"]["tools"]] == ["gigacode"]

sample = """worker note
```json
{"status":"DONE","summary":"ok","changed":[],"verified":[],"escalation":null,"blockers":[]}
```
"""
handoff = server.extract_json_object(sample)
assert handoff is not None
assert handoff["status"] == "DONE"

parsed, is_error = server.parse_worker_handoff(json.dumps(handoff), 0, "")
assert parsed["summary"] == "ok"
assert is_error is False

print("GigaCode black-box bridge: PASS")
