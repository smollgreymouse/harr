#!/usr/bin/env python3
"""Harr Workspace MCP App backed by the local revisioned Workspace store."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import traceback

MCP_DIR = Path(__file__).resolve().parents[1]
if str(MCP_DIR) not in sys.path:
    sys.path.insert(0, str(MCP_DIR))
from workspace_control.server import validate_sync_paths

URI = "ui://harr-workspace/panel.html"
HTML = Path(__file__).with_name("panel.html").read_text(encoding="utf-8")
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


def canonical_project(raw: str) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("project is required")
    project = Path(raw).expanduser().resolve()
    if not project.is_dir():
        raise ValueError(f"project is not a directory: {project}")
    return project


def run_workspace(project: Path, *args: str):
    result = subprocess.run(
        [HARR, "workspace", *args], cwd=project, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=40, check=False,
    )
    if result.returncode != 0:
        raise ValueError(result.stderr.strip() or result.stdout.strip() or f"harr workspace {' '.join(args)} failed")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid Harr workspace JSON: {exc}") from exc


def root_row(path: str, kind: str) -> dict:
    p = Path(path)
    status = "OK" if p.is_dir() else "missing"
    return {"path": path, "kind": kind, "status": status}


def normalize_snapshot(raw: dict, project: Path) -> dict:
    primary = str(raw.get("primary", ""))
    additional = [str(x) for x in raw.get("additional", []) if isinstance(x, str)]
    return {
        "workspaceId": str(raw.get("id", "")),
        "name": Path(primary).name if primary else "Workspace",
        "project": str(project),
        "primary": primary,
        "revision": int(raw.get("revision", 0)),
        "additional": additional,
        "roots": [root_row(primary, "primary")] + [root_row(path, "additional") for path in additional],
        "notice": "LeanCTX root inclusion does not grant Codex filesystem read/write permission.",
    }


def current_snapshot(project_raw: str) -> dict:
    project = canonical_project(project_raw)
    return normalize_snapshot(run_workspace(project, "show"), project)


def project_schema() -> dict:
    return {"type": "string", "description": "Absolute current project/workspace root for this Codex thread."}


def tools() -> list[dict]:
    app_only = {"ui": {"visibility": ["app"]}}
    return [
        {
            "name": "show_harr_workspace",
            "description": "Open the Harr Workspace panel for the current project. Pass the absolute current project root. Read-only for the model; mutations happen only through the app UI.",
            "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
            "inputSchema": {"type": "object", "properties": {"project": project_schema()}, "required": ["project"], "additionalProperties": False},
            "_meta": {"ui": {"resourceUri": URI, "visibility": ["model", "app"]}, "ui/resourceUri": URI, "openai/outputTemplate": URI},
        },
        {
            "name": "workspace_ui_get",
            "description": "App-only current Workspace snapshot for an explicit project.",
            "inputSchema": {"type": "object", "properties": {"project": project_schema()}, "required": ["project"], "additionalProperties": False},
            "_meta": app_only,
        },
        {
            "name": "workspace_ui_add_root",
            "description": "App-only CAS add of an additional Workspace root.",
            "inputSchema": {"type": "object", "properties": {"project": project_schema(), "path": {"type": "string"}, "expected_revision": {"type": "integer", "minimum": 1}}, "required": ["project", "path", "expected_revision"], "additionalProperties": False},
            "_meta": app_only,
        },
        {
            "name": "workspace_ui_remove_root",
            "description": "App-only CAS removal of an additional Workspace root.",
            "inputSchema": {"type": "object", "properties": {"project": project_schema(), "path": {"type": "string"}, "expected_revision": {"type": "integer", "minimum": 1}}, "required": ["project", "path", "expected_revision"], "additionalProperties": False},
            "_meta": app_only,
        },
    ]


def tool_result(payload: dict, *, text: str = "UI-only Workspace operation completed", with_ui: bool = False) -> dict:
    result = {"content": [{"type": "text", "text": text}], "structuredContent": payload}
    if with_ui:
        result["_meta"] = {"ui": {"resourceUri": URI}, "ui/resourceUri": URI, "openai/outputTemplate": URI}
    return result


def dispatch(request: dict) -> None:
    request_id = request.get("id")
    if request_id is None:
        return
    method = request.get("method")
    params = request.get("params") or {}
    try:
        if method == "initialize":
            emit_result(request_id, {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}, "resources": {}}, "serverInfo": {"name": "harr-workspace-app", "version": "0.2"}})
        elif method == "tools/list":
            emit_result(request_id, {"tools": tools()})
        elif method == "tools/call":
            name = params.get("name")
            args = params.get("arguments") or {}
            if name == "show_harr_workspace":
                snapshot = current_snapshot(args.get("project"))
                visible = f"Harr Workspace {snapshot['name']}: revision {snapshot['revision']}, {len(snapshot['additional'])} additional root(s)."
                emit_result(request_id, tool_result(snapshot, text=visible, with_ui=True))
            elif name == "workspace_ui_get":
                emit_result(request_id, tool_result(current_snapshot(args.get("project"))))
            elif name in {"workspace_ui_add_root", "workspace_ui_remove_root"}:
                project = canonical_project(args.get("project"))
                path = args.get("path")
                expected = args.get("expected_revision")
                if not isinstance(path, str) or not path.strip():
                    raise ValueError("path is required")
                if not isinstance(expected, int) or expected < 1:
                    raise ValueError("expected_revision must be a positive integer")
                operation = "add" if name.endswith("add_root") else "remove"
                if operation == "add":
                    validate_sync_paths(run_workspace(project, "show"), [path])
                run_workspace(project, operation, path, "--expected-revision", str(expected))
                emit_result(request_id, tool_result(current_snapshot(str(project))))
            else:
                emit_error(request_id, "unknown tool", -32601)
        elif method == "resources/read":
            if params.get("uri") != URI:
                raise ValueError("unknown resource")
            emit_result(request_id, {"contents": [{"uri": URI, "mimeType": "text/html;profile=mcp-app", "text": HTML}]})
        elif method == "resources/list":
            emit_result(request_id, {"resources": [{"uri": URI, "name": "Harr Workspace", "mimeType": "text/html;profile=mcp-app"}]})
        elif method == "resources/templates/list":
            emit_result(request_id, {"resourceTemplates": []})
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
