#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import selectors
import subprocess
import time
from typing import Any

PROJECT_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), ".."))
INSTANCE_ID = os.environ.get("HARR_EIN_SMOKE_INSTANCE", "").strip()
if not INSTANCE_ID:
    raise SystemExit("set HARR_EIN_SMOKE_INSTANCE to an explicitly user-authorized named Ein instance before running this real-model smoke test")

proc = subprocess.Popen(
    [os.environ.get("LEANCTX_SMOKE_BINARY", "lean-ctx")],
    cwd=PROJECT_ROOT,
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=open(os.environ.get("LEANCTX_SMOKE_STDERR", os.devnull), "w", encoding="utf-8"),
    text=True,
    bufsize=1,
)
if proc.stdin is None or proc.stdout is None:
    raise RuntimeError("failed to open lean-ctx stdio")

selector = selectors.DefaultSelector()
selector.register(proc.stdout, selectors.EVENT_READ)

def send(obj: dict[str, Any]) -> None:
    proc.stdin.write(json.dumps(obj, separators=(",", ":")) + "\n")
    proc.stdin.flush()

def read_until_id(req_id: int, timeout: float) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    deadline = time.monotonic() + timeout
    seen: list[dict[str, Any]] = []
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"timeout waiting for MCP response id={req_id}; seen={seen!r}")
        if proc.poll() is not None:
            raise RuntimeError(f"lean-ctx exited early with {proc.returncode}; seen={seen!r}")
        events = selector.select(min(remaining, 1.0))
        if not events:
            continue
        line = proc.stdout.readline()
        if not line:
            continue
        line = line.strip()
        if not line:
            continue
        item = json.loads(line)
        seen.append(item)
        if item.get("id") == req_id:
            return item, seen

def tool_payload(response: dict[str, Any]) -> dict[str, Any]:
    if "error" in response:
        raise RuntimeError(f"MCP error: {response['error']!r}")
    result = response.get("result")
    if not isinstance(result, dict):
        raise RuntimeError(f"missing MCP result: {response!r}")
    if result.get("isError"):
        raise RuntimeError(f"tool returned isError: {result!r}")
    content = result.get("content")
    if not isinstance(content, list) or not content:
        raise RuntimeError(f"missing tool content: {result!r}")
    text = content[0].get("text") if isinstance(content[0], dict) else None
    if not isinstance(text, str):
        raise RuntimeError(f"missing text result: {result!r}")
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise RuntimeError(f"downstream JSON is not an object: {parsed!r}")
    return parsed

def call_ein(req_id: int, downstream_args: dict[str, Any], *, progress_token: str | None = None,
                  timeout: float) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    params: dict[str, Any] = {
        "name": "ctx_tools",
        "arguments": {
            "action": "call",
            "tool": f"{INSTANCE_ID}::ein",
            "arguments": downstream_args,
        },
    }
    if progress_token is not None:
        params["_meta"] = {"progressToken": progress_token}
    send({"jsonrpc": "2.0", "id": req_id, "method": "tools/call", "params": params})
    response, seen = read_until_id(req_id, timeout)
    return tool_payload(response), seen

try:
    send({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "harr-ein-live-stream-smoke", "version": "0.1"},
        },
    })
    init, _ = read_until_id(1, 20)
    version = init.get("result", {}).get("serverInfo", {}).get("version")
    if version != "3.11.0":
        raise RuntimeError(f"unexpected LeanCTX version: {version!r}")
    send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

    prompt = """Read-only live-stream transport smoke test. Do not edit, create, delete, commit, or push anything.

Acceptance criteria:
C1. Inspect README.md near the beginning and verify that this repository is Harr.
C2. Use ordinary assistant prose while working so the bridge has at least one user-visible progress message before the final handoff.
C3. Return DONE only after the read-only verification succeeds.

Keep the task tiny. The final handoff must follow the bridge-required JSON schema."""

    started, _ = call_ein(
        2,
        {"action": "start", "prompt": prompt, "timeout_sec": 180},
        timeout=40,
    )
    sid = started.get("session_id")
    if not isinstance(sid, str) or not sid:
        raise RuntimeError(f"start returned no session_id: {started!r}")
    if started.get("status") not in {"RUNNING", "STARTING", "DONE"}:
        raise RuntimeError(f"unexpected start status: {started!r}")
    if started.get("status") == "DONE":
        raise RuntimeError("Ein worker finished before wait; cannot validate live progress path")

    terminal, wait_seen = call_ein(
        3,
        {"action": "wait", "session_id": sid, "wait_timeout_sec": 240},
        progress_token="ein-live-smoke",
        timeout=270,
    )

    progress = [
        item for item in wait_seen
        if item.get("method") == "notifications/progress"
        and isinstance(item.get("params"), dict)
        and item["params"].get("progressToken") == "ein-live-smoke"
    ]
    messages = [item["params"].get("message", "") for item in progress]

    if terminal.get("status") != "DONE":
        raise RuntimeError(f"terminal status is not DONE: {terminal!r}")
    if not progress:
        raise RuntimeError(f"no progress notifications reached the outer MCP client; terminal={terminal!r}")
    if any('\"status\": \"DONE\"' in msg or "```json" in msg for msg in messages):
        raise RuntimeError(f"final JSON leaked into progress notifications: {messages!r}")
    if not all(isinstance(msg, str) and msg.strip() for msg in messages):
        raise RuntimeError(f"unexpected progress message shape: {messages!r}")

    print(json.dumps({
        "ok": True,
        "session_id": sid,
        "start_status": started.get("status"),
        "terminal_status": terminal.get("status"),
        "progress_count": len(progress),
        "progress_messages": messages,
        "summary": terminal.get("summary"),
    }, ensure_ascii=False, indent=2))
finally:
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
