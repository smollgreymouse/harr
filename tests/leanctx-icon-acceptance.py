#!/usr/bin/env python3
"""Exercise a real pinned LeanCTX MCP server through Harr's manager launcher.

Usage: python3 tests/leanctx-icon-acceptance.py --binary PATH
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
ICON = ROOT / "harr.png"
ICON_SHA256 = "0a601b2145d1bdbc9e987cb1da61663ce543e610e3d082ae5a1d1169ceaa007e"
MANAGER = ROOT / "common/mcp/manager.py"
MAX_FRAME = 2 * 1024 * 1024


def launch_manager(binary: str) -> None:
    import importlib.util
    spec = importlib.util.spec_from_file_location("harr_acceptance_manager", MANAGER)
    assert spec and spec.loader
    manager = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(manager)
    manager.exec_leanctx(
        argparse.Namespace(real=binary, rest=["mcp"]), {"servers": []}
    )


def receive_rpc(proc: subprocess.Popen[bytes], selector: selectors.BaseSelector,
                pending: bytearray, request_id: int, timeout: float) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        marker = pending.find(b"\r\n\r\n")
        if marker >= 0:
            header = bytes(pending[:marker]).decode("ascii", errors="strict")
            length = next((int(line.split(":", 1)[1].strip())
                           for line in header.split("\r\n")
                           if line.lower().startswith("content-length:")), None)
            if length is None or length < 0 or length > MAX_FRAME:
                raise RuntimeError(f"invalid MCP frame length: {length}")
            frame_end = marker + 4 + length
            if len(pending) >= frame_end:
                payload = json.loads(pending[marker + 4:frame_end])
                del pending[:frame_end]
                if payload.get("id") == request_id:
                    return payload
                continue
        remaining = deadline - time.monotonic()
        if not selector.select(remaining):
            break
        chunk = os.read(proc.stdout.fileno(), 65536)
        if not chunk:
            raise RuntimeError("LeanCTX MCP exited before responding")
        pending.extend(chunk)
        if len(pending) > MAX_FRAME + 4096:
            raise RuntimeError("LeanCTX MCP response exceeded the bounded frame size")
    raise TimeoutError(f"LeanCTX MCP request {request_id} timed out")


def send_rpc(proc: subprocess.Popen[bytes], method: str, request_id: int,
             params: dict | None = None) -> None:
    message = json.dumps({"jsonrpc": "2.0", "id": request_id,
                          "method": method, "params": params or {}}).encode()
    proc.stdin.write(f"Content-Length: {len(message)}\r\n\r\n".encode() + message)
    proc.stdin.flush()


def send_notification(proc: subprocess.Popen[bytes], method: str,
                      params: dict | None = None) -> None:
    message = json.dumps({"jsonrpc": "2.0", "method": method,
                          "params": params or {}}).encode()
    proc.stdin.write(f"Content-Length: {len(message)}\r\n\r\n".encode() + message)
    proc.stdin.flush()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True, help="verified pinned LeanCTX executable")
    args = parser.parse_args()
    binary = Path(args.binary).resolve(strict=True)
    if not binary.is_file():
        parser.error(f"LeanCTX binary is not a file: {binary}")
    icon_bytes = ICON.read_bytes()
    if hashlib.sha256(icon_bytes).hexdigest() != ICON_SHA256:
        raise RuntimeError("source Harr icon does not match the accepted original asset")

    with tempfile.TemporaryDirectory(prefix="harr-leanctx-acceptance-") as isolated:
        base = Path(isolated)
        home, config, data, state, project = (base / name for name in
                                               ("home", "config", "data", "state", "project"))
        for directory in (home, config, data, state, project):
            directory.mkdir()
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(home), "XDG_CONFIG_HOME": str(config),
            "XDG_DATA_HOME": str(data), "XDG_STATE_HOME": str(state),
            "XDG_CACHE_HOME": str(base / "cache"),
            "HARR_CONFIG_DIR": str(config / "harr"),
            "HARR_WORKSPACE_MODE": "legacy", "NO_COLOR": "1",
        }
        (config / "harr").mkdir()
        (config / "harr" / "mcp").mkdir()
        (config / "harr" / "mcp" / "config.json").write_text(
            '{"schema":1,"servers":[]}', encoding="utf-8")
        command = [sys.executable, str(Path(__file__).resolve()), "--manager-child", str(binary)]
        proc = subprocess.Popen(command, cwd=project, env=env, stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
        selector = selectors.DefaultSelector()
        selector.register(proc.stdout, selectors.EVENT_READ)
        pending = bytearray()
        try:
            send_rpc(proc, "initialize", 1, {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "harr-icon-acceptance", "version": "1"},
            })
            initialized = receive_rpc(proc, selector, pending, 1, 20)
            result = initialized.get("result", {})
            server_info = result.get("serverInfo", {})
            if server_info.get("name") != "lean-ctx":
                raise RuntimeError(f"unexpected serverInfo.name: {server_info.get('name')!r}")
            icons = server_info.get("icons")
            if not isinstance(icons, list) or not icons:
                raise RuntimeError("initialize response has no Harr icon in serverInfo.icons")
            icon = icons[0]
            prefix = "data:image/png;base64,"
            if icon.get("mimeType") != "image/png" or not icon.get("src", "").startswith(prefix):
                raise RuntimeError("serverInfo icon is not a PNG data URI")
            decoded = base64.b64decode(icon["src"][len(prefix):], validate=True)
            if decoded != icon_bytes:
                raise RuntimeError("LeanCTX serverInfo icon differs from the original Harr PNG")

            send_notification(proc, "notifications/initialized")
            send_rpc(proc, "tools/list", 3)
            listed = receive_rpc(proc, selector, pending, 3, 30)
            tools = listed.get("result", {}).get("tools", [])
            names = [tool.get("name") for tool in tools]
            if len(names) != len(set(names)):
                raise RuntimeError("tools/list contains duplicate tool names")
            ctx_read = next((tool for tool in tools if tool.get("name") == "ctx_read"), None)
            if not ctx_read or not isinstance(ctx_read.get("inputSchema"), dict):
                raise RuntimeError("tools/list is missing the ctx_read input schema")
            if any("data:image" in json.dumps(tool) for tool in tools):
                raise RuntimeError("large Harr icon data URI leaked into tool metadata")
            print(f"real LeanCTX MCP acceptance: PASS ({len(tools)} unique tools; exact Harr PNG; ctx_read schema)")
            return 0
        finally:
            selector.close()
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=3)
            if proc.stderr:
                proc.stderr.close()


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--manager-child":
        launch_manager(sys.argv[2])
    raise SystemExit(main())
