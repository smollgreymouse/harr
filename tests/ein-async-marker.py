#!/usr/bin/env python3
"""Production named-Ein async marker contract without a real model or Desktop host."""

from __future__ import annotations

import json
import importlib.util
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
DIRECT = ROOT / "common" / "mcp" / "ein_direct.py"
SERVER = ROOT / "common" / "mcp" / "einherjar_server.py"
MARKER_URI = "ui://harr-ein/marker.html"


def rpc(process: subprocess.Popen, number: int, method: str, params: dict | None = None, timeout: float = 10.0) -> dict:
    assert process.stdin is not None and process.stdout is not None and process.stderr is not None
    process.stdin.write(json.dumps({"jsonrpc": "2.0", "id": number, "method": method, "params": params or {}}) + "\n")
    process.stdin.flush()
    assert select.select([process.stdout], [], [], timeout)[0], f"timeout waiting for {method}"
    raw = process.stdout.readline()
    assert raw, process.stderr.read()
    value = json.loads(raw)
    assert value.get("id") == number, value
    return value


def stop(process: subprocess.Popen) -> None:
    process.terminate()
    try:
        process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate(timeout=5)


with tempfile.TemporaryDirectory(prefix="harr-ein-marker-") as tmp:
    base = Path(tmp)
    home = base / "home"
    home.mkdir()
    config_root = home / ".config" / "harr"
    (config_root / "einherjar").mkdir(parents=True)
    work = base / "workspace"
    work.mkdir()

    fake = base / "fake_worker.py"
    fake.write_text(
        """import json,time
time.sleep(5.5)
print(json.dumps({
  "status":"DONE",
  "summary":"async marker fixture completed",
  "changed":[],
  "verified":[{"criterion":"marker","check":"fixture","result":"PASS","evidence":"exit=0"}],
  "self_review":{"criteria_complete":True,"diff_scope_clean":True,"unverified":[]},
  "escalation":None,
  "blockers":[]
}))
""",
        encoding="utf-8",
    )
    instances = {
        "schema": 2,
        "instances": [{
            "id": "fake-marker",
            "adapter": "custom",
            "enabled": True,
            "definition": {
                "adapter": "command-template",
                "start": [sys.executable, str(fake), "{prompt}"],
            },
        }],
    }
    (config_root / "einherjar" / "instances.json").write_text(json.dumps(instances), encoding="utf-8")

    env = {
        **os.environ,
        "HOME": str(home),
        "HARR_CONFIG_DIR": str(config_root),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_CACHE_HOME": str(home / ".cache"),
        "XDG_STATE_HOME": str(home / ".local" / "state"),
        "PYTHONPATH": str(ROOT),
    }

    direct = subprocess.Popen(
        [sys.executable, str(DIRECT), "fake-marker"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=work,
        env=env,
        bufsize=1,
    )
    try:
        initialized = rpc(direct, 1, "initialize")["result"]
        assert "resources" in initialized["capabilities"]

        tools = rpc(direct, 2, "tools/list")["result"]["tools"]
        by_name = {tool["name"]: tool for tool in tools}
        assert set(by_name) == {
            "ein",
            "ein_marker_wait_ui",
            "ein_marker_claim_ui",
            "ein_marker_release_ui",
            "ein_marker_event_ui",
        }
        ein_meta = by_name["ein"]["_meta"]
        assert ein_meta["ui"]["resourceUri"] == MARKER_URI
        assert ein_meta["openai/ui"]["preferredModelDisplayMode"] == "inline"
        for name in set(by_name) - {"ein"}:
            assert by_name[name]["_meta"]["ui"]["visibility"] == ["app"]

        resource = rpc(direct, 3, "resources/read", {"uri": MARKER_URI})["result"]["contents"][0]
        meta = resource["_meta"]
        assert meta["openai/widgetHeightHint"] == 44
        assert meta["openai/widgetMinFrameHeight"] == 40
        assert meta["openai/widgetShowCodexWidgetInline"] is True
        html = resource["text"]
        assert "ui/message" in html
        assert "[harr-ein-completion]" in html
        assert "ui/request-display-mode" not in html
        assert "fullscreen" not in html
        assert "toolAction!=='start'&&toolAction!=='resume'" in html

        started = rpc(
            direct,
            4,
            "tools/call",
            {"name": "ein", "arguments": {"action": "start", "prompt": "fixture"}},
            timeout=8,
        )["result"]["structuredContent"]
        assert started["status"] in {"STARTING", "RUNNING"}, started
        sid = started["session_id"]
        job_id = started.get("job_id") or started.get("runtime", {}).get("job_id")
        assert isinstance(job_id, str) and len(job_id) == 12, started

        stale = rpc(
            direct,
            5,
            "tools/call",
            {
                "name": "ein_marker_wait_ui",
                "arguments": {
                    "panel_id": "stale",
                    "session_id": sid,
                    "job_id": "aaaaaaaaaaaa",
                    "timeout_ms": 100,
                },
            },
        )["result"]["structuredContent"]
        assert stale["replaced"] is True and stale["terminal"] is False

        # The marker long-poll must not monopolize the direct Ein stdio loop.
        assert direct.stdin is not None and direct.stdout is not None
        direct.stdin.write(json.dumps({
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {
                "name": "ein_marker_wait_ui",
                "arguments": {
                    "panel_id": "marker-a",
                    "session_id": sid,
                    "job_id": job_id,
                    "timeout_ms": 7000,
                },
            },
        }) + "\n")
        direct.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 61, "method": "ping", "params": {}}) + "\n")
        direct.stdin.flush()
        assert select.select([direct.stdout], [], [], 1.0)[0], "marker long-poll blocked ping"
        ping = json.loads(direct.stdout.readline())
        assert ping["id"] == 61 and ping["result"] == {}, ping
        assert select.select([direct.stdout], [], [], 10.0)[0], "terminal marker wait timed out"
        waited_reply = json.loads(direct.stdout.readline())
        assert waited_reply["id"] == 6, waited_reply
        waited = waited_reply["result"]["structuredContent"]
        assert waited["terminal"] is True and waited["status"] == "DONE", waited
        assert waited["handoff"]["summary"] == "async marker fixture completed"

        args_a = {
            "panel_id": "marker-a",
            "session_id": sid,
            "job_id": job_id,
            "owner_token": "owner-a",
        }
        first = rpc(direct, 7, "tools/call", {"name": "ein_marker_claim_ui", "arguments": args_a})["result"]["structuredContent"]
        assert first["claimed"] is True and first["handoff"]["status"] == "DONE"

        second = rpc(
            direct,
            8,
            "tools/call",
            {
                "name": "ein_marker_claim_ui",
                "arguments": {**args_a, "panel_id": "marker-b", "owner_token": "owner-b"},
            },
        )["result"]["structuredContent"]
        assert second["claimed"] is False

        released = rpc(direct, 9, "tools/call", {"name": "ein_marker_release_ui", "arguments": args_a})["result"]["structuredContent"]
        assert released["released"] is True

        reclaimed = rpc(
            direct,
            10,
            "tools/call",
            {
                "name": "ein_marker_claim_ui",
                "arguments": {**args_a, "panel_id": "marker-b", "owner_token": "owner-b"},
            },
        )["result"]["structuredContent"]
        assert reclaimed["claimed"] is True
    finally:
        stop(direct)

    runtime = config_root / "einherjar" / "runtime" / "fake-marker"
    gateway_env = {
        **env,
        "HARR_CONFIG_DIR": str(runtime),
        "HARR_EIN_INSTANCE": "fake-marker",
    }
    gateway_env.pop("HARR_EIN_MCP_APP", None)
    gateway = subprocess.Popen(
        [sys.executable, str(SERVER)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=work,
        env=gateway_env,
        bufsize=1,
    )
    try:
        initialized = rpc(gateway, 20, "initialize")["result"]
        assert "resources" not in initialized["capabilities"]
        tools = rpc(gateway, 21, "tools/list")["result"]["tools"]
        assert len(tools) == 1 and tools[0]["name"] == "ein"
        assert "_meta" not in tools[0]
        unknown = rpc(gateway, 22, "resources/read", {"uri": MARKER_URI})
        assert unknown["error"]["code"] == -32601
    finally:
        stop(gateway)

    # Terminal outcomes include success, failure and cancellation. The
    # filesystem claim must also arbitrate two simultaneous UI owners.
    with patch.dict(os.environ, {**env, "HARR_EIN_INSTANCE": "fake-marker", "HARR_EIN_MCP_APP": "1"}):
        marker_spec = importlib.util.spec_from_file_location("ein_marker_claim_contract", SERVER)
        assert marker_spec and marker_spec.loader
        marker = importlib.util.module_from_spec(marker_spec)
        marker_spec.loader.exec_module(marker)
    marker.MARKER_CLAIM_ROOT = base / "claim-contract"
    marker.MARKER_CLAIM_ROOT.mkdir()
    job = "123456789abc"
    for terminal_status in ("DONE", "FAILED", "CANCELLED", "ESCALATE", "TIMEOUT"):
        payload = {"status": terminal_status, "job_id": job, "summary": "fixture", "handoff": {"status": terminal_status}}
        with patch.object(marker, "_dispatch_named_action", return_value={"structuredContent": payload}):
            snapshot = marker._marker_snapshot(sid, job)
        assert snapshot["terminal"] is True and snapshot["status"] == terminal_status, snapshot

    barrier = threading.Barrier(2)
    snapshot = {"instance": "fake-marker", "session_id": sid, "job_id": job,
                "status": "DONE", "terminal": True, "replaced": False,
                "handoff": {"status": "DONE"}}
    def simultaneous_snapshot(session_id, job_id):
        barrier.wait(timeout=5)
        return snapshot
    owners = ("panel-a", "panel-b")
    with patch.object(marker, "_marker_snapshot", side_effect=simultaneous_snapshot):
        with ThreadPoolExecutor(max_workers=2) as pool:
            claims = list(pool.map(
                lambda owner: marker._tool_payload(marker._marker_claim({
                    "session_id": sid, "job_id": job, "owner_token": owner,
                })),
                owners,
            ))
    assert sorted(result["claimed"] for result in claims) == [False, True], claims
    winning_owner = next(owner for owner, result in zip(owners, claims) if result["claimed"])
    assert marker._tool_payload(marker._marker_release({
        "session_id": sid, "job_id": job, "owner_token": winning_owner,
    }))["released"] is True

print("Named Ein async marker: PASS")
