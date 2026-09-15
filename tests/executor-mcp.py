#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
EXECUTOR_DIR = ROOT / "common" / "executor"
sys.path.insert(0, str(EXECUTOR_DIR))
import mcp_server  # noqa: E402


with tempfile.TemporaryDirectory() as tmp_raw:
    old_state = os.environ.get("HARR_EXECUTOR_STATE")
    old_child = os.environ.get("HARR_EXECUTOR_CHILD")
    os.environ["HARR_EXECUTOR_STATE"] = str(Path(tmp_raw) / "state")
    os.environ.pop("HARR_EXECUTOR_CHILD", None)
    try:
        server = mcp_server.Server()
        discover = server.handle({"jsonrpc": "2.0", "id": 1, "method": "server/discover", "params": {}})
        assert discover and discover["error"]["code"] == -32601
        initialized = server.handle({"jsonrpc": "2.0", "id": 2, "method": "initialize", "params": {"protocolVersion": "2025-11-25"}})
        assert initialized and initialized["result"]["protocolVersion"] == "2025-11-25"
        assert initialized["result"]["capabilities"]["tools"]["listChanged"] is False
        listed = server.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}})
        assert listed
        names = [item["name"] for item in listed["result"]["tools"]]
        assert names == ["start", "wait", "continue", "inspect", "cancel"]
        start_schema = listed["result"]["tools"][0]["inputSchema"]
        assert set(start_schema["required"]) == {"repo_root", "task_label", "execution_contract", "allowed_paths", "required_steps", "required_validation"}

        os.environ["HARR_EXECUTOR_CHILD"] = "1"
        child = mcp_server.Server()
        child_list = child.handle({"jsonrpc": "2.0", "id": 4, "method": "tools/list", "params": {}})
        assert child_list and child_list["result"]["tools"] == []
        child_call = child.handle({"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "start", "arguments": {}}})
        assert child_call and child_call["result"]["isError"] is True
        assert "disabled inside an executor child" in child_call["result"]["content"][0]["text"]

        proc = subprocess.run(
            [sys.executable, str(EXECUTOR_DIR / "mcp_server.py")],
            input="\n".join([
                json.dumps({"jsonrpc": "2.0", "id": 11, "method": "initialize", "params": {"protocolVersion": "2025-11-25"}}),
                json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}),
                json.dumps({"jsonrpc": "2.0", "id": 12, "method": "tools/list", "params": {}}),
            ]) + "\n",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
            env={**os.environ, "HARR_EXECUTOR_CHILD": "1"},
        )
        responses = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
        assert [item["id"] for item in responses] == [11, 12]
        assert responses[1]["result"]["tools"] == []
    finally:
        if old_state is None:
            os.environ.pop("HARR_EXECUTOR_STATE", None)
        else:
            os.environ["HARR_EXECUTOR_STATE"] = old_state
        if old_child is None:
            os.environ.pop("HARR_EXECUTOR_CHILD", None)
        else:
            os.environ["HARR_EXECUTOR_CHILD"] = old_child

print("executor MCP legacy stdio/recursion guard: PASS")
