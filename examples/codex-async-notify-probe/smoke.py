#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
import subprocess
import sys


HERE = pathlib.Path(__file__).resolve().parent
SERVER = HERE / "server.py"
MARKER_URI = "ui://async-notify-probe/marker.html"


class Client:
    def __init__(self) -> None:
        self.proc = subprocess.Popen(
            [sys.executable, str(SERVER)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._id = 0

    def call(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        req = {"jsonrpc": "2.0", "id": self._id, "method": method}
        if params is not None:
            req["params"] = params
        assert self.proc.stdin is not None
        assert self.proc.stdout is not None
        self.proc.stdin.write(json.dumps(req) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            err = ""
            if self.proc.stderr is not None:
                err = self.proc.stderr.read()
            raise RuntimeError(f"server closed unexpectedly: {err}")
        msg = json.loads(line)
        if "error" in msg:
            raise RuntimeError(msg["error"])
        return msg["result"]

    def close(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=2)


def main() -> int:
    c = Client()
    try:
        init = c.call("initialize", {})
        assert init["serverInfo"]["name"] == "codex-mcp-async-probe"

        tools = c.call("tools/list")["tools"]
        names = {t["name"] for t in tools}
        required = {
            "show_async_workspace_probe",
            "start_async_marker_probe",
            "probe_wait_job_ui",
            "probe_claim_ui",
            "probe_release_ui",
        }
        assert required <= names

        resource = c.call("resources/read", {"uri": MARKER_URI})["contents"][0]
        meta = resource["_meta"]
        assert meta["openai/widgetHeightHint"] == 44
        assert meta["openai/widgetMinFrameHeight"] == 40
        assert meta["openai/widgetShowCodexWidgetInline"] is True

        started = c.call(
            "tools/call",
            {
                "name": "start_async_marker_probe",
                "arguments": {"delay_sec": 1, "message": "smoke"},
            },
        )
        job = started["structuredContent"]
        job_id = job["job_id"]
        assert job["status"] == "RUNNING"

        waited = c.call(
            "tools/call",
            {
                "name": "probe_wait_job_ui",
                "arguments": {
                    "panel_id": "smoke-panel",
                    "job_id": job_id,
                    "timeout_ms": 4000,
                },
            },
        )["structuredContent"]["job"]
        assert waited["status"] == "DONE"
        assert waited["event_id"]

        claimed = c.call(
            "tools/call",
            {
                "name": "probe_claim_ui",
                "arguments": {
                    "panel_id": "smoke-panel",
                    "event_id": waited["event_id"],
                },
            },
        )["structuredContent"]
        assert claimed["claimed"] is True

        second = c.call(
            "tools/call",
            {
                "name": "probe_claim_ui",
                "arguments": {
                    "panel_id": "other-panel",
                    "event_id": waited["event_id"],
                },
            },
        )["structuredContent"]
        assert second["claimed"] is False

        released = c.call(
            "tools/call",
            {
                "name": "probe_release_ui",
                "arguments": {
                    "panel_id": "smoke-panel",
                    "event_id": waited["event_id"],
                },
            },
        )["structuredContent"]
        assert released["released"] is True

        print("async notify probe smoke: PASS")
        return 0
    finally:
        c.close()


if __name__ == "__main__":
    raise SystemExit(main())
