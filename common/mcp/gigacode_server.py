#!/usr/bin/env python3
"""Minimal stdio MCP server exposing persistent GigaCode execution.

The MCP boundary is intentionally narrow:
- action=start: launch a detached persistent GigaCode session from plan_path or prompt.
- action=resume: launch a detached continuation of that same session.
- action=status: read progress or the final handoff without waiting.

GigaCode must return a planner-ready structured handoff. In particular,
ESCALATE responses contain enough code evidence for the planner to decide
what to do next without reopening the source merely to rediscover the mismatch.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import uuid
import re
from collections import deque


SERVER_NAME = "gigacode"
SERVER_VERSION = "1.10.0"
ROOT = Path.cwd().resolve()
DEFAULT_HARD_TIMEOUT_SEC = 0
DEFAULT_STALL_TIMEOUT_SEC = 0
DEFAULT_WAIT_TIMEOUT_SEC = 1500
MAX_WAIT_TIMEOUT_SEC = 1500
WAIT_POLL_INTERVAL_SEC = 1.0
STARTUP_CONFIRM_TIMEOUT_SEC = 20.0
STARTUP_CONFIRM_POLL_SEC = 0.25
POLL_INTERVAL_SEC = 5.0
WORKSPACE_KEY = hashlib.sha256(str(ROOT).encode("utf-8")).hexdigest()[:12]
CACHE_ROOT = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "gigacode-mcp" / WORKSPACE_KEY
CACHE_ROOT.mkdir(parents=True, exist_ok=True)

# Regex: canonical UUID hex format only
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def _validate_session_id(session_id: object) -> str | None:
    """Return session_id if it is a valid canonical UUID string, else None.

    Rejects empty strings, non-strings, path separators, relative components,
    drive letters, and every non-UUID pattern.
    """
    if not isinstance(session_id, str):
        return None
    m = _UUID_RE.fullmatch(session_id)
    if m is None:
        return None
    return session_id

WORKER_CONTRACT = r"""
You are an implementation worker. The caller is a more capable planner and owns
architecture, root-cause decisions, scope changes, and ambiguous design choices.

Your job is to execute an already-decided plan faithfully and cheaply.

Before editing:
1. Read the complete plan.
2. Read only enough repository code to validate the plan's important anchors,
   symbols, call paths, and assumptions.
3. If a material plan assumption does not match the code, STOP BEFORE EDITING
   and return ESCALATE. Do not redesign the solution yourself.

During implementation:
- Stay inside the plan's scope and design.
- Do not perform unrelated cleanup.
- Run the validation requested by the plan.
- Before DONE, perform your own final acceptance pass: map every acceptance
  criterion to a concrete verification result, inspect the final diff/scope for
  unrelated changes, and identify anything still unverified.
- Do not commit, push, or make external writes unless the plan explicitly says so.
- If an unexpected architectural contradiction appears after edits have begun,
  stop making further changes and return ESCALATE. Report every file already changed;
  do not silently revert or broaden the design.
- Ordinary local implementation mistakes that can be fixed without changing the
  plan are yours to fix; do not escalate trivial syntax/test errors.
- Use your normal execution capabilities. The bridge does not prescribe or
  depend on your internal tools, MCP servers, shell implementation, or editor.
- Keep long-running validation bounded. Do not enter sleep/poll loops, launch
  duplicate expensive work merely to wait, or repeatedly probe output just for
  progress. If validation cannot complete in this turn, preserve completed edits
  and return FAILED with the unfinished check and the evidence already gathered.

The final response MUST be exactly one JSON object and no Markdown fences or
surrounding prose. Use this schema:

{
  "status": "DONE" | "ESCALATE" | "FAILED",
  "summary": "short planner-facing summary",
  "changed": [
    {"path": "relative/path", "what": "specific change"}
  ],
  "verified": [
    {
      "criterion": "acceptance criterion id or short statement",
      "check": "command or invariant checked",
      "result": "PASS" | "FAIL",
      "evidence": "compact decisive evidence including exit/result when applicable"
    }
  ],
  "self_review": {
    "criteria_complete": true | false,
    "diff_scope_clean": true | false,
    "unverified": ["criterion or limitation still not proven"]
  },
  "escalation": null | {
    "kind": "plan_code_mismatch" | "ambiguous_design" | "scope_conflict" | "unexpected_architecture" | "validation_contradiction" | "other",
    "expected": "what the plan assumed or required",
    "observed": "what the repository actually contains or does",
    "evidence": [
      {
        "path": "relative/path",
        "symbol": "symbol/function/type or null",
        "lines": "line/range if known, else null",
        "fact": "precise code fact that proves the mismatch",
        "snippet": "minimal decisive code excerpt, preferably <= 8 lines, or null"
      }
    ],
    "impact": "why continuing would require changing the plan or architecture",
    "decision_needed": "one concrete decision/question the planner must resolve",
    "options": [
      {"option": "possible next direction", "consequence": "what choosing it changes"}
    ]
  },
  "blockers": [
    {"kind": "tool|build|test|environment|permission|other", "detail": "specific blocker", "evidence": "relevant compact output"}
  ]
}

Rules for the handoff:
- DONE: escalation must be null; blockers and self_review.unverified must be
  empty; every acceptance criterion must appear in verified with result=PASS;
  self_review.criteria_complete and self_review.diff_scope_clean must both be true.
- ESCALATE: provide enough evidence for the planner to reason without rereading
  the cited source just to understand the mismatch. Prefer exact symbols,
  paths, line ranges, and a tiny decisive snippet. State expected vs observed,
  impact, and the exact decision needed. Do not dump whole files.
- ESCALATE options must be neutral decision branches grounded in observed facts.
  Do NOT invent missing behavior, APIs, algorithms, data, target symbols, or
  implementation details. If a corrected design/target is unknown, say that the
  planner must provide it rather than proposing a plausible substitute.
- FAILED: use for execution/tool/environment failures that do not require an
  architectural decision. Include the failed command/check and compact evidence.
- For verification commands, include the exit/result outcome. Do not make the
  parent rerun a check merely to know whether it passed.
- Keep the whole JSON compact. Evidence should be sufficient, not exhaustive.
- Never claim a check passed unless you actually performed it.
""".strip()


TOOLS = [
    {
        "name": "gigacode",
        "description": (
            "Delegate execution to persistent GigaCode as a detached job. action=start and "
            "action=resume perform a short startup handshake and return RUNNING only after actual "
            "GigaCode model/tool activity is observed; otherwise they return STARTING or FAILED. "
            "action=status is a compact nonblocking public state read returning RUNNING or the final "
            "DONE/FAILED/ESCALATE handoff without exposing executor event history. "
            "action=messages returns only GigaCode assistant prose from the recorded session, never "
            "tool calls/results or runtime/debug events. "
            "action=wait blocks inside the MCP bridge until terminal state or a bounded wait timeout, "
            "so the parent model does not wake for polling. "
            "hard_timeout_sec=0 means unlimited and stall_elapsed_sec is informational. "
            "action=cancel requests orderly termination of a running detached job. "
            "plan_path avoids resending an existing plan."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["start", "resume", "status", "messages", "wait", "cancel"],
                    "description": "start/resume are nonblocking; status is an immediate snapshot; messages returns assistant prose; wait blocks for terminal state up to wait_timeout_sec; cancel requests orderly termination.",
                },
                "plan_path": {
                    "type": "string",
                    "description": "For start: existing implementation plan path inside the workspace. Use either plan_path or prompt, not both.",
                },
                "session_id": {
                    "type": "string",
                    "description": "For resume/cancel/status/messages/wait: session id returned by a prior start.",
                },
                "prompt": {
                    "type": "string",
                    "description": "For start: direct task when no plan file exists. For resume: only new planner decision/correction/evidence.",
                },
                "timeout_sec": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "For start/resume: optional hard wall-clock limit in seconds. 0 (default) means unlimited. Any nonnegative integer accepted.",
                },
                "wait_timeout_sec": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 1500,
                    "description": "For wait: maximum seconds to block inside the bridge. Default 1500. A timeout returns compact RUNNING; it does not cancel GigaCode.",
                },
                "after_revision": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "For messages: return assistant messages newer than this revision. Omit to return the latest messages.",
                },
                "message_limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 50,
                    "description": "For messages: maximum number of assistant messages to return. Default 8.",
                },
            },
            "required": ["action"],
            "additionalProperties": False,
        },
    },
]


def emit(message: dict) -> None:
    sys.stdout.write(json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def error_response(request_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def text_result(payload: dict, *, is_error: bool = False) -> dict:
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    result = {
        "content": [{"type": "text", "text": text}],
        "structuredContent": payload,
    }
    if is_error:
        result["isError"] = True
    return result


def resolve_plan(plan_arg: str) -> Path:
    path = Path(plan_arg)
    if not path.is_absolute():
        path = ROOT / path
    path = path.resolve()

    try:
        path.relative_to(ROOT)
    except ValueError as exc:
        raise ValueError("plan_path must stay inside the workspace root") from exc

    if not path.is_file():
        raise ValueError(f"plan file does not exist: {plan_arg}")
    return path


def _state_path(session_id: str) -> Path:
    return CACHE_ROOT / f"{session_id}.state.json"


def _runtime_log_path(session_id: str) -> Path:
    return CACHE_ROOT / f"{session_id}.runtime.log"


def _append_runtime_log(session_id: str, message: str) -> None:
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with _runtime_log_path(session_id).open("a", encoding="utf-8") as handle:
        handle.write(f"{stamp} {message}\n")


def _write_state(session_id: str, payload: dict) -> None:
    target = _state_path(session_id)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    tmp.replace(target)


def _load_state(session_id: str) -> dict | None:
    path = _state_path(session_id)
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def _find_chat_path(session_id: str) -> Path | None:
    base = Path.home() / ".gigacode" / "projects"
    if not base.is_dir():
        return None
    for candidate in base.glob(f"*/chats/{session_id}.jsonl"):
        if candidate.is_file():
            return candidate
    return None


def _chat_size(session_id: str) -> int:
    path = _find_chat_path(session_id)
    if path is None:
        return 0
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _activity_after_offset(session_id: str, offset: int) -> dict | None:
    """Return the first meaningful GigaCode activity appended after offset."""
    path = _find_chat_path(session_id)
    if path is None:
        return None
    try:
        size = path.stat().st_size
        if size <= offset:
            return None
        with path.open("r", encoding="utf-8") as handle:
            if offset:
                handle.seek(offset)
                handle.readline()  # discard a possible partial line
            for line in handle:
                try:
                    item = json.loads(line)
                except Exception:
                    continue
                timestamp = item.get("timestamp")
                kind = item.get("type")

                if kind == "assistant":
                    parts = item.get("message", {}).get("parts", [])
                    # Prefer a concrete requested tool call over accompanying prose.
                    for part in parts:
                        if not isinstance(part, dict):
                            continue
                        call = part.get("functionCall")
                        if isinstance(call, dict):
                            return {
                                "timestamp": timestamp,
                                "kind": "tool_call_requested",
                                "tool": call.get("name"),
                            }
                    for part in parts:
                        if not isinstance(part, dict):
                            continue
                        text = part.get("text")
                        if isinstance(text, str) and text.strip():
                            return {
                                "timestamp": timestamp,
                                "kind": "assistant_output",
                                "text": text.replace("\n", " ").strip()[:240],
                            }

                if kind == "system":
                    event = item.get("systemPayload", {}).get("uiEvent", {})
                    event_name = event.get("event.name")
                    if event_name == "gigacode.api_response":
                        # API transport activity alone is not enough to claim that
                        # the worker started executing the task. Wait for assistant
                        # output or a requested/executed tool call.
                        continue
                    if event_name == "gigacode.tool_call":
                        return {
                            "timestamp": timestamp,
                            "kind": "tool_executed",
                            "tool": event.get("function_name"),
                            "status": event.get("status"),
                        }

                if kind == "tool_result":
                    parts = item.get("message", {}).get("parts", [])
                    for part in parts:
                        if not isinstance(part, dict):
                            continue
                        response = part.get("functionResponse")
                        if isinstance(response, dict):
                            return {
                                "timestamp": timestamp,
                                "kind": "tool_result",
                                "tool": response.get("name"),
                            }
    except OSError:
        return None
    return None


def _assistant_messages(session_id: str) -> list[dict]:
    """Return only user-visible assistant prose from the recorded GigaCode chat.

    Revisions are monotonic within the append-only chat transcript. Tool calls,
    tool results, system/runtime events, and empty text parts are deliberately
    excluded.
    """
    path = _find_chat_path(session_id)
    if path is None:
        return []

    messages: list[dict] = []
    revision = 0
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    item = json.loads(line)
                except Exception:
                    continue
                if item.get("type") != "assistant":
                    continue
                timestamp = item.get("timestamp")
                parts = item.get("message", {}).get("parts", [])
                for part in parts:
                    if not isinstance(part, dict):
                        continue
                    text = part.get("text")
                    if not isinstance(text, str):
                        continue
                    text = text.strip()
                    if not text:
                        continue
                    revision += 1
                    messages.append({
                        "revision": revision,
                        "timestamp": timestamp,
                        "text": text,
                    })
    except OSError:
        return []
    return messages


def _tail_chat_events(session_id: str, limit: int = 12) -> list[dict]:
    path = _find_chat_path(session_id)
    if path is None:
        return []

    lines: deque[str] = deque(maxlen=120)
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                lines.append(line)
    except OSError:
        return []

    events: list[dict] = []
    for line in lines:
        try:
            item = json.loads(line)
        except Exception:
            continue
        timestamp = item.get("timestamp")
        kind = item.get("type")
        summary = None

        if kind == "assistant":
            parts = item.get("message", {}).get("parts", [])
            labels = []
            for part in parts:
                call = part.get("functionCall") if isinstance(part, dict) else None
                if isinstance(call, dict):
                    labels.append(f"call:{call.get('name', '?')}")
                elif isinstance(part, dict) and isinstance(part.get("text"), str):
                    text = part["text"].replace("\n", " ").strip()
                    if text:
                        labels.append("text:" + text[:180])
            if labels:
                summary = " | ".join(labels[:4])

        elif kind == "system":
            event = item.get("systemPayload", {}).get("uiEvent", {})
            event_name = event.get("event.name")
            if event_name in {"gigacode.api_response", "gigacode.tool_call"}:
                summary = (
                    f"{event_name}:{event.get('function_name', '')} "
                    f"status={event.get('status', '')} duration_ms={event.get('duration_ms', '')}"
                )

        elif kind == "tool_result":
            parts = item.get("message", {}).get("parts", [])
            labels = []
            for part in parts:
                response = part.get("functionResponse") if isinstance(part, dict) else None
                if isinstance(response, dict):
                    output = str(response.get("response", {}).get("output", ""))
                    labels.append(
                        f"result:{response.get('name', '?')} "
                        + output.replace("\n", " ")[:180]
                    )
            if labels:
                summary = " | ".join(labels[:3])

        if summary:
            events.append({"timestamp": timestamp, "event": summary})

    return events[-limit:]


def _pid_alive(pid: object) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False

    if os.name == "nt":
        import ctypes

        process_query_limited_information = 0x1000
        still_active = 259
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return False
            return exit_code.value == still_active
        finally:
            kernel32.CloseHandle(handle)

    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def status_tool(arguments: dict) -> dict:
    raw_sid = arguments.get("session_id")
    session_id = _validate_session_id(raw_sid)
    if session_id is None:
        return text_result({
            "session_id": raw_sid if isinstance(raw_sid, str) else "",
            "status": "FAILED",
            "summary": "status requires a valid UUID session_id.",
        }, is_error=True)
    state = _load_state(session_id)

    if state and isinstance(state.get("handoff"), dict):
        handoff = state["handoff"]
        payload = {
            "session_id": session_id,
            **handoff,
            "runtime": {
                "phase": state.get("phase"),
                "job_id": state.get("job_id"),
                "elapsed_sec": state.get("elapsed_sec"),
                "exit_code": state.get("exit_code"),
            },
        }
        return text_result(payload)

    if state is None:
        return text_result({
            "session_id": session_id,
            "status": "UNKNOWN",
            "summary": "No detached runtime state exists for this session.",
        })

    process_running = _pid_alive(state.get("pid")) or _pid_alive(state.get("worker_pid"))
    phase = state.get("phase", "unknown")

    if phase in {"queued", "running", "completed", "cancelled"} and not process_running:
        payload = {
            "session_id": session_id,
            "status": "FAILED",
            "summary": "Detached GigaCode job stopped without a final handoff.",
            "changed": [],
            "verified": [],
            "escalation": None,
            "blockers": [{
                "kind": "tool",
                "detail": "worker process is no longer running but runtime state is unfinished",
                "evidence": f"phase={phase}; job_id={state.get('job_id')}",
            }],
            "runtime": {
                "phase": phase,
                "elapsed_sec": state.get("elapsed_sec"),
            },
        }
        return text_result(payload, is_error=True)

    job_id = state.get("job_id")
    cancel_check = bool(job_id) and _check_cancel_request(session_id, job_id)
    payload = {
        "session_id": session_id,
        "status": "RUNNING",
        "summary": "GigaCode is still executing the delegated task.",
        "runtime": {
            "phase": phase,
            "elapsed_sec": state.get("elapsed_sec"),
            "timeout_sec": state.get("timeout_sec"),
            "hard_timeout_sec": state.get("hard_timeout_sec", state.get("timeout_sec")),
            "stall_elapsed_sec": state.get("stall_elapsed_sec"),
            "cancel_requested": cancel_check,
            "process_running": process_running,
        },
    }
    return text_result(payload)


def messages_tool(arguments: dict) -> dict:
    raw_sid = arguments.get("session_id")
    session_id = _validate_session_id(raw_sid)
    if session_id is None:
        return text_result({
            "session_id": raw_sid if isinstance(raw_sid, str) else "",
            "status": "FAILED",
            "summary": "messages requires a valid UUID session_id.",
        }, is_error=True)

    messages = _assistant_messages(session_id)
    latest_revision = messages[-1]["revision"] if messages else 0
    limit = int(arguments.get("message_limit", 8))
    after_revision = arguments.get("after_revision")

    if after_revision is None:
        selected = messages[-limit:]
        next_revision = latest_revision
        has_more = False
    else:
        selected = [item for item in messages if item["revision"] > after_revision][:limit]
        next_revision = selected[-1]["revision"] if selected else int(after_revision)
        has_more = latest_revision > next_revision

    return text_result({
        "session_id": session_id,
        "status": "MESSAGES",
        "revision": next_revision,
        "latest_revision": latest_revision,
        "has_more": has_more,
        "messages": selected,
    })


def wait_tool(arguments: dict) -> dict:
    raw_sid = arguments.get("session_id")
    session_id = _validate_session_id(raw_sid)
    if session_id is None:
        return text_result({
            "session_id": raw_sid if isinstance(raw_sid, str) else "",
            "status": "FAILED",
            "summary": "wait requires a valid UUID session_id.",
        }, is_error=True)

    wait_timeout_sec = int(arguments.get("wait_timeout_sec", DEFAULT_WAIT_TIMEOUT_SEC))
    deadline = time.monotonic() + wait_timeout_sec
    started = time.monotonic()

    while True:
        result = status_tool({"session_id": session_id})
        payload = json.loads(result["content"][0]["text"])
        if payload.get("status") != "RUNNING":
            return result

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            payload["wait"] = {
                "timed_out": True,
                "waited_sec": round(time.monotonic() - started, 1),
            }
            payload["summary"] = (
                "GigaCode is still executing after the bounded MCP wait. "
                "The job continues in the background."
            )
            return text_result(payload)

        time.sleep(min(WAIT_POLL_INTERVAL_SEC, remaining))


def _new_process_group_kwargs() -> dict:
    if os.name == "nt":
        return {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
    return {"start_new_session": True}


def _terminate_process_tree(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return

    if os.name == "nt":
        process.terminate()
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return

    try:
        process.wait(timeout=5)
        return
    except subprocess.TimeoutExpired:
        pass

    if os.name == "nt":
        taskkill = shutil.which("taskkill")
        if taskkill:
            subprocess.run(
                [taskkill, "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        else:
            process.kill()
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            return

    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass


def run_gigacode(
    session_id: str,
    session_args: list[str],
    prompt: str,
    timeout_sec: int,
    job_id: str | None = None,
) -> tuple[int, str, str]:
    executable = shutil.which("gigacode")
    if not executable:
        return 127, "", "gigacode executable not found in PATH"

    command = [
        executable,
        "--chat-recording",
        *session_args,
        "--approval-mode",
        "auto-edit",
        "--append-system-prompt",
        WORKER_CONTRACT,
        "--output-format",
        "text",
        prompt,
    ]

    turn_key = f"{int(time.time())}-{uuid.uuid4().hex[:6]}"
    stdout_path = CACHE_ROOT / f"{session_id}.{turn_key}.stdout"
    stderr_path = CACHE_ROOT / f"{session_id}.{turn_key}.stderr"
    started_epoch = time.time()
    started_monotonic = time.monotonic()

    _append_runtime_log(
        session_id,
        f"START turn={turn_key} timeout_sec={timeout_sec} cwd={ROOT}",
    )

    with stdout_path.open("w", encoding="utf-8") as stdout_handle, stderr_path.open(
        "w", encoding="utf-8"
    ) as stderr_handle:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            text=True,
            stdout=stdout_handle,
            stderr=stderr_handle,
            env=os.environ.copy(),
            **_new_process_group_kwargs(),
        )

        last_logged_chat_size = -1
        last_progress_monotonic = started_monotonic
        while process.poll() is None:
            elapsed = time.monotonic() - started_monotonic
            chat_path = _find_chat_path(session_id)
            chat_size = None
            chat_age = None
            if chat_path is not None:
                try:
                    stat = chat_path.stat()
                    chat_size = stat.st_size
                    chat_age = round(max(0.0, time.time() - stat.st_mtime), 1)
                except OSError:
                    pass

            state = {
                "phase": "running",
                "session_id": session_id,
                "job_id": job_id,
                "turn": turn_key,
                "pid": process.pid,
                "worker_pid": os.getpid(),
                "cwd": str(ROOT),
                "started_epoch": started_epoch,
                "elapsed_sec": round(elapsed, 1),
                "timeout_sec": timeout_sec,
                "chat_path": str(chat_path) if chat_path else None,
                "chat_size": chat_size,
                "chat_age_sec": chat_age,
                "stdout_path": str(stdout_path),
                "stderr_path": str(stderr_path),
            }

            if chat_size is not None and chat_size != last_logged_chat_size:
                _append_runtime_log(
                    session_id,
                    f"PROGRESS turn={turn_key} elapsed={elapsed:.1f}s chat_size={chat_size} chat_age={chat_age}",
                )
                last_logged_chat_size = chat_size
                last_progress_monotonic = time.monotonic()

            stall_elapsed = time.monotonic() - last_progress_monotonic
            state["stall_elapsed_sec"] = round(stall_elapsed, 1)
            state["stall_timeout_sec"] = DEFAULT_STALL_TIMEOUT_SEC
            state["hard_timeout_sec"] = timeout_sec
            _write_state(session_id, state)

            # Log informative stall message but never kill for inactivity
            if DEFAULT_STALL_TIMEOUT_SEC > 0 and stall_elapsed >= DEFAULT_STALL_TIMEOUT_SEC:
                _append_runtime_log(
                    session_id,
                    f"STALL turn={turn_key} no_progress={stall_elapsed:.1f}s (informational, not killed)",
                )

            # Check for external cancel request
            if job_id is not None and _check_cancel_request(session_id, job_id):
                _append_runtime_log(
                    session_id,
                    f"CANCEL turn={turn_key} job={job_id} pid={process.pid}",
                )
                _terminate_process_tree(process)
                stdout_handle.flush()
                stderr_handle.flush()
                output = stdout_path.read_text(encoding="utf-8", errors="replace").strip()
                stderr = stderr_path.read_text(encoding="utf-8", errors="replace").strip()
                events = _tail_chat_events(session_id)
                cancel_summary = (
                    f"GigaCode was manually cancelled by the planner. "
                    f"Session remains resumable: {session_id}. "
                    f"Last events: {json.dumps(events[-5:], ensure_ascii=False)}"
                )
                _write_state(
                    session_id,
                    {
                        **state,
                        "phase": "cancelled",
                        "elapsed_sec": round(time.monotonic() - started_monotonic, 1),
                        "exit_code": -15,
                        "last_events": events[-8:],
                    },
                )
                _cleanup_control(session_id, job_id)
                return -15, output, (stderr + "\n" + cancel_summary).strip()

            if timeout_sec > 0 and elapsed >= timeout_sec:
                _append_runtime_log(
                    session_id,
                    f"TIMEOUT turn={turn_key} elapsed={elapsed:.1f}s pid={process.pid}",
                )
                _terminate_process_tree(process)

                stdout_handle.flush()
                stderr_handle.flush()
                output = stdout_path.read_text(encoding="utf-8", errors="replace").strip()
                stderr = stderr_path.read_text(encoding="utf-8", errors="replace").strip()
                events = _tail_chat_events(session_id)
                timeout_detail = (
                    f"GigaCode MCP hard timeout after {timeout_sec}s. "
                    f"Session remains resumable: {session_id}. "
                    f"Last events: {json.dumps(events[-5:], ensure_ascii=False)}"
                )
                _write_state(
                    session_id,
                    {
                        **state,
                        "phase": "timed_out",
                        "elapsed_sec": round(time.monotonic() - started_monotonic, 1),
                        "exit_code": 124,
                        "last_events": events[-8:],
                    },
                )
                return 124, output, (stderr + "\n" + timeout_detail).strip()

            time.sleep(POLL_INTERVAL_SEC)

        exit_code = process.returncode

    output = stdout_path.read_text(encoding="utf-8", errors="replace").strip()
    stderr = stderr_path.read_text(encoding="utf-8", errors="replace").strip()
    elapsed = time.monotonic() - started_monotonic
    events = _tail_chat_events(session_id)
    _write_state(
        session_id,
        {
            "phase": "completed",
            "session_id": session_id,
            "job_id": job_id,
            "turn": turn_key,
            "pid": process.pid,
            "worker_pid": os.getpid(),
            "cwd": str(ROOT),
            "started_epoch": started_epoch,
            "elapsed_sec": round(elapsed, 1),
            "timeout_sec": timeout_sec,
            "exit_code": exit_code,
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
            "last_events": events[-8:],
        },
    )
    _append_runtime_log(
        session_id,
        f"END turn={turn_key} exit_code={exit_code} elapsed={elapsed:.1f}s",
    )
    return exit_code, output, stderr


def cancel_tool(arguments: dict) -> dict:
    raw_sid = arguments.get("session_id")
    session_id = _validate_session_id(raw_sid)
    if session_id is None:
        return text_result({
            "status": "FAILED",
            "summary": "cancel requires a valid session_id (canonical UUID).",
            "changed": [],
            "verified": [],
            "escalation": None,
            "blockers": [{"kind": "other", "detail": "invalid session_id", "evidence": ""}],
        }, is_error=True)

    state = _load_state(session_id)

    if state is None:
        return text_result({
            "session_id": session_id,
            "status": "UNKNOWN",
            "summary": "No session found for this session_id.",
        })

    if state.get("phase") == "finished":
        return text_result({
            "session_id": session_id,
            "status": "ALREADY_FINISHED",
            "summary": "Session has already completed. No running job to cancel.",
            "handoff": state.get("handoff"),
        })

    job_id = state.get("job_id")
    if not job_id:
        return text_result({
            "session_id": session_id,
            "status": "FAILED",
            "summary": "No active job_id in session state.",
        }, is_error=True)

    running = _pid_alive(state.get("pid")) or _pid_alive(state.get("worker_pid"))
    if not running:
        return text_result({
            "session_id": session_id,
            "status": "ALREADY_STOPPED",
            "summary": "Session job is not running. No cancellation needed.",
        })

    _append_runtime_log(
        session_id,
        f"CANCEL_REQUEST job={job_id} from planner",
    )
    if not _request_cancel(session_id, job_id):
        return text_result({
            "session_id": session_id,
            "status": "FAILED",
            "summary": "Failed to write cancel request.",
        }, is_error=True)

    return text_result({
        "session_id": session_id,
        "status": "CANCEL_REQUESTED",
        "summary": f"Cancellation requested for job {job_id}. The worker will terminate the process tree on its next loop iteration.",
        "job_id": job_id,
    })


def _job_path(session_id: str, job_id: str) -> Path:
    return CACHE_ROOT / f"{session_id}.{job_id}.job.json"


def _control_path(session_id: str, job_id: str) -> Path:
    return CACHE_ROOT / f"{session_id}.{job_id}.control.json"


def _request_cancel(session_id: str, job_id: str) -> bool:
    """Write an atomic cancel request for the worker to observe."""
    control = {
        "action": "cancel",
        "session_id": session_id,
        "job_id": job_id,
        "requested_at": time.time(),
    }
    tmp = _control_path(session_id, job_id).with_suffix(".tmp")
    try:
        tmp.write_text(
            json.dumps(control, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        tmp.replace(_control_path(session_id, job_id))
        return True
    except OSError:
        return False


def _check_cancel_request(session_id: str, job_id: str) -> bool:
    """Worker-side check: return True if a cancel request exists for this job/turn."""
    cp = _control_path(session_id, job_id)
    if not cp.is_file():
        return False
    try:
        control = json.loads(cp.read_text(encoding="utf-8"))
        if control.get("action") == "cancel" and control.get("job_id") == job_id:
            return True
    except Exception:
        pass
    return False


def _cleanup_control(session_id: str, job_id: str) -> None:
    cp = _control_path(session_id, job_id)
    try:
        cp.unlink()
    except OSError:
        pass


def launch_detached_job(
    session_id: str,
    session_args: list[str],
    prompt: str,
    timeout_sec: int,
) -> dict:
    existing = _load_state(session_id)
    if existing and existing.get("phase") in {"queued", "running", "completed"}:
        if _pid_alive(existing.get("pid")) or _pid_alive(existing.get("worker_pid")):
            raise ValueError("session already has a running GigaCode job")

    baseline_chat_size = _chat_size(session_id)
    job_id = uuid.uuid4().hex[:12]
    spec = {
        "session_id": session_id,
        "session_args": session_args,
        "prompt": prompt,
        "timeout_sec": timeout_sec,
        "job_id": job_id,
        "cwd": str(ROOT),
    }
    job_path = _job_path(session_id, job_id)
    job_path.write_text(
        json.dumps(spec, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    worker_log = CACHE_ROOT / f"{session_id}.{job_id}.worker.log"
    state = {
        "phase": "queued",
        "session_id": session_id,
        "job_id": job_id,
        "worker_pid": None,
        "cwd": str(ROOT),
        "started_epoch": time.time(),
        "elapsed_sec": 0.0,
        "timeout_sec": timeout_sec,
        "worker_log": str(worker_log),
    }
    _write_state(session_id, state)

    with worker_log.open("a", encoding="utf-8") as log_handle:
        worker = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--run-job", str(job_path)],
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=log_handle,
            env=os.environ.copy(),
            close_fds=True,
            **_new_process_group_kwargs(),
        )

    current = _load_state(session_id) or state
    if current.get("phase") == "queued" and current.get("job_id") == job_id:
        _write_state(session_id, {**current, "worker_pid": worker.pid})
    _append_runtime_log(
        session_id,
        f"DETACHED job={job_id} worker_pid={worker.pid} timeout_sec={timeout_sec}",
    )

    confirm_deadline = time.monotonic() + (
        STARTUP_CONFIRM_TIMEOUT_SEC
        if timeout_sec == 0
        else min(STARTUP_CONFIRM_TIMEOUT_SEC, max(1.0, float(timeout_sec)))
    )
    while time.monotonic() < confirm_deadline:
        current = _load_state(session_id) or {}

        handoff = current.get("handoff")
        if isinstance(handoff, dict):
            return {
                "session_id": session_id,
                **handoff,
                "runtime": {
                    "phase": current.get("phase"),
                    "job_id": current.get("job_id"),
                    "elapsed_sec": current.get("elapsed_sec"),
                    "exit_code": current.get("exit_code"),
                    "startup_confirmed": True,
                },
            }

        activity = _activity_after_offset(session_id, baseline_chat_size)
        if activity is not None:
            _append_runtime_log(
                session_id,
                f"CONFIRMED job={job_id} activity={json.dumps(activity, ensure_ascii=False)}",
            )
            return {
                "session_id": session_id,
                "status": "RUNNING",
                "summary": "GigaCode accepted the task and produced confirmed activity.",
                "job_id": job_id,
                "startup_confirmed": True,
                "runtime": {
                    "phase": current.get("phase", "running"),
                    "timeout_sec": timeout_sec,
                },
            }

        running = _pid_alive(current.get("pid")) or _pid_alive(current.get("worker_pid"))
        if current.get("phase") in {"timed_out", "finished"} and not running:
            break
        time.sleep(STARTUP_CONFIRM_POLL_SEC)

    current = _load_state(session_id) or {}
    running = _pid_alive(current.get("pid")) or _pid_alive(current.get("worker_pid"))
    if not running:
        return {
            "session_id": session_id,
            "status": "FAILED",
            "summary": "Detached GigaCode job stopped before producing confirmed activity.",
            "changed": [],
            "verified": [],
            "escalation": None,
            "blockers": [{
                "kind": "tool",
                "detail": "worker stopped during startup handshake",
                "evidence": f"phase={current.get('phase')}; job_id={job_id}",
            }],
            "runtime": {
                "phase": current.get("phase"),
                "job_id": job_id,
                "startup_confirmed": False,
            },
        }

    return {
        "session_id": session_id,
        "status": "STARTING",
        "summary": (
            f"GigaCode process is alive, but no model/tool activity was confirmed within "
            f"{STARTUP_CONFIRM_TIMEOUT_SEC:.0f}s."
        ),
        "job_id": job_id,
        "startup_confirmed": False,
        "runtime": {
            "phase": current.get("phase", "running"),
            "timeout_sec": timeout_sec,
        },
    }


def run_detached_job(job_path_arg: str) -> int:
    job_path = Path(job_path_arg)
    try:
        spec = json.loads(job_path.read_text(encoding="utf-8"))
        session_id = spec["session_id"]
        session_args = spec["session_args"]
        prompt = spec["prompt"]
        timeout_sec = int(spec["timeout_sec"])
        job_id = spec["job_id"]
    except Exception as exc:
        sys.stderr.write(f"invalid detached job spec: {exc}\n")
        return 2

    initial = _load_state(session_id) or {}
    _write_state(
        session_id,
        {
            **initial,
            "phase": "running",
            "session_id": session_id,
            "job_id": job_id,
            "worker_pid": os.getpid(),
            "started_epoch": initial.get("started_epoch", time.time()),
            "elapsed_sec": 0.0,
            "timeout_sec": timeout_sec,
        },
    )

    exit_code, output, stderr = run_gigacode(
        session_id,
        session_args,
        prompt,
        timeout_sec,
        job_id=job_id,
    )
    handoff, _ = parse_worker_handoff(output, exit_code, stderr)
    state = _load_state(session_id) or {}
    _write_state(
        session_id,
        {
            **state,
            "phase": "finished",
            "job_id": job_id,
            "worker_pid": os.getpid(),
            "exit_code": exit_code,
            "handoff": handoff,
        },
    )
    _append_runtime_log(
        session_id,
        f"HANDOFF job={job_id} status={handoff.get('status')} exit_code={exit_code}",
    )
    try:
        job_path.unlink()
    except OSError:
        pass
    return 0


def extract_json_object(output: str) -> dict | None:
    """Extract a JSON object even if the worker wrapped it in prose/fences."""
    stripped = output.strip()
    if not stripped:
        return None

    try:
        value = json.loads(stripped)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    candidates: list[dict] = []
    for index, char in enumerate(stripped):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(stripped, index)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            candidates.append(value)

    if not candidates:
        return None

    required = {"status", "summary", "changed", "verified", "escalation", "blockers"}
    for candidate in reversed(candidates):
        if required.issubset(candidate):
            return candidate
    return candidates[-1]


def parse_worker_handoff(output: str, exit_code: int, stderr: str) -> tuple[dict, bool]:
    if exit_code != 0:
        payload = {
            "status": "FAILED",
            "summary": "GigaCode process failed before producing a usable handoff.",
            "changed": [],
            "verified": [],
            "escalation": None,
            "blockers": [{
                "kind": "tool",
                "detail": f"gigacode exited with code {exit_code}",
                "evidence": (stderr or output)[-4000:],
            }],
        }
        return payload, True

    handoff = extract_json_object(output)
    if handoff is None:
        payload = {
            "status": "FAILED",
            "summary": "GigaCode violated the worker handoff protocol.",
            "changed": [],
            "verified": [],
            "escalation": None,
            "blockers": [{
                "kind": "other",
                "detail": "worker returned no parseable JSON handoff",
                "evidence": output[-4000:],
            }],
        }
        return payload, True

    required = {"status", "summary", "changed", "verified", "escalation", "blockers"}
    missing = sorted(required - set(handoff))
    if missing or handoff.get("status") not in {"DONE", "ESCALATE", "FAILED"}:
        payload = {
            "status": "FAILED",
            "summary": "GigaCode returned an invalid worker handoff object.",
            "changed": [],
            "verified": [],
            "escalation": None,
            "blockers": [{
                "kind": "other",
                "detail": f"invalid handoff fields; missing={missing}",
                "evidence": output[-4000:],
            }],
        }
        return payload, True

    if handoff["status"] == "ESCALATE":
        escalation = handoff.get("escalation")
        escalation_required = {
            "kind", "expected", "observed", "evidence",
            "impact", "decision_needed", "options",
        }
        escalation_missing = (
            sorted(escalation_required - set(escalation))
            if isinstance(escalation, dict)
            else sorted(escalation_required)
        )
        evidence_ok = (
            isinstance(escalation, dict)
            and isinstance(escalation.get("evidence"), list)
            and len(escalation["evidence"]) > 0
        )
        decision_ok = (
            isinstance(escalation, dict)
            and isinstance(escalation.get("decision_needed"), str)
            and bool(escalation["decision_needed"].strip())
        )
        if escalation_missing or not evidence_ok or not decision_ok:
            payload = {
                "status": "FAILED",
                "summary": "GigaCode escalated without a complete planner-ready handoff.",
                "changed": handoff.get("changed") if isinstance(handoff.get("changed"), list) else [],
                "verified": handoff.get("verified") if isinstance(handoff.get("verified"), list) else [],
                "escalation": None,
                "blockers": [{
                    "kind": "other",
                    "detail": (
                        "invalid ESCALATE handoff; "
                        f"missing={escalation_missing}, "
                        f"evidence_present={evidence_ok}, "
                        f"decision_present={decision_ok}"
                    ),
                    "evidence": output[-4000:],
                }],
            }
            return payload, True

    if handoff["status"] == "DONE":
        done_errors: list[str] = []
        if handoff.get("escalation") is not None:
            done_errors.append("escalation must be null")

        blockers = handoff.get("blockers")
        if blockers != []:
            done_errors.append("blockers must be empty")

        verified = handoff.get("verified")
        if not isinstance(verified, list) or not verified:
            done_errors.append("verified must be a non-empty list")
        else:
            for index, item in enumerate(verified):
                if not isinstance(item, dict):
                    done_errors.append(f"verified[{index}] must be an object")
                    continue
                if not isinstance(item.get("criterion"), str) or not item["criterion"].strip():
                    done_errors.append(f"verified[{index}].criterion is required")
                if not isinstance(item.get("check"), str) or not item["check"].strip():
                    done_errors.append(f"verified[{index}].check is required")
                if item.get("result") != "PASS":
                    done_errors.append(f"verified[{index}].result must be PASS")
                if not isinstance(item.get("evidence"), str) or not item["evidence"].strip():
                    done_errors.append(f"verified[{index}].evidence is required")

        self_review = handoff.get("self_review")
        if not isinstance(self_review, dict):
            done_errors.append("self_review is required")
        else:
            if self_review.get("criteria_complete") is not True:
                done_errors.append("self_review.criteria_complete must be true")
            if self_review.get("diff_scope_clean") is not True:
                done_errors.append("self_review.diff_scope_clean must be true")
            if self_review.get("unverified") != []:
                done_errors.append("self_review.unverified must be empty")

        if done_errors:
            payload = {
                "status": "FAILED",
                "summary": "GigaCode returned DONE without a complete self-verification handoff.",
                "changed": handoff.get("changed") if isinstance(handoff.get("changed"), list) else [],
                "verified": verified if isinstance(verified, list) else [],
                "escalation": None,
                "blockers": [{
                    "kind": "other",
                    "detail": "; ".join(done_errors),
                    "evidence": "Resume the same session and request the missing acceptance evidence/self-review.",
                }],
            }
            return payload, True

    return handoff, handoff["status"] == "FAILED"


def start_tool(arguments: dict) -> dict:
    plan_path = arguments.get("plan_path")
    direct_prompt = arguments.get("prompt")

    if bool(plan_path) == bool(direct_prompt):
        raise ValueError("start requires exactly one of plan_path or prompt")

    session_id = str(uuid.uuid4())
    if plan_path:
        plan = resolve_plan(plan_path)
        worker_prompt = (
            f"Read the complete implementation plan from {plan}. "
            "Perform the preflight required by your worker contract, then execute it if valid. "
            "Return only the required JSON handoff."
        )
    else:
        worker_prompt = (
            "Execute this direct planner task under the same worker contract. "
            "Treat the supplied task as the complete plan: validate material assumptions before editing, "
            "escalate instead of redesigning if they do not match the repository, and return only the required JSON handoff.\n\n"
            + direct_prompt.strip()
        )

    timeout_sec = int(arguments.get("timeout_sec", DEFAULT_HARD_TIMEOUT_SEC))
    payload = launch_detached_job(
        session_id,
        ["--session-id", session_id],
        worker_prompt,
        timeout_sec,
    )
    return text_result(payload)


def resume_tool(arguments: dict) -> dict:
    raw_sid = arguments.get("session_id")
    session_id = _validate_session_id(raw_sid)
    if session_id is None:
        raise ValueError("resume requires a valid UUID session_id")
    prompt = (
        "Continue the same task and worker contract. "
        "The planner provides only new information below. Apply it to the existing session context.\n\n"
        + arguments["prompt"].strip()
        + "\n\nReturn only the required JSON handoff."
    )
    timeout_sec = int(arguments.get("timeout_sec", DEFAULT_HARD_TIMEOUT_SEC))
    payload = launch_detached_job(
        session_id,
        ["--resume", session_id],
        prompt,
        timeout_sec,
    )
    return text_result(payload)


def handle(request: dict) -> dict | None:
    method = request.get("method")
    request_id = request.get("id")

    if method == "initialize":
        requested = request.get("params", {}).get("protocolVersion", "2025-06-18")
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": requested,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        }

    if method in {"notifications/initialized", "notifications/cancelled"}:
        return None

    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}}

    if method == "tools/call":
        params = request.get("params", {})
        name = params.get("name")
        arguments = params.get("arguments") or {}
        try:
            if name != "gigacode":
                raise ValueError(f"unknown tool: {name}")
            action = arguments.get("action")
            timeout_value = arguments.get("timeout_sec")
            if timeout_value is not None:
                if isinstance(timeout_value, bool) or not isinstance(timeout_value, int):
                    raise ValueError("timeout_sec must be a nonnegative integer")
                if timeout_value < 0:
                    raise ValueError("timeout_sec must be a nonnegative integer")
            if action == "start":
                plan_path = arguments.get("plan_path")
                direct_prompt = arguments.get("prompt")
                if plan_path is not None and not isinstance(plan_path, str):
                    raise ValueError("plan_path must be a string")
                if direct_prompt is not None and not isinstance(direct_prompt, str):
                    raise ValueError("prompt must be a string")
                result = start_tool(arguments)
            elif action == "resume":
                if not isinstance(arguments.get("session_id"), str) or not isinstance(arguments.get("prompt"), str):
                    raise ValueError("resume requires session_id and prompt as strings")
                result = resume_tool(arguments)
            elif action == "status":
                if not isinstance(arguments.get("session_id"), str):
                    raise ValueError("status requires session_id as a string")
                result = status_tool(arguments)
            elif action == "messages":
                if not isinstance(arguments.get("session_id"), str):
                    raise ValueError("messages requires session_id as a string")
                after_revision = arguments.get("after_revision")
                if after_revision is not None:
                    if isinstance(after_revision, bool) or not isinstance(after_revision, int) or after_revision < 0:
                        raise ValueError("after_revision must be a nonnegative integer")
                message_limit = arguments.get("message_limit")
                if message_limit is not None:
                    if isinstance(message_limit, bool) or not isinstance(message_limit, int):
                        raise ValueError("message_limit must be an integer")
                    if message_limit < 1 or message_limit > 50:
                        raise ValueError("message_limit must be between 1 and 50")
                result = messages_tool(arguments)
            elif action == "wait":
                if not isinstance(arguments.get("session_id"), str):
                    raise ValueError("wait requires session_id as a string")
                wait_timeout_value = arguments.get("wait_timeout_sec")
                if wait_timeout_value is not None:
                    if isinstance(wait_timeout_value, bool) or not isinstance(wait_timeout_value, int):
                        raise ValueError("wait_timeout_sec must be an integer")
                    if wait_timeout_value < 1 or wait_timeout_value > MAX_WAIT_TIMEOUT_SEC:
                        raise ValueError(f"wait_timeout_sec must be between 1 and {MAX_WAIT_TIMEOUT_SEC}")
                result = wait_tool(arguments)
            elif action == "cancel":
                if not isinstance(arguments.get("session_id"), str):
                    raise ValueError("cancel requires session_id as a string")
                result = cancel_tool(arguments)
            else:
                raise ValueError("action must be start, resume, status, messages, wait, or cancel")
            return {"jsonrpc": "2.0", "id": request_id, "result": result}
        except Exception as exc:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": text_result({"error": str(exc)}, is_error=True),
            }

    if request_id is None:
        return None
    return error_response(request_id, -32601, f"Method not found: {method}")


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--run-job":
        return run_detached_job(sys.argv[2])

    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            request = json.loads(raw)
            response = handle(request)
        except Exception as exc:
            response = error_response(None, -32603, str(exc))
        if response is not None:
            emit(response)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
