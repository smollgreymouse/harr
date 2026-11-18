#!/usr/bin/env python3
"""Doctor's direct remote-HTTP MCP catalog check against a canned streamable-HTTP server."""
from __future__ import annotations

import importlib.util
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]

spec = importlib.util.spec_from_file_location("harr_doctor", ROOT / "common" / "doctor.py")
assert spec and spec.loader
doctor = importlib.util.module_from_spec(spec)
sys_modules_name = spec.name
import sys
sys.modules[sys_modules_name] = doctor
spec.loader.exec_module(doctor)

TOOLS = [
    {"name": "webSearchPrime", "inputSchema": {"type": "object", "properties": {}}},
]
STATE = {"auth": "right-key", "sse": False, "session_id": "sess-test-1"}


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length))
        auth = self.headers.get("Authorization", "")
        if auth != f"Bearer {STATE['auth']}":
            body = b'{"error":"unauthorized"}'
            self.send_response(401)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        method = payload.get("method")
        if method == "initialize":
            result = {
                "jsonrpc": "2.0",
                "id": payload["id"],
                "result": {"protocolVersion": "2025-06-18", "capabilities": {}, "serverInfo": {"name": "fake-zai", "version": "1"}},
            }
            headers = {"Content-Type": "application/json", "Mcp-Session-Id": STATE["session_id"]}
        elif method == "notifications/initialized":
            self.send_response(202)
            self.end_headers()
            return
        elif method == "tools/list":
            result = {"jsonrpc": "2.0", "id": payload["id"], "result": {"tools": TOOLS}}
            headers = {"Content-Type": "text/event-stream" if STATE["sse"] else "application/json"}
        else:
            self.send_response(400)
            self.end_headers()
            return
        body = json.dumps(result).encode("utf-8")
        if STATE["sse"] and method == "tools/list":
            body = b"data: " + body + b"\n\n"
        self.send_response(200)
        for key, value in headers.items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:  # keep test output clean
        pass


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{server.server_address[1]}/mcp"

server_entry = {
    "name": "websearch",
    "transport": "http",
    "url": url,
    "secrets": [
        {
            "name": "websearch",
            "file": "zai-coding-plan-key",
            "memento_id": "mcp/zai-coding-plan/default",
            "target": {"kind": "header", "name": "Authorization", "format": "Bearer {secret}"},
        }
    ],
    "doctor": {"required_tools": ["webSearchPrime"], "probe": {"kind": "catalog-only", "timeout_sec": 10}},
}

with tempfile.TemporaryDirectory(prefix="harr-http-catalog-") as raw:
    tmp = Path(raw)
    paths = SimpleNamespace(secrets=tmp / "secrets")
    paths.secrets.mkdir()
    secret_path = paths.secrets / "zai-coding-plan-key"

    # Missing secret fails closed before any request is made.
    check = doctor.http_catalog_check(server_entry, paths, timeout=10)
    assert check.status == "FAIL" and "secret is missing" in check.summary

    secret_path.write_text("right-key\n", encoding="utf-8")
    check = doctor.http_catalog_check(server_entry, paths, timeout=10)
    assert check.status == "PASS", check.summary
    assert check.evidence["tools"] == ["webSearchPrime"], check.evidence

    # SSE-framed responses parse as well.
    STATE["sse"] = True
    check = doctor.http_catalog_check(server_entry, paths, timeout=10)
    assert check.status == "PASS", check.summary
    STATE["sse"] = False

    # A wrong key fails the handshake without leaking the credential.
    secret_path.write_text("wrong-key\n", encoding="utf-8")
    check = doctor.http_catalog_check(server_entry, paths, timeout=10)
    assert check.status == "FAIL" and "right-key" not in check.summary
    assert "right-key" not in json.dumps(check.evidence)

    # A plain-internet http:// URL is rejected by the URL guard.
    insecure = dict(server_entry, url=url.replace("http://127.0.0.1", "http://example.invalid"))
    check = doctor.http_catalog_check(insecure, paths, timeout=10)
    assert check.status == "FAIL"

    # Missing required tools fail the catalog contract.
    secret_path.write_text("right-key\n", encoding="utf-8")
    broken = dict(server_entry, doctor={"required_tools": ["nonexistent_tool"], "probe": {"kind": "catalog-only"}})
    check = doctor.http_catalog_check(broken, paths, timeout=10)
    assert check.status == "FAIL" and "missing required tools" in check.summary

server.shutdown()
print("remote HTTP MCP catalog check: PASS")
