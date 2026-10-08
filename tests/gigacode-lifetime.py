#!/usr/bin/env python3
"""Deterministic tests for GigaCode lifetime behaviour.

Uses mocked subprocess.Popen and time.monotonic/time.time to simulate
the run_gigacode worker loop without real processes or wall-clock waits.
All state/control files go into a TemporaryDirectory sandbox.
"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = ROOT / "common" / "mcp" / "gigacode_server.py"

spec = importlib.util.spec_from_file_location("harr_gigacode_server", SERVER_PATH)
assert spec and spec.loader
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)

tests_passed = 0
tests_failed = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global tests_passed, tests_failed
    if condition:
        tests_passed += 1
    else:
        tests_failed += 1
        msg = f"FAIL: {label}"
        if detail:
            msg += f" — {detail}"
        print(msg)


def _sandboxed_server(base: Path) -> type:
    """Return a fresh import of the server module with CACHE_ROOT under *base*."""
    # We can't easily re-import, so we monkey-patch CACHE_ROOT on the existing module
    server.CACHE_ROOT = base / "cache"
    server.CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    return server


def _make_mock_process(returncode: int | None = None) -> MagicMock:
    """Return a MagicMock that looks like a subprocess.Popen."""
    proc = MagicMock(spec=subprocess.Popen)
    proc.pid = 12345
    proc.returncode = returncode
    proc.poll.return_value = returncode
    proc.stdout = None
    proc.stderr = None
    proc.stdin = None
    return proc


class FakeTime:
    """Deterministic fake for time.monotonic() and time.time().

    Advances by a configurable delta on each access.
    """

    def __init__(self, start: float = 1000.0, delta: float = 1.0):
        self._now = start
        self._delta = delta
        self._lock = threading.Lock()

    def monotonic(self) -> float:
        with self._lock:
            val = self._now
            self._now += self._delta
            return val

    def time(self) -> float:
        return self.monotonic()

    def advance(self, secs: float) -> None:
        with self._lock:
            self._now += secs


# ======================================================================
# Helper: run the run_gigacode loop with mocked dependencies
# ======================================================================


def run_gigacode_with_mocks(
    session_id: str,
    timeout_sec: int,
    *,
    fake_time: FakeTime,
    process_ticks_before_exit: int,
    fake_chat_path: Path | None = None,
    cancel_after_tick: int | None = None,
    job_id: str | None = "test-job-001",
) -> tuple[int, str, str]:
    """Execute run_gigacode with mocked Popen, time, chat, and optional cancel.

    The mock process stays alive for *process_ticks_before_exit* loop iterations
    (each tick advances fake_time by its delta). Returns (exit_code, output, stderr).
    """

    # Mock shutil.which to return a fake executable path
    def fake_which(name: str) -> str | None:
        if name == "gigacode":
            return "/usr/bin/fake-gigacode"
        return None

    # Mock Popen
    mock_proc = _make_mock_process(returncode=None)

    def fake_popen(*args, **kwargs):
        # Simulate process life: stay alive for N ticks, then exit 0
        tick = [0]

        def fake_poll():
            tick[0] += 1
            if tick[0] >= process_ticks_before_exit:
                mock_proc.returncode = 0
                return 0
            return None

        mock_proc.poll = fake_poll
        mock_proc.pid = 12345
        return mock_proc

    # Mock _find_chat_path: return fake_chat_path if provided, else None
    original_find_chat = server._find_chat_path
    if fake_chat_path is not None:
        fake_chat_path.touch()
    else:
        fake_chat_path_obj = None

    def fake_find_chat(sid: str) -> Path | None:
        if fake_chat_path is not None and fake_chat_path.exists():
            return fake_chat_path
        return None

    # Mock time
    def fake_sleep(secs: float) -> None:
        # Advance fake time instead of actually sleeping
        fake_time.advance(secs)

    def fake_monotonic() -> float:
        return fake_time.monotonic()

    def fake_time_func() -> float:
        return fake_time.time()

    # Mock _tail_chat_events to return empty
    original_tail_events = server._tail_chat_events
    server._tail_chat_events = lambda sid, limit=12: []

    # Mock _terminate_process_tree to avoid real os.killpg
    original_terminate = server._terminate_process_tree

    def fake_terminate(process: object) -> None:
        # Simulate termination by setting returncode so poll sees it
        if hasattr(process, "poll") and callable(process.poll):
            if process.poll() is None:
                process.returncode = -15

    server._terminate_process_tree = fake_terminate

    # Enable cancel after specific tick count
    if cancel_after_tick is not None:
        server._request_cancel(session_id, job_id)

    # Patch time.monotonic, time.time and time.sleep on the server module
    # so the worker loop doesn't use wall clock
    original_server_monotonic = server.time.monotonic
    original_server_time = server.time.time
    original_server_sleep = server.time.sleep
    server.time.monotonic = fake_monotonic
    server.time.time = fake_time_func
    server.time.sleep = fake_sleep

    patches = [
        patch.object(server, "_find_chat_path", fake_find_chat),
    ]

    for p in patches:
        p.start()

    # Directly patch the module-level references used inside run_gigacode
    original_shutil_which = server.shutil.which
    server.shutil.which = fake_which
    original_subprocess_Popen = server.subprocess.Popen
    server.subprocess.Popen = fake_popen

    try:
        exit_code, output, stderr = server.run_gigacode(
            session_id,
            ["--session-id", session_id],
            "test prompt",
            timeout_sec,
            job_id=job_id,
        )
    finally:
        server.time.monotonic = original_server_monotonic
        server.time.time = original_server_time
        server.time.sleep = original_server_sleep
        for p in patches:
            p.stop()
        server._terminate_process_tree = original_terminate
        server.shutil.which = original_shutil_which
        server.subprocess.Popen = original_subprocess_Popen
        server._find_chat_path = original_find_chat
        server._tail_chat_events = original_tail_events

    return exit_code, output, stderr


# ======================================================================
# Tests
# ======================================================================

# -----------------------------------------------------------------------
# A: Default (timeout=0) survives far beyond old 900s and 300s stall
# -----------------------------------------------------------------------
with tempfile.TemporaryDirectory(prefix="gigacode-lt-") as tmpdir:
    srv = _sandboxed_server(Path(tmpdir))
    sid = str(server.uuid.uuid4())

    # Simulate 2000 seconds of wall time (well past old 900s hard limit)
    # and 400 seconds of inactivity (past old 300s stall) using slow-progress pattern
    ft = FakeTime(start=5000.0, delta=15.0)  # 15s per loop tick
    # Process lives for 150 ticks = 2250 simulated seconds
    exit_code, output, stderr = run_gigacode_with_mocks(
        sid,
        timeout_sec=0,
        fake_time=ft,
        process_ticks_before_exit=150,
    )
    check("A1: default 0 timeout exits cleanly after >2000s simulated",
          exit_code == 0,
          f"got exit_code={exit_code}")

    # Check that state was written during the loop and preserves job_id
    state = server._load_state(sid)
    check("A2: state has job_id after run_gigacode",
          state is not None and state.get("job_id") == "test-job-001")
    check("A3: state elapsed_sec is tracked",
          state is not None and state.get("elapsed_sec", 0) > 0)

# -----------------------------------------------------------------------
# B: Explicit positive timeout_sec terminates at deadline
# -----------------------------------------------------------------------
with tempfile.TemporaryDirectory(prefix="gigacode-lt-") as tmpdir:
    srv = _sandboxed_server(Path(tmpdir))
    sid = str(server.uuid.uuid4())
    ft = FakeTime(start=10000.0, delta=1.0)
    # 30 ticks at 1s each = 30s simulated, timeout is 25s
    # Process would return 0 at tick 30 but timeout at 25s should win
    exit_code, output, stderr = run_gigacode_with_mocks(
        sid,
        timeout_sec=25,
        fake_time=ft,
        process_ticks_before_exit=30,
    )
    # After 25 ticks the timeout check elapses >= 25 and terminates
    check("B1: positive timeout terminates with exit_code 124",
          exit_code == 124,
          f"got exit_code={exit_code}")
    check("B2: timeout summary mentions 'hard timeout' or 'TIMEOUT'",
          "TIMEOUT" in stderr or "hard timeout" in stderr,
          f"stderr={stderr[:200]}")

# -----------------------------------------------------------------------
# C: Matching cancel terminates the correct process
# -----------------------------------------------------------------------
with tempfile.TemporaryDirectory(prefix="gigacode-lt-") as tmpdir:
    srv = _sandboxed_server(Path(tmpdir))
    sid = str(server.uuid.uuid4())
    jid = "cancel-target-job"
    ft = FakeTime(start=20000.0, delta=1.0)
    # Write cancel request before starting
    server._request_cancel(sid, jid)
    # Process would live 100 ticks but cancel at tick 1 should win
    exit_code, output, stderr = run_gigacode_with_mocks(
        sid,
        timeout_sec=0,
        fake_time=ft,
        process_ticks_before_exit=100,
        job_id=jid,
    )
    check("C1: matching cancel terminates with exit_code -15",
          exit_code == -15,
          f"got exit_code={exit_code}")
    check("C2: cancel summary identifies manual cancellation",
          "manually cancelled" in stderr,
          f"stderr={stderr[:300]}")
    check("C3: cancel summary mentions resumable session",
          "resumable" in stderr,
          f"stderr={stderr[:300]}")
    # Cancel control file should be cleaned up
    check("C4: control file cleaned up after cancel",
          not server._check_cancel_request(sid, jid))

# -----------------------------------------------------------------------
# D: Stale cancel (different job_id) does not affect a resumed job
# -----------------------------------------------------------------------
with tempfile.TemporaryDirectory(prefix="gigacode-lt-") as tmpdir:
    srv = _sandboxed_server(Path(tmpdir))
    sid = str(server.uuid.uuid4())
    # Write cancel for old job
    server._request_cancel(sid, "old-job-id")
    ft = FakeTime(start=30000.0, delta=1.0)
    # New job with different job_id — cancel for "old-job-id" should NOT match
    exit_code, output, stderr = run_gigacode_with_mocks(
        sid,
        timeout_sec=0,
        fake_time=ft,
        process_ticks_before_exit=5,
        job_id="new-job-id",
    )
    check("D1: stale cancel does not affect new job, exits cleanly",
          exit_code == 0,
          f"got exit_code={exit_code}")
    server._cleanup_control(sid, "old-job-id")

# -----------------------------------------------------------------------
# E: Stable job_id survives in state across loop iterations
# -----------------------------------------------------------------------
with tempfile.TemporaryDirectory(prefix="gigacode-lt-") as tmpdir:
    srv = _sandboxed_server(Path(tmpdir))
    sid = str(server.uuid.uuid4())
    ft = FakeTime(start=40000.0, delta=2.0)
    run_gigacode_with_mocks(
        sid,
        timeout_sec=0,
        fake_time=ft,
        process_ticks_before_exit=10,
        job_id="stable-job-42",
    )
    state = server._load_state(sid)
    check("E1: job_id stable in final state",
          state is not None and state.get("job_id") == "stable-job-42")
    check("E2: turn key present in final state",
          state is not None and state.get("turn") is not None and isinstance(state["turn"], str))

# -----------------------------------------------------------------------
# F: status_tool exposes cancel_requested when cancel file exists
# -----------------------------------------------------------------------
with tempfile.TemporaryDirectory(prefix="gigacode-lt-") as tmpdir:
    srv = _sandboxed_server(Path(tmpdir))
    sid = str(server.uuid.uuid4())
    jid = "status-cancel-test"
    # Write running state WITH job_id (as run_gigacode now does)
    srv._write_state(sid, {
        "phase": "running",
        "session_id": sid,
        "job_id": jid,
        "pid": os.getpid(),
        "worker_pid": os.getpid(),
        "elapsed_sec": 10.0,
        "timeout_sec": 0,
        "hard_timeout_sec": 0,
        "stall_elapsed_sec": 2.0,
    })
    # Write cancel request
    srv._request_cancel(sid, jid)
    status_resp = srv.status_tool({"session_id": sid})
    status_data = json.loads(status_resp["content"][0]["text"])
    check("F1: status shows cancel_requested=true",
          status_data.get("runtime", {}).get("cancel_requested") is True)
    check("F2: status shows hard_timeout_sec=0",
          status_data.get("runtime", {}).get("hard_timeout_sec") == 0)
    check("F3: status shows stall_elapsed_sec",
          status_data.get("runtime", {}).get("stall_elapsed_sec") == 2.0)
    srv._cleanup_control(sid, jid)
    srv._state_path(sid).unlink(missing_ok=True)

# -----------------------------------------------------------------------
# G: Parse_worker_handoff correctly handles cancelled handoff
# -----------------------------------------------------------------------
cancel_handoff = json.dumps({
    "status": "FAILED",
    "summary": "GigaCode was manually cancelled by the planner. Session remains resumable: abc-123.",
    "changed": [],
    "verified": [],
    "escalation": None,
    "blockers": [{"kind": "other", "detail": "manual cancellation", "evidence": "session remains resumable"}],
})
parsed, is_error = server.parse_worker_handoff(cancel_handoff, 0, "")
check("G1: cancel handoff parses as FAILED",
      parsed["status"] == "FAILED" and is_error is True)
check("G2: cancel summary mentions manual cancellation",
      "manually cancelled" in parsed["summary"])

# -----------------------------------------------------------------------
# H: Deterministic handshake test: timeout_sec=0 gives full 20s startup window
# -----------------------------------------------------------------------
# Simulate launch_detached_job's handshake loop with mocked dependencies.
# When timeout_sec=0, confirm_deadline = STARTUP_CONFIRM_TIMEOUT_SEC (20s),
# NOT min(20, max(1, 0)) = 1s.  We verify the handshake waits for chat
# activity appearing after ~15 simulated seconds.
with tempfile.TemporaryDirectory(prefix="gigacode-lt-") as tmpdir:
    srv = _sandboxed_server(Path(tmpdir))
    sid = str(server.uuid.uuid4())
    jid = "handshake-test-job"

    # Build a fake job file so _load_job_spec doesn't fail
    job_path = server._job_path(sid, jid)
    job_path.parent.mkdir(parents=True, exist_ok=True)
    job_path.write_text(json.dumps({
        "session_id": sid,
        "session_args": ["--session-id", sid],
        "prompt": "test",
        "timeout_sec": 0,
    }), encoding="utf-8")

    # Mock: Popen creates a fake process that exits 0 eventually
    handshake_ft = FakeTime(start=50000.0, delta=1.0)
    handshake_proc = _make_mock_process(returncode=None)
    poll_count = [0]

    def handshake_poll():
        poll_count[0] += 1
        if poll_count[0] >= 100:
            handshake_proc.returncode = 0
            return 0
        return None

    handshake_proc.poll = handshake_poll

    def handshake_popen(*args, **kwargs):
        return handshake_proc

    # Mock _load_state for worker status: handoff appears at loop tick 15
    original_load_state = server._load_state
    handshake_tick = [0]
    server._load_state = lambda sid_arg: (
        handshake_tick.__setitem__(0, handshake_tick[0] + 1) or
        ({
            "phase": "finished",
            "session_id": sid_arg,
            "job_id": jid,
            "handoff": {"status": "DONE", "summary": "ok"},
        } if handshake_tick[0] >= 15 else None)
    )

    # Patch time on the server module
    orig_mono = server.time.monotonic
    orig_time = server.time.time
    orig_sleep = server.time.sleep
    server.time.monotonic = handshake_ft.monotonic
    server.time.time = handshake_ft.time
    server.time.sleep = lambda s: handshake_ft.advance(s)

    # Patch subprocess on the server module
    orig_popen = server.subprocess.Popen
    server.subprocess.Popen = handshake_popen

    try:
        result = server.launch_detached_job(sid, ["--session-id", sid], "test", 0)
    finally:
        server.time.monotonic = orig_mono
        server.time.time = orig_time
        server.time.sleep = orig_sleep
        server.subprocess.Popen = orig_popen
        server._load_state = original_load_state

    check("H1: handshake with timeout_sec=0 completes within 20 simulated seconds (not STARTING/FAILED)",
          result.get("status") in ("RUNNING", "DONE"),
          f"got status={result.get('status')}")
    check("H2: handshake completed (not STARTING)",
          result.get("status") != "STARTING",
          f"got {result.get('status')}")
    # Verify the constant is indeed 20
    check("H3: STARTUP_CONFIRM_TIMEOUT_SEC unchanged at 20",
          server.STARTUP_CONFIRM_TIMEOUT_SEC == 20.0)

# -----------------------------------------------------------------------
# I: Cancel of finished or already-stopped session returns appropriate status
# -----------------------------------------------------------------------
with tempfile.TemporaryDirectory(prefix="gigacode-lt-") as tmpdir:
    srv = _sandboxed_server(Path(tmpdir))
    finished_sid = str(server.uuid.uuid4())
    srv._write_state(finished_sid, {"phase": "finished", "session_id": finished_sid, "handoff": {"status": "DONE"}})
    finished_cancel = srv.cancel_tool({"session_id": finished_sid})
    finished_data = json.loads(finished_cancel["content"][0]["text"])
    check("I1: cancel on finished session returns ALREADY_FINISHED",
          finished_data["status"] == "ALREADY_FINISHED")
    srv._state_path(finished_sid).unlink(missing_ok=True)

# -----------------------------------------------------------------------
# J: No false RUNNING status after cancellation
# -----------------------------------------------------------------------
# The handoff path in status_tool returns the handoff directly (not RUNNING)
# when state has a handoff dict
with tempfile.TemporaryDirectory(prefix="gigacode-lt-") as tmpdir:
    srv = _sandboxed_server(Path(tmpdir))
    done_sid = str(server.uuid.uuid4())
    srv._write_state(done_sid, {
        "phase": "finished",
        "session_id": done_sid,
        "handoff": {"status": "DONE", "summary": "ok", "changed": [], "verified": [], "escalation": None, "blockers": []},
    })
    status_resp = srv.status_tool({"session_id": done_sid})
    status_data = json.loads(status_resp["content"][0]["text"])
    check("J1: cancelled terminal status is DONE, not RUNNING",
          status_data.get("status") == "DONE",
          f"got status={status_data.get('status')}")
    srv._state_path(done_sid).unlink(missing_ok=True)

print(f"\nGigaCode lifetime tests: {tests_passed} passed, {tests_failed} failed")
raise SystemExit(1 if tests_failed else 0)