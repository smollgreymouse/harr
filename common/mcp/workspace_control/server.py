#!/usr/bin/env python3
"""Tiny direct MCP for Harr Workspace authority control.

This server intentionally stays outside the LeanCTX gateway: it exists to change the
Workspace authority that LeanCTX itself consumes, so routing it through LeanCTX would
create a bootstrap cycle for not-yet-authorized roots.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import traceback

OUTPUT_LOCK = threading.Lock()


def default_harr() -> str:
    explicit = os.environ.get("HARR_BIN")
    if explicit:
        return explicit
    local = Path.home() / ".local" / "bin" / "harr"
    if local.is_file():
        return str(local)
    return shutil.which("harr") or str(local)


HARR = default_harr()


def emit_result(request_id, value):
    with OUTPUT_LOCK:
        print(json.dumps({"jsonrpc": "2.0", "id": request_id, "result": value}, ensure_ascii=False), flush=True)


def emit_error(request_id, message, code=-32000):
    with OUTPUT_LOCK:
        print(json.dumps({"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": str(message)}}, ensure_ascii=False), flush=True)


def canonical_dir(raw: str, label: str) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"{label} is required")
    path = Path(raw).expanduser().resolve()
    if not path.is_dir():
        raise ValueError(f"{label} is not a directory: {path}")
    return path


def run_harr(project: Path, *args: str) -> dict:
    result = subprocess.run(
        [HARR, "workspace", *args], cwd=project, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45, check=False,
    )
    if result.returncode != 0:
        raise ValueError(result.stderr.strip() or result.stdout.strip() or f"harr workspace {' '.join(args)} failed")
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid Harr workspace JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("Harr workspace response must be a JSON object")
    return value


def workspace_get(project_raw: str) -> dict:
    project = canonical_dir(project_raw, "project")
    return run_harr(project, "show")


def validate_sync_paths(state: dict, raw_paths: list[str]) -> list[str]:
    if not isinstance(raw_paths, list) or not raw_paths:
        raise ValueError("paths must be a non-empty array")
    if len(raw_paths) > 32:
        raise ValueError("paths may contain at most 32 directories")
    primary = canonical_dir(str(state.get("primary", "")), "Workspace primary")
    home = Path.home().resolve()
    accepted: list[str] = []
    for raw in raw_paths:
        target = canonical_dir(raw, "Workspace path")
        if target == Path(target.anchor):
            raise ValueError(f"refusing filesystem root: {target}")
        if target == home:
            raise ValueError(f"refusing user home as Workspace root: {target}")
        if target != primary and primary.is_relative_to(target):
            raise ValueError(f"refusing broad parent of Workspace primary: {target}")
        if str(target) in accepted:
            raise ValueError(f"refusing duplicate Workspace path in one request: {target}")
        accepted.append(str(target))
    return accepted


def workspace_sync(project_raw: str, raw_paths: list[str]) -> dict:
    project = canonical_dir(project_raw, "project")
    before = run_harr(project, "show")
    paths = validate_sync_paths(before, raw_paths)
    result = run_harr(project, "sync", *paths)
    return {"beforeRevision": int(before.get("revision", 0)), **result}


def tools() -> list[dict]:
    return [
        {
            "name": "workspace_get",
            "description": "Read the Harr Workspace selected by an explicit current project directory.",
            "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
            "inputSchema": {"type": "object", "properties": {"project": {"type": "string"}}, "required": ["project"], "additionalProperties": False},
        },
        {
            "name": "workspace_sync",
            "description": "Add already-known working directories from the current agent session to Harr Workspace. Add-only; never removes roots. Rejects filesystem root, user HOME and broad parents of the primary root. This does not grant access to an already-running rootless LeanCTX process; restart/reconnect LeanCTX with HARR_WORKSPACE_ROOT set to the explicit primary root.",
            "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
            "inputSchema": {
                "type": "object",
                "properties": {
                    "project": {"type": "string"},
                    "paths": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 32},
                },
                "required": ["project", "paths"],
                "additionalProperties": False,
            },
        },
        {
            "name": "workspace_owner_get",
            "description": "Read the cooperative owner note of a registered Workspace checkout. Read-only; never creates or reconciles a Workspace.",
            "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
            "inputSchema": {
                "type": "object",
                "properties": {"project": {"type": "string"}, "root": {"type": "string"}},
                "required": ["project", "root"],
                "additionalProperties": False,
            },
        },
        {
            "name": "workspace_owner_claim",
            "description": "Claim or update the cooperative owner note of a registered checkout for one task identity. If another task holds it, returns confirmation_required: ask the user first, then re-claim with take_over_from set to the shown owner_id. This is a note, not a lease or lock.",
            "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
            "inputSchema": {
                "type": "object",
                "properties": {
                    "project": {"type": "string"},
                    "root": {"type": "string"},
                    "owner_id": {"type": "string", "description": "Stable task identifier reused across calls of this task"},
                    "owner_label": {"type": "string"},
                    "take_over_from": {"type": "string", "description": "owner_id shown by the previous claim/get; asserts the user already agreed to the transfer"},
                },
                "required": ["project", "root", "owner_id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "workspace_owner_release",
            "description": "Remove your own owner note from a registered checkout at the end of a task. Another task's note is never removed.",
            "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
            "inputSchema": {
                "type": "object",
                "properties": {
                    "project": {"type": "string"},
                    "root": {"type": "string"},
                    "owner_id": {"type": "string"},
                },
                "required": ["project", "root", "owner_id"],
                "additionalProperties": False,
            },
        },
    ]


def warning_text(payload: dict) -> str:
    warnings = payload.get("warnings")
    if not isinstance(warnings, list) or not warnings:
        return ""
    lines = []
    for warning in warnings:
        if not isinstance(warning, dict):
            continue
        message = warning.get("message")
        command = warning.get("remove_command")
        if not isinstance(message, str):
            continue
        if isinstance(command, str):
            lines.append(f"WARNING: {message} Remove with: {command}")
        else:
            lines.append(f"WARNING: {message}")
    return "\n" + "\n".join(lines) if lines else ""


def tool_result(payload: dict, text: str) -> dict:
    return {"content": [{"type": "text", "text": text + warning_text(payload)}], "structuredContent": payload}


def owner_get(project_raw: str, root_raw: str) -> dict:
    project = canonical_dir(project_raw, "project")
    root = str(Path(root_raw).expanduser().resolve(strict=False))
    return run_harr(project, "owner", "get", root, "--project", str(project))


def owner_claim(
    project_raw: str,
    root_raw: str,
    owner_id: str,
    owner_label: str | None,
    take_over_from: str | None,
) -> dict:
    project = canonical_dir(project_raw, "project")
    root = str(Path(root_raw).expanduser().resolve(strict=False))
    args = ["owner", "claim", root, "--project", str(project), "--owner-id", str(owner_id)]
    if owner_label:
        args += ["--owner-label", str(owner_label)]
    if take_over_from:
        args += ["--take-over-from", str(take_over_from)]
    return run_harr(project, *args)


def owner_release(project_raw: str, root_raw: str, owner_id: str) -> dict:
    project = canonical_dir(project_raw, "project")
    root = str(Path(root_raw).expanduser().resolve(strict=False))
    return run_harr(project, "owner", "release", root, "--project", str(project), "--owner-id", str(owner_id))


def owner_text(payload: dict) -> str:
    owner = payload.get("owner") or {}
    status = payload.get("status")
    if status == "claimed":
        return f"Owner note claimed for {payload.get('root')}."
    if status == "reclaimed":
        return f"Owner note updated for {payload.get('root')} (same task identity)."
    if status == "confirmation_required":
        current = owner.get("owner_id")
        label = owner.get("owner_label") or current
        seen = owner.get("last_seen_at")
        return (
            f"Checkout {payload.get('root')} is already noted for task '{label}' "
            f"(owner_id={current}, last seen {seen}). Ask the user before taking over; "
            f"then re-claim with take_over_from={current}."
        )
    if status == "transferred":
        note = payload.get("note") or ""
        return note or f"Owner note transferred for {payload.get('root')}."
    if status == "owner_changed":
        current = owner.get("owner_id")
        return (
            f"The owner note changed while you were asking: it now belongs to "
            f"owner_id={current} ({owner.get('owner_label')}). Re-run get and ask the user again."
        )
    if status == "released":
        return f"Owner note removed from {payload.get('root')}."
    if status == "not_owner":
        return (
            f"owner_id does not own the note on {payload.get('root')}; "
            "only the owning task may release it."
        )
    if status == "absent":
        return f"No owner note on {payload.get('root')}."
    return json.dumps(payload, ensure_ascii=False)


def dispatch(request: dict) -> None:
    request_id = request.get("id")
    if request_id is None:
        return
    method = request.get("method")
    params = request.get("params") or {}
    try:
        if method == "initialize":
            emit_result(request_id, {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}, "serverInfo": {"name": "harr-workspace", "version": "0.1"}})
        elif method == "tools/list":
            emit_result(request_id, {"tools": tools()})
        elif method == "tools/call":
            name = params.get("name")
            args = params.get("arguments") or {}
            if name == "workspace_get":
                state = workspace_get(args.get("project"))
                emit_result(request_id, tool_result(state, f"Harr Workspace revision {state.get('revision', 0)}"))
            elif name == "workspace_sync":
                state = workspace_sync(args.get("project"), args.get("paths"))
                sync = state.get("sync") or {}
                emit_result(request_id, tool_result(state, f"Harr Workspace sync added {len(sync.get('added') or [])} root(s)"))
            elif name == "workspace_owner_get":
                payload = owner_get(args.get("project"), args.get("root"))
                owner = payload.get("owner") or {}
                if owner:
                    text = (
                        f"Checkout {payload.get('root')} is noted for task "
                        f"'{owner.get('owner_label') or owner.get('owner_id')}' "
                        f"(owner_id={owner.get('owner_id')}, last seen {owner.get('last_seen_at')})."
                    )
                else:
                    text = f"No owner note on {payload.get('root')}."
                emit_result(request_id, tool_result(payload, text))
            elif name == "workspace_owner_claim":
                payload = owner_claim(
                    args.get("project"),
                    args.get("root"),
                    args.get("owner_id"),
                    args.get("owner_label"),
                    args.get("take_over_from"),
                )
                emit_result(request_id, tool_result(payload, owner_text(payload)))
            elif name == "workspace_owner_release":
                payload = owner_release(args.get("project"), args.get("root"), args.get("owner_id"))
                emit_result(request_id, tool_result(payload, owner_text(payload)))
            else:
                emit_error(request_id, "unknown tool", -32601)
        elif method == "ping":
            emit_result(request_id, {})
        else:
            emit_error(request_id, "unsupported method", -32601)
    except Exception as exc:
        emit_error(request_id, str(exc))
        print(traceback.format_exc(), file=sys.stderr, flush=True)


def main() -> None:
    for line in sys.stdin:
        try:
            request = json.loads(line)
            threading.Thread(target=dispatch, args=(request,), daemon=True).start()
        except Exception:
            print(traceback.format_exc(), file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
