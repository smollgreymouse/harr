#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from typing import Any

from service import ExecutorService

SERVER_NAME = "harr-executor"
SERVER_VERSION = "0.1.0"
LEGACY_PROTOCOL = "2025-11-25"


def _tool(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "properties": properties,
            "required": required,
        },
    }


TOOLS = [
    _tool(
        "start",
        "Start the explicit Harr implementation executor after the planner has completed repository investigation and produced a deterministic Execution Contract. Returns immediately with a run id; use wait for meaningful state changes. The executor model is configured by Harr (Luna low by default), not selected by the planner.",
        {
            "repo_root": {"type": "string", "description": "Absolute Git worktree root."},
            "task_label": {"type": "string", "maxLength": 200},
            "execution_contract": {"type": "string", "description": "Detailed HARR EXECUTOR CONTRACT. Must contain fixed decisions, exact ordered edits, invariants, STOP/BLOCKED conditions and validation."},
            "allowed_paths": {"type": "array", "minItems": 1, "maxItems": 200, "items": {"type": "string"}, "description": "Exact repo-relative paths, directory prefixes ending in /, or narrow glob patterns the executor may change."},
            "required_steps": {"type": "array", "maxItems": 200, "items": {"type": "string"}, "description": "Step ids that must all be reported completed before DONE is accepted."},
            "required_validation": {"type": "array", "maxItems": 100, "items": {"type": "string"}, "description": "Validation check labels that must all be reported PASS before DONE is accepted."},
        },
        ["repo_root", "task_label", "execution_contract", "allowed_paths", "required_steps", "required_validation"],
    ),
    _tool(
        "wait",
        "Long-poll a Harr executor run. Pass the last sequence already seen; the call returns on the next meaningful state transition or after at most 45 seconds. Do not poll repeatedly without using after_sequence.",
        {
            "run_id": {"type": "string"},
            "after_sequence": {"type": "integer", "minimum": 0},
            "timeout_seconds": {"type": "number", "minimum": 0, "maximum": 45, "default": 30},
        },
        ["run_id", "after_sequence"],
    ),
    _tool(
        "continue",
        "Resume the same persistent executor session after a BLOCKED packet. Send only a Planner Resolution Delta, never the whole plan again. expected_sequence must equal the BLOCKED packet sequence; stale resolutions are rejected.",
        {
            "run_id": {"type": "string"},
            "expected_sequence": {"type": "integer", "minimum": 1},
            "resolution_delta": {"type": "string", "description": "Targeted planner decision resolving the reported blocker without repeating unchanged contract context."},
        },
        ["run_id", "expected_sequence", "resolution_delta"],
    ),
    _tool(
        "inspect",
        "Read a bounded fragment of an executor artifact only when the compact terminal packet is insufficient. Prefer blocker evidence and normal packet fields; do not inspect full transcripts by default.",
        {
            "run_id": {"type": "string"},
            "artifact": {"type": "string"},
            "offset": {"type": "integer", "minimum": 0, "default": 0},
            "max_chars": {"type": "integer", "minimum": 1, "maximum": 20000, "default": 12000},
        },
        ["run_id", "artifact"],
    ),
    _tool(
        "cancel",
        "Cancel a Harr executor run. A running codex exec child is terminated; a blocked run is closed immediately. Harr never auto-reverts workspace edits.",
        {"run_id": {"type": "string"}},
        ["run_id"],
    ),
]


class Server:
    def __init__(self) -> None:
        self.disabled_in_child = os.environ.get("HARR_EXECUTOR_CHILD") == "1"
        self.service = None if self.disabled_in_child else ExecutorService()

    def handle(self, request: dict[str, Any]) -> dict[str, Any] | None:
        request_id = request.get("id")
        method = request.get("method")
        if method == "server/discover":
            # Deliberately advertise legacy-only behavior. Dual-era clients fall back
            # to initialize; this keeps the tiny dependency-free stdio server stable.
            return self.error(request_id, -32601, "Method not found")
        if method == "initialize":
            return self.result(
                request_id,
                {
                    "protocolVersion": LEGACY_PROTOCOL,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                    "instructions": "Explicit planner-to-executor bridge. Use only after a detailed execution contract exists; executor never replans architecture.",
                },
            )
        if method in {"notifications/initialized", "notifications/cancelled"}:
            return None
        if method == "ping":
            return self.result(request_id, {})
        if method == "tools/list":
            return self.result(request_id, {"tools": [] if self.disabled_in_child else TOOLS})
        if method == "tools/call":
            if self.disabled_in_child:
                return self.tool_error(request_id, "executor bridge is disabled inside an executor child")
            params = request.get("params") or {}
            name = params.get("name")
            arguments = params.get("arguments") or {}
            if not isinstance(arguments, dict):
                return self.error(request_id, -32602, "tool arguments must be an object")
            try:
                value = self.call_tool(str(name), arguments)
            except (KeyError, ValueError, RuntimeError) as exc:
                return self.tool_error(request_id, f"{exc.__class__.__name__}: {exc}")
            except Exception as exc:
                return self.tool_error(request_id, f"unexpected executor bridge error: {exc.__class__.__name__}: {exc}")
            return self.tool_result(request_id, value)
        if request_id is None:
            return None
        return self.error(request_id, -32601, f"Method not found: {method}")

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        assert self.service is not None
        if name == "start":
            return self.service.start(
                repo_root=str(arguments["repo_root"]),
                task_label=str(arguments["task_label"]),
                execution_contract=str(arguments["execution_contract"]),
                allowed_paths=[str(item) for item in arguments["allowed_paths"]],
                required_steps=[str(item) for item in arguments["required_steps"]],
                required_validation=[str(item) for item in arguments["required_validation"]],
            )
        if name == "wait":
            return self.service.wait(
                run_id=str(arguments["run_id"]),
                after_sequence=int(arguments["after_sequence"]),
                timeout_seconds=float(arguments.get("timeout_seconds", 30)),
            )
        if name == "continue":
            return self.service.continue_run(
                run_id=str(arguments["run_id"]),
                expected_sequence=int(arguments["expected_sequence"]),
                resolution_delta=str(arguments["resolution_delta"]),
            )
        if name == "inspect":
            return self.service.inspect(
                run_id=str(arguments["run_id"]),
                artifact=str(arguments["artifact"]),
                offset=int(arguments.get("offset", 0)),
                max_chars=int(arguments.get("max_chars", 12000)),
            )
        if name == "cancel":
            return self.service.cancel(run_id=str(arguments["run_id"]))
        raise ValueError(f"unknown tool: {name}")

    @staticmethod
    def result(request_id: Any, value: Any) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": value}

    @staticmethod
    def error(request_id: Any, code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}

    @staticmethod
    def tool_result(request_id: Any, value: Any) -> dict[str, Any]:
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        return {"jsonrpc": "2.0", "id": request_id, "result": {"content": [{"type": "text", "text": text}], "structuredContent": value, "isError": False}}

    @staticmethod
    def tool_error(request_id: Any, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": {"content": [{"type": "text", "text": message}], "isError": True}}


def main() -> int:
    server = Server()
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                raise ValueError("JSON-RPC request must be an object")
            response = server.handle(request)
        except Exception as exc:
            response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": f"server error: {exc.__class__.__name__}: {exc}"}}
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
