#!/usr/bin/env python3
"""Harr Einherjar: generic detached worker bridge for external agent CLIs."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import signal
import shutil
import subprocess
import sys
import time
import uuid

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from common.executor.backends import (
    BackendResumeRequest,
    BackendStartRequest,
    get_backend_adapter,
    list_available_backends,
    load_einherjar_config,
    resolve_backend,
)
from common.executor.protocol import parse_worker_handoff

SERVER_NAME = "einherjar"
SERVER_VERSION = "0.1.0"
ROOT = Path.cwd().resolve()
DEFAULT_HARD_TIMEOUT_SEC = 0
DEFAULT_WAIT_TIMEOUT_SEC = 1500
MAX_WAIT_TIMEOUT_SEC = 1500
POLL_INTERVAL_SEC = 0.5
STARTUP_WAIT_SEC = 3.0
INSTANCE_ID = os.environ.get("HARR_EIN_INSTANCE")
if INSTANCE_ID and not re.fullmatch(r"[a-z][a-z0-9-]{0,62}", INSTANCE_ID):
    raise SystemExit("invalid Ein MCP instance name")
WORKSPACE_KEY = hashlib.sha256(str(ROOT).encode("utf-8")).hexdigest()[:12]
CACHE_ROOT = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "harr" / "einherjar" / (INSTANCE_ID or "default") / WORKSPACE_KEY
CACHE_ROOT.mkdir(parents=True, exist_ok=True)
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

TOOLS = [{
    "name": "ein" if INSTANCE_ID else "worker",
    "description": (
        "Delegate a bounded implementation/verification contract to an external CLI agent through "
        "Harr Einherjar. start/resume are detached; status is nonblocking; wait blocks inside the "
        "bridge; messages is opt-in progress; cancel is explicit; backends lists safe capabilities. "
        "Harr session ids are backend-neutral and vendor session ids never leave the bridge."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["start", "resume", "status", "messages", "wait", "cancel", "backends"]},
            "backend": {"type": "string", "description": "Optional backend for start only. Defaults to Einherjar config."},
            "plan_path": {"type": "string", "description": "Start from an implementation plan inside the workspace."},
            "prompt": {"type": "string", "description": "Direct start task or resume delta."},
            "session_id": {"type": "string", "description": "Harr Einherjar session UUID."},
            "timeout_sec": {"type": "integer", "minimum": 0},
            "wait_timeout_sec": {"type": "integer", "minimum": 1, "maximum": MAX_WAIT_TIMEOUT_SEC},
            "after_revision": {"type": "integer", "minimum": 0},
            "message_limit": {"type": "integer", "minimum": 1, "maximum": 50},
        },
        "required": ["action"],
        "additionalProperties": False,
    },
}]


def emit(message: dict) -> None:
    sys.stdout.write(json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def text_result(payload: dict, *, is_error: bool = False) -> dict:
    result = {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))}],
        "structuredContent": payload,
    }
    if is_error:
        result["isError"] = True
    return result


def _validate_session_id(value: object) -> str | None:
    return value if isinstance(value, str) and _UUID_RE.fullmatch(value) else None


def resolve_plan(raw: str) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = ROOT / path
    path = path.resolve()
    try:
        path.relative_to(ROOT)
    except ValueError as exc:
        raise ValueError("plan_path must stay inside the workspace root") from exc
    if not path.is_file():
        raise ValueError(f"plan file does not exist: {raw}")
    return path


def _state_path(session_id: str) -> Path:
    return CACHE_ROOT / f"{session_id}.state.json"


def _job_path(session_id: str, job_id: str) -> Path:
    return CACHE_ROOT / f"{session_id}.{job_id}.job.json"


def _control_path(session_id: str, job_id: str) -> Path:
    return CACHE_ROOT / f"{session_id}.{job_id}.control.json"


def _runtime_log_path(session_id: str) -> Path:
    return CACHE_ROOT / f"{session_id}.runtime.log"


def _write_state(session_id: str, state: dict) -> None:
    target = _state_path(session_id)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(target)


def _load_state(session_id: str) -> dict | None:
    try:
        value = json.loads(_state_path(session_id).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _append_log(session_id: str, message: str) -> None:
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with _runtime_log_path(session_id).open("a", encoding="utf-8") as handle:
        handle.write(f"{stamp} {message}\n")


def _pid_alive(pid: object) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            return bool(kernel32.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


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
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
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


def _owner_identity(pid: int) -> str | None:
    """Linux process start time protects the detached-worker owner check from PID reuse."""
    if not sys.platform.startswith("linux"):
        return None
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        return stat.rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError):
        return None


def _owner_alive(owner: dict | None) -> bool:
    if not owner:
        return True
    identity = _owner_identity(owner.get("pid"))
    return identity is not None and identity == owner.get("start_ticks")


def _request_cancel(session_id: str, job_id: str) -> None:
    target = _control_path(session_id, job_id)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps({"action": "cancel", "job_id": job_id, "requested_at": time.time()}), encoding="utf-8")
    tmp.replace(target)


def _cancel_requested(session_id: str, job_id: str) -> bool:
    try:
        value = json.loads(_control_path(session_id, job_id).read_text(encoding="utf-8"))
        return value.get("action") == "cancel" and value.get("job_id") == job_id
    except (OSError, json.JSONDecodeError):
        return False


def _cleanup_control(session_id: str, job_id: str) -> None:
    try:
        _control_path(session_id, job_id).unlink()
    except OSError:
        pass


def _adapter_from_state(state: dict):
    backend = state.get("backend")
    if not isinstance(backend, str):
        raise ValueError("session state has no backend")
    cfg = state.get("backend_config")
    return get_backend_adapter(backend, cfg) if cfg is not None else get_backend_adapter(backend)


def _progress_messages(state: dict) -> list[dict]:
    raw = state.get("stdout_path")
    if not isinstance(raw, str):
        return []
    path = Path(raw)
    try:
        # Bound planner-visible parsing. Full raw logs stay out-of-band.
        with path.open("rb") as handle:
            size = path.stat().st_size
            if size > 2_000_000:
                handle.seek(size - 2_000_000)
                handle.readline()
            text = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return []
    try:
        values = _adapter_from_state(state).progress_messages(text)
    except Exception:
        return []
    result = []
    for index, value in enumerate(values, start=1):
        if isinstance(value, str) and value.strip():
            result.append({"revision": index, "text": value.strip()[:8000]})
    return result


def status_tool(arguments: dict) -> dict:
    session_id = _validate_session_id(arguments.get("session_id"))
    if session_id is None:
        return text_result({"status": "FAILED", "summary": "status requires a valid Harr session UUID."}, is_error=True)
    state = _load_state(session_id)
    if state is None:
        return text_result({"session_id": session_id, "status": "UNKNOWN", "summary": "No Einherjar session found."})
    if isinstance(state.get("handoff"), dict):
        return text_result({
            "session_id": session_id,
            "backend": state.get("backend"),
            **state["handoff"],
            "runtime": {
                "phase": state.get("phase"), "job_id": state.get("job_id"),
                "elapsed_sec": state.get("elapsed_sec"), "exit_code": state.get("exit_code"),
                "resumable": bool(state.get("vendor_session_id")),
            },
        })
    running = _pid_alive(state.get("pid")) or _pid_alive(state.get("worker_pid"))
    if state.get("phase") in {"queued", "running"} and not running:
        return text_result({
            "session_id": session_id, "backend": state.get("backend"), "status": "FAILED",
            "summary": "Detached external worker stopped without a final handoff.",
            "changed": [], "verified": [], "escalation": None,
            "blockers": [{"kind": "tool", "detail": "worker process is no longer running", "evidence": f"phase={state.get('phase')}; job_id={state.get('job_id')}"}],
        }, is_error=True)
    return text_result({
        "session_id": session_id, "backend": state.get("backend"), "status": "RUNNING" if state.get("startup_confirmed") else "STARTING",
        "summary": f"Einherjar backend {state.get('backend')} is still executing.",
        "runtime": {
            "phase": state.get("phase"), "job_id": state.get("job_id"),
            "elapsed_sec": state.get("elapsed_sec"), "timeout_sec": state.get("timeout_sec"),
            "cancel_requested": bool(state.get("job_id")) and _cancel_requested(session_id, state["job_id"]),
            "process_running": running, "startup_confirmed": bool(state.get("startup_confirmed")),
        },
    })


def messages_tool(arguments: dict) -> dict:
    session_id = _validate_session_id(arguments.get("session_id"))
    if session_id is None:
        return text_result({"status": "FAILED", "summary": "messages requires a valid Harr session UUID."}, is_error=True)
    state = _load_state(session_id)
    if state is None:
        return text_result({"session_id": session_id, "status": "UNKNOWN", "messages": []})
    messages = _progress_messages(state)
    latest = messages[-1]["revision"] if messages else 0
    limit = int(arguments.get("message_limit", 8))
    after = arguments.get("after_revision")
    if after is None:
        selected = messages[-limit:]
        revision = latest
        has_more = False
    else:
        selected = [x for x in messages if x["revision"] > after][:limit]
        revision = selected[-1]["revision"] if selected else int(after)
        has_more = latest > revision
    return text_result({
        "session_id": session_id, "backend": state.get("backend"), "status": "MESSAGES",
        "revision": revision, "latest_revision": latest, "has_more": has_more, "messages": selected,
    })


def _emit_progress(token: object, progress: float, message: str) -> None:
    emit({"jsonrpc": "2.0", "method": "notifications/progress", "params": {"progressToken": token, "progress": progress, "message": message}})


def wait_tool(arguments: dict, progress_token: object = None) -> dict:
    session_id = _validate_session_id(arguments.get("session_id"))
    if session_id is None:
        return text_result({"status": "FAILED", "summary": "wait requires a valid Harr session UUID."}, is_error=True)
    timeout = int(arguments.get("wait_timeout_sec", DEFAULT_WAIT_TIMEOUT_SEC))
    deadline = time.monotonic() + timeout
    start = time.monotonic()
    revision = 0
    while True:
        if progress_token is not None:
            msg = json.loads(messages_tool({"session_id": session_id, "after_revision": revision, "message_limit": 50})["content"][0]["text"])
            for item in msg.get("messages", []):
                revision = max(revision, int(item.get("revision", 0)))
                _emit_progress(progress_token, float(revision), f"Einherjar: {item.get('text', '')}")
        result = status_tool({"session_id": session_id})
        payload = json.loads(result["content"][0]["text"])
        if payload.get("status") not in {"RUNNING", "STARTING"}:
            return result
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            payload["wait"] = {"timed_out": True, "waited_sec": round(time.monotonic() - start, 1)}
            payload["summary"] = "External worker is still executing; the detached job continues."
            return text_result(payload)
        time.sleep(min(1.0, remaining))


def cancel_tool(arguments: dict) -> dict:
    session_id = _validate_session_id(arguments.get("session_id"))
    if session_id is None:
        return text_result({"status": "FAILED", "summary": "cancel requires a valid Harr session UUID."}, is_error=True)
    state = _load_state(session_id)
    if state is None:
        return text_result({"session_id": session_id, "status": "UNKNOWN", "summary": "No Einherjar session found."})
    if isinstance(state.get("handoff"), dict):
        return text_result({"session_id": session_id, "status": "ALREADY_FINISHED", "handoff": state["handoff"]})
    job_id = state.get("job_id")
    if not isinstance(job_id, str) or not job_id:
        return text_result({"session_id": session_id, "status": "FAILED", "summary": "Session has no active job."}, is_error=True)
    if not (_pid_alive(state.get("pid")) or _pid_alive(state.get("worker_pid"))):
        return text_result({"session_id": session_id, "status": "ALREADY_STOPPED", "summary": "Worker is not running."})
    _request_cancel(session_id, job_id)
    _append_log(session_id, f"CANCEL_REQUEST job={job_id}")
    return text_result({"session_id": session_id, "status": "CANCEL_REQUESTED", "job_id": job_id})


def backends_tool() -> dict:
    config = load_einherjar_config()
    return text_result({
        "status": "BACKENDS",
        "default_backend": config["default_backend"],
        "backends": [item.public_dict() for item in list_available_backends(config)],
    })


def _failed_handoff(summary: str, detail: str, evidence: str = "") -> dict:
    return {
        "status": "FAILED", "summary": summary, "changed": [], "verified": [],
        "escalation": None,
        "blockers": [{"kind": "tool", "detail": detail, "evidence": evidence[-4000:]}],
    }


def _run_turn(spec: dict) -> int:
    session_id = spec["session_id"]
    job_id = spec["job_id"]
    backend = spec["backend"]
    backend_config = spec.get("backend_config")
    adapter = get_backend_adapter(backend, backend_config) if backend_config is not None else get_backend_adapter(backend)
    prompt = spec["prompt"]
    mode = spec["mode"]
    owner = spec.get("owner")
    timeout_sec = int(spec.get("timeout_sec", 0))
    state = _load_state(session_id) or {}
    prepared_prompt = adapter.prepare_prompt(prompt)
    request = (
        BackendStartRequest(prompt=prepared_prompt, workspace_root=ROOT, timeout_sec=timeout_sec, harr_session_id=session_id)
        if mode == "start"
        else BackendResumeRequest(
            prompt=prepared_prompt, workspace_root=ROOT, timeout_sec=timeout_sec,
            vendor_session_id=spec["vendor_session_id"], harr_session_id=session_id,
        )
    )
    try:
        command = adapter.start_command(request) if mode == "start" else adapter.resume_command(request)
    except Exception as exc:
        adapter.cleanup()
        _cleanup_control(session_id, job_id)
        try:
            Path(spec["job_path"]).unlink()
        except (KeyError, OSError):
            pass
        handoff = _failed_handoff("External worker could not be started.", str(exc))
        _write_state(session_id, {**state, "phase": "finished", "exit_code": 127, "handoff": handoff})
        return 0

    turn = f"{int(time.time())}-{uuid.uuid4().hex[:6]}"
    stdout_path = CACHE_ROOT / f"{session_id}.{turn}.stdout"
    stderr_path = CACHE_ROOT / f"{session_id}.{turn}.stderr"
    started = time.monotonic()
    started_epoch = time.time()
    process = None
    try:
        with stdout_path.open("w", encoding="utf-8") as stdout_handle, stderr_path.open("w", encoding="utf-8") as stderr_handle:
            stdin_text = adapter.stdin_text(prepared_prompt)
            process = subprocess.Popen(
                command, cwd=ROOT, text=True,
                stdin=subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL,
                stdout=stdout_handle, stderr=stderr_handle, env=os.environ.copy(),
                **_new_process_group_kwargs(),
            )
            if stdin_text is not None and process.stdin is not None:
                process.stdin.write(stdin_text)
                if not stdin_text.endswith("\n"):
                    process.stdin.write("\n")
                process.stdin.close()
            state = {
                **state, "phase": "running", "session_id": session_id, "job_id": job_id,
                "backend": backend, "backend_config": backend_config, "pid": process.pid,
                "worker_pid": os.getpid(), "cwd": str(ROOT), "started_epoch": started_epoch,
                "elapsed_sec": 0.0, "timeout_sec": timeout_sec,
                "stdout_path": str(stdout_path), "stderr_path": str(stderr_path),
            "startup_confirmed": False,
            }
            _write_state(session_id, state)
            _append_log(session_id, f"START backend={backend} mode={mode} job={job_id} pid={process.pid}")
            terminal_reason = None
            while process.poll() is None:
                elapsed = time.monotonic() - started
                state["elapsed_sec"] = round(elapsed, 1)
                if not state["startup_confirmed"]:
                    try:
                        size = stdout_path.stat().st_size
                        if size:
                            with stdout_path.open("rb") as live:
                                live.seek(max(0, size - 131072))
                                chunk = live.read().decode("utf-8", errors="replace")
                            if adapter.progress_messages(chunk):
                                state["startup_confirmed"] = True
                    except OSError:
                        pass
                _write_state(session_id, state)
                if not _owner_alive(owner):
                    terminal_reason = "owner_disconnected"
                    _append_log(session_id, f"OWNER_LOST job={job_id} pid={process.pid}")
                    _terminate_process_tree(process)
                    break
                if _cancel_requested(session_id, job_id):
                    terminal_reason = "cancelled"
                    _terminate_process_tree(process)
                    break
                if timeout_sec > 0 and elapsed >= timeout_sec:
                    terminal_reason = "timed_out"
                    _terminate_process_tree(process)
                    break
                time.sleep(POLL_INTERVAL_SEC)
            exit_code = process.returncode if process.returncode is not None else (-15 if terminal_reason == "cancelled" else 124)
        stdout = stdout_path.read_text(encoding="utf-8", errors="replace")
        stderr = stderr_path.read_text(encoding="utf-8", errors="replace")
        vendor_session_id = state.get("vendor_session_id")
        if mode == "start" and not vendor_session_id:
            vendor_session_id = adapter.initial_vendor_session_id(request)
        if not vendor_session_id:
            vendor_session_id = adapter.extract_vendor_session_id(stdout, stderr)
        if terminal_reason == "owner_disconnected":
            handoff = _failed_handoff("External worker was cancelled because its owning MCP process exited.", "owner disconnected", stderr)
            exit_code = -15
        elif terminal_reason == "cancelled":
            handoff = _failed_handoff("External worker was cancelled.", "manual cancellation", stderr)
            exit_code = -15
        elif terminal_reason == "timed_out":
            handoff = _failed_handoff("External worker exceeded the requested hard timeout.", f"timeout after {timeout_sec}s", stderr)
            exit_code = 124
        else:
            final = adapter.final_output(stdout, stderr)
            handoff, _ = parse_worker_handoff(final, int(exit_code), stderr)
        elapsed = round(time.monotonic() - started, 1)
        _write_state(session_id, {
            **state, "phase": "finished", "elapsed_sec": elapsed, "exit_code": exit_code,
            "vendor_session_id": vendor_session_id, "handoff": handoff,
        })
        _append_log(session_id, f"END backend={backend} job={job_id} exit={exit_code} status={handoff.get('status')}")
    finally:
        adapter.cleanup()
        _cleanup_control(session_id, job_id)
        try:
            Path(spec["job_path"]).unlink()
        except (KeyError, OSError):
            pass
    return 0


def launch_job(session_id: str, backend: str, backend_config: dict | None, prompt: str, timeout_sec: int, mode: str, vendor_session_id: str | None = None) -> dict:
    existing = _load_state(session_id)
    if existing and existing.get("phase") in {"queued", "running"} and (
        _pid_alive(existing.get("pid")) or _pid_alive(existing.get("worker_pid"))
    ):
        raise ValueError("session already has a running Einherjar job")
    job_id = uuid.uuid4().hex[:12]
    job_path = _job_path(session_id, job_id)
    spec = {
        "session_id": session_id, "backend": backend, "backend_config": backend_config,
        "prompt": prompt, "timeout_sec": timeout_sec, "job_id": job_id,
        "mode": mode, "vendor_session_id": vendor_session_id, "cwd": str(ROOT),
        "job_path": str(job_path),
    }
    if sys.platform.startswith("linux"):
        identity = _owner_identity(os.getpid())
        if identity is None:
            raise RuntimeError("cannot establish Einherjar MCP owner identity")
        spec["owner"] = {"pid": os.getpid(), "start_ticks": identity}
    job_path.write_text(json.dumps(spec, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    state = {
        "phase": "queued", "session_id": session_id, "job_id": job_id, "backend": backend,
        "backend_config": backend_config, "vendor_session_id": vendor_session_id,
        "worker_pid": None, "cwd": str(ROOT), "started_epoch": time.time(),
        "elapsed_sec": 0.0, "timeout_sec": timeout_sec, "startup_confirmed": False,
    }
    _write_state(session_id, state)
    worker_log = CACHE_ROOT / f"{session_id}.{job_id}.worker.log"
    with worker_log.open("a", encoding="utf-8") as log_handle:
        worker = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--run-job", str(job_path)],
            cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log_handle, stderr=log_handle,
            env=os.environ.copy(), close_fds=True, **_new_process_group_kwargs(),
        )
    state["worker_pid"] = worker.pid
    state["worker_log"] = str(worker_log)
    _write_state(session_id, state)

    deadline = time.monotonic() + STARTUP_WAIT_SEC
    while time.monotonic() < deadline:
        current = _load_state(session_id) or state
        if isinstance(current.get("handoff"), dict):
            return {
                "session_id": session_id, "backend": backend, **current["handoff"],
                "runtime": {"phase": current.get("phase"), "job_id": job_id, "elapsed_sec": current.get("elapsed_sec"), "exit_code": current.get("exit_code")},
            }
        if current.get("phase") == "running" and current.get("startup_confirmed") and _pid_alive(current.get("pid")):
            return {
                "session_id": session_id, "backend": backend, "status": "RUNNING",
                "summary": f"Einherjar started backend {backend}.", "job_id": job_id,
                "runtime": {"phase": "running", "timeout_sec": timeout_sec, "startup_confirmed": True},
            }
        if not _pid_alive(current.get("worker_pid")):
            break
        time.sleep(0.05)
    current = _load_state(session_id) or state
    if _pid_alive(current.get("worker_pid")) or _pid_alive(current.get("pid")):
        return {
            "session_id": session_id, "backend": backend, "status": "STARTING",
            "summary": f"Einherjar backend {backend} worker is starting.", "job_id": job_id,
            "runtime": {"phase": current.get("phase"), "timeout_sec": timeout_sec, "startup_confirmed": False},
        }
    return {
        "session_id": session_id, "backend": backend, "status": "FAILED",
        "summary": "Detached Einherjar worker stopped during startup.",
        "changed": [], "verified": [], "escalation": None,
        "blockers": [{"kind": "tool", "detail": "worker stopped during startup", "evidence": f"job_id={job_id}"}],
    }


def start_tool(arguments: dict) -> dict:
    plan_path = arguments.get("plan_path")
    direct_prompt = arguments.get("prompt")
    if bool(plan_path) == bool(direct_prompt):
        raise ValueError("start requires exactly one of plan_path or prompt")
    config = load_einherjar_config()
    if INSTANCE_ID and "backend" in arguments:
        raise ValueError("backend is fixed by Ein instance")
    backend_name, adapter = resolve_backend(arguments.get("backend"), config)
    probe = adapter.probe()
    if not probe.found:
        raise ValueError(probe.diagnostic or f"backend {backend_name} is unavailable")
    custom = config.get("backends", {}).get(backend_name)
    session_id = str(uuid.uuid4())
    if plan_path:
        plan = resolve_plan(plan_path)
        prompt = (
            f"Read the complete implementation plan from {plan}. Perform the worker-contract preflight, "
            "execute it if valid, and return only the required JSON handoff."
        )
    else:
        prompt = (
            "Execute this direct planner task under the worker contract. Validate material assumptions before "
            "editing; escalate instead of redesigning; return only the required JSON handoff.\n\n"
            + direct_prompt.strip()
        )
    return text_result(launch_job(
        session_id, backend_name, custom, prompt,
        int(arguments.get("timeout_sec", DEFAULT_HARD_TIMEOUT_SEC)), "start",
    ))


def resume_tool(arguments: dict) -> dict:
    session_id = _validate_session_id(arguments.get("session_id"))
    if session_id is None:
        raise ValueError("resume requires a valid Harr session UUID")
    state = _load_state(session_id)
    if state is None:
        raise ValueError("unknown Einherjar session")
    vendor_session_id = state.get("vendor_session_id")
    if not isinstance(vendor_session_id, str) or not vendor_session_id:
        raise ValueError("selected backend session has no resumable vendor session id")
    adapter = _adapter_from_state(state)
    if not adapter.probe().resumable:
        raise ValueError(f"backend {state.get('backend')} does not support resume")
    prompt = (
        "Continue the same task and worker contract. Apply only the planner delta below to the existing "
        "session context. Return only the required JSON handoff.\n\n" + arguments["prompt"].strip()
    )
    return text_result(launch_job(
        session_id, state["backend"], state.get("backend_config"), prompt,
        int(arguments.get("timeout_sec", DEFAULT_HARD_TIMEOUT_SEC)), "resume", vendor_session_id,
    ))


def _validate_arguments(arguments: dict) -> None:
    action = arguments.get("action")
    if action not in ({"start", "resume", "status", "messages", "wait", "cancel"} if INSTANCE_ID else {"start", "resume", "status", "messages", "wait", "cancel", "backends"}):
        raise ValueError("unknown Einherjar action")
    timeout = arguments.get("timeout_sec")
    if timeout is not None and (isinstance(timeout, bool) or not isinstance(timeout, int) or timeout < 0):
        raise ValueError("timeout_sec must be a nonnegative integer")
    wait_timeout = arguments.get("wait_timeout_sec")
    if wait_timeout is not None and (
        isinstance(wait_timeout, bool) or not isinstance(wait_timeout, int) or not (1 <= wait_timeout <= MAX_WAIT_TIMEOUT_SEC)
    ):
        raise ValueError(f"wait_timeout_sec must be between 1 and {MAX_WAIT_TIMEOUT_SEC}")
    after = arguments.get("after_revision")
    if after is not None and (isinstance(after, bool) or not isinstance(after, int) or after < 0):
        raise ValueError("after_revision must be a nonnegative integer")
    limit = arguments.get("message_limit")
    if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or not (1 <= limit <= 50)):
        raise ValueError("message_limit must be between 1 and 50")
    if action != "start" and arguments.get("backend") is not None:
        raise ValueError("backend may only be specified for start")
    if action == "start":
        for key in ("plan_path", "prompt", "backend"):
            if arguments.get(key) is not None and not isinstance(arguments[key], str):
                raise ValueError(f"{key} must be a string")
    if action == "resume":
        if not isinstance(arguments.get("session_id"), str) or not isinstance(arguments.get("prompt"), str):
            raise ValueError("resume requires session_id and prompt strings")
    if action in {"status", "messages", "wait", "cancel"} and not isinstance(arguments.get("session_id"), str):
        raise ValueError(f"{action} requires session_id")


if INSTANCE_ID:
    TOOLS[:] = [json.loads((Path(__file__).with_name("ein_tool_schema.json")).read_text(encoding="utf-8"))]


def handle(request: dict) -> dict | None:
    method = request.get("method")
    request_id = request.get("id")
    if method == "initialize":
        requested = request.get("params", {}).get("protocolVersion", "2025-06-18")
        return {"jsonrpc": "2.0", "id": request_id, "result": {"protocolVersion": requested, "capabilities": {"tools": {"listChanged": False}}, "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION}}}
    if method in {"notifications/initialized", "notifications/cancelled"}:
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = request.get("params", {})
        try:
            if params.get("name") != ("ein" if INSTANCE_ID else "worker"):
                raise ValueError(f"unknown tool: {params.get('name')}")
            arguments = params.get("arguments") or {}
            _validate_arguments(arguments)
            action = arguments["action"]
            if action == "start":
                result = start_tool(arguments)
            elif action == "resume":
                result = resume_tool(arguments)
            elif action == "status":
                result = status_tool(arguments)
            elif action == "messages":
                result = messages_tool(arguments)
            elif action == "wait":
                meta = params.get("_meta")
                token = meta.get("progressToken") if isinstance(meta, dict) else None
                result = wait_tool(arguments, token)
            elif action == "cancel":
                result = cancel_tool(arguments)
            else:
                result = backends_tool()
            return {"jsonrpc": "2.0", "id": request_id, "result": result}
        except Exception as exc:
            return {"jsonrpc": "2.0", "id": request_id, "result": text_result({"error": str(exc)}, is_error=True)}
    if request_id is None:
        return None
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--run-job":
        try:
            spec = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
        except Exception as exc:
            sys.stderr.write(f"invalid Einherjar job spec: {exc}\n")
            return 2
        return _run_turn(spec)
    for line in sys.stdin:
        try:
            request = json.loads(line)
            response = handle(request)
            if response is not None:
                emit(response)
        except Exception as exc:
            emit({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(exc)}})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
