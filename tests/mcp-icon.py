#!/usr/bin/env python3
"""Verify manager icon-path wiring and Harr Ein metadata (not the real LeanCTX binary)."""
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
ICON = ROOT / "harr.png"
assert hashlib.sha256(ICON.read_bytes()).hexdigest() == "0a601b2145d1bdbc9e987cb1da61663ce543e610e3d082ae5a1d1169ceaa007e"
MANAGER_PATH = ROOT / "common/mcp/manager.py"
SERVER_PATH = ROOT / "common/mcp/einherjar_server.py"

spec = importlib.util.spec_from_file_location("harr_test_manager", MANAGER_PATH)
manager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manager)

captured = {}
def capture_env(*args, **kwargs):
    child_env = kwargs.get("env") or (args[-1] if args else {})
    captured.update(child_env)

with tempfile.TemporaryDirectory(prefix="harr-icon-runtime-") as tmp:
    runtime_mcp = Path(tmp) / "common/mcp"
    runtime_assets = runtime_mcp / "assets"
    runtime_assets.mkdir(parents=True)
    (runtime_assets / "harr.png").write_bytes(ICON.read_bytes())
    manager.HERE = runtime_mcp
    with patch.dict(os.environ, {"HARR_WORKSPACE_MODE": "legacy"}, clear=True), \
         patch.object(manager.os, "execvpe", side_effect=capture_env), \
         patch.object(manager.subprocess, "call", side_effect=capture_env):
        manager.exec_leanctx(type("Args", (), {"real": "/bin/true", "rest": ["mcp"]})(), {"servers": []})
    expected_icon = runtime_assets / "harr.png"
    assert captured.get("HARR_MCP_ICON_PATH") == str(expected_icon)
    assert captured.get("LEAN_CTX_LOG") == "info,rmcp=warn"
    captured.clear()
    with patch.dict(os.environ, {"HARR_WORKSPACE_MODE": "legacy", "LEAN_CTX_LOG": "debug"}, clear=True), \
         patch.object(manager.os, "execvpe", side_effect=capture_env), \
         patch.object(manager.subprocess, "call", side_effect=capture_env):
        manager.exec_leanctx(type("Args", (), {"real": "/bin/true", "rest": ["mcp"]})(), {"servers": []})
    assert captured.get("LEAN_CTX_LOG") == "debug"
    captured.clear()
    with patch.dict(os.environ, {}, clear=True), \
         patch.object(manager.os, "execvpe", side_effect=capture_env), \
         patch.object(manager.subprocess, "call", side_effect=capture_env):
        manager.exec_leanctx(type("Args", (), {"real": "/bin/true", "rest": ["status"]})(), {"servers": []})
    assert "HARR_MCP_ICON_PATH" not in captured

os.environ["HARR_MCP_ICON_PATH"] = str(ICON)
server_spec = importlib.util.spec_from_file_location("harr_test_ein_server", SERVER_PATH)
server = importlib.util.module_from_spec(server_spec)
server_spec.loader.exec_module(server)
response = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
icon = response["result"]["serverInfo"]["icons"][0]
expected_uri = "data:image/png;base64," + base64.b64encode(ICON.read_bytes()).decode("ascii")
assert icon == {"src": expected_uri, "mimeType": "image/png"}

os.environ.pop("HARR_MCP_ICON_PATH")
fallback = server.handle({"jsonrpc": "2.0", "id": 2, "method": "initialize", "params": {}})
assert "icons" not in fallback["result"]["serverInfo"]

print("managed Ein MCP icon handoff: PASS")
