#!/usr/bin/env python3
"""Real-subprocess reliability regression tests for the detached worker bridges.

Covers the lifecycle contract shared by the private GigaCode runtime and Einherjar:
hard timeout, cooperative cancel, SIGKILL escalation when a child ignores
SIGTERM, owner-loss evidence persistence, dead-worker status, restart gating,
and cache-root cleanup after terminal transitions.

Real child processes are used with tiny poll intervals; no live agent CLI,
no network, no pytest.
"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from contextlib import ExitStack
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
IS_POSIX = os.name != "nt"
IS_LINUX = sys.platform.startswith("linux")

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


# Sandbox the whole cache tree before importing either server: both modules
# resolve CACHE_ROOT from XDG_CACHE_HOME at import time and create it.
_TMP = tempfile.TemporaryDirectory(prefix="worker-rel-")
SANDBOX = Path(_TMP.name)
os.environ["XDG_CACHE_HOME"] = str(SANDBOX / "xdg-cache")


def _load_server(rel_path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / rel_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gc = _load_server("common/executor/gigacode_runtime.py", "worker_rel_gigacode")
ein = _load_server("common/mcp/einherjar_server.py", "worker_rel_einherjar")

FAST_POLL = 0.05
# Real grace windows inside _terminate_process_tree (5s TERM + 5s KILL) bound
# the worst case; joins must exceed that so a hung loop fails the test, not
# the harness.
TERMINATE_UPPER_BOUND_SEC = 14.0


def sandboxed(module, cache_name: str, sandbox: Path, executable: str | None = None,
              poll: float | None = FAST_POLL, chat_none: bool = True):
    """Enter patches that isolate one scenario: cache root, cwd, fake CLI, fast poll."""
    stack = ExitStack()
    cache = sandbox / cache_name
    cache.mkdir(parents=True, exist_ok=True)
    stack.enter_context(patch.object(module, "ROOT", sandbox))
    stack.enter_context(patch.object(module, "CACHE_ROOT", cache))
    if executable is not None:
        stack.enter_context(patch.object(module.shutil, "which", return_value=executable))
    if chat_none and hasattr(module, "_find_chat_path"):
        stack.enter_context(patch.object(module, "_find_chat_path", return_value=None))
    if poll is not None and hasattr(module, "POLL_INTERVAL_SEC"):
        stack.enter_context(patch.object(module, "POLL_INTERVAL_SEC", poll))
    return stack


def fake_cli(sandbox: Path, name: str, body: str) -> str:
    path = sandbox / name
    path.write_text("#!/usr/bin/env python3\n" + body, encoding="utf-8")
    path.chmod(0o755)
    return str(path)


SLEEPER_BODY = "import time; time.sleep(30)\n"

TERM_IGNORER_BODY = (
    "import signal, sys, time\n"
    "from pathlib import Path\n"
    "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
    "Path(sys.argv[1]).write_text('ready')\n"
    "time.sleep(30)\n"
)


def spawner_body(pid_path: Path) -> str:
    # The bridge passes its own argv, so the pid path is baked into the script.
    return (
        "import subprocess, sys, time\n"
        f"pid_path = r'{pid_path}'\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
        "with open(pid_path, 'w') as handle:\n"
        "    handle.write(str(child.pid))\n"
        "time.sleep(30)\n"
    )

FAILED_HANDOFF = {
    "status": "FAILED",
    "summary": "reliability-test finisher",
    "changed": [],
    "verified": [],
    "escalation": None,
    "blockers": [{"kind": "other", "detail": "synthetic finisher", "evidence": "n/a"}],
}

FINISHER_BODY = "import json\nprint(json.dumps(" + json.dumps(FAILED_HANDOFF) + "))\n"


def wait_for(predicate, timeout: float, interval: float = 0.02) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


def run_in_thread(fn) -> tuple[threading.Thread, list]:
    """Run fn() in a thread; capture ('ok', value) or ('error', exc)."""
    result: list = []

    def target():
        try:
            result.append(("ok", fn()))
        except Exception as exc:
            result.append(("error", exc))

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    return thread, result


def dead_pid() -> int:
    """Return a pid that has exited and been reaped."""
    probe = subprocess.Popen([sys.executable, "-c", "pass"])
    pid = probe.pid
    probe.wait()
    return pid


def assert_pid_gone(pid, label: str, timeout: float = 5.0) -> None:
    if pid is None:
        check(label, False, "no pid recorded")
        return

    def gone():
        if os.name == "nt":
            return not gc._pid_alive(pid)
        try:
            os.kill(pid, 0)
        except OSError:
            return True
        return False

    check(label, wait_for(gone, timeout), f"pid {pid} still alive")


def runtime_log_lines(module, session_id: str) -> list[str]:
    try:
        text = module._runtime_log_path(session_id).read_text(encoding="utf-8")
    except OSError:
        return []
    return [line for line in text.splitlines() if line.strip()]


def json_events(lines: list[str]) -> list[dict]:
    events = []
    for line in lines:
        parts = line.split(" ", 1)
        if len(parts) != 2:
            continue
        try:
            value = json.loads(parts[1])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            events.append(value)
    return events


def no_job_or_control_files(module, label: str) -> None:
    leftovers = [
        item.name
        for item in module.CACHE_ROOT.iterdir()
        if item.name.endswith(".job.json") or item.name.endswith(".control.json")
    ]
    check(label, not leftovers, f"leftover control/job files: {leftovers}")


# =====================================================================
# A. GigaCode bridge: hard timeout with a real subprocess
# =====================================================================
with tempfile.TemporaryDirectory(prefix="worker-rel-a-") as tmpdir:
    sandbox = Path(tmpdir)
    sid = str(uuid.uuid4())
    executable = fake_cli(sandbox, "sleeper", SLEEPER_BODY)
    with sandboxed(gc, "cache", sandbox, executable=executable):
        thread, result = run_in_thread(lambda: gc.run_gigacode(
            sid, ["--session-id", sid], "test", 1, job_id="job-a",
        ))
        thread.join(10)
        check("A0: run_gigacode returned after timeout", bool(result) and result[0][0] == "ok",
              "worker did not return within 10s" if not result else repr(result))
        if result and result[0][0] == "ok":
            exit_code, _output, _stderr = result[0][1]
            state = gc._load_state(sid)
            check("A1: hard timeout exits 124", exit_code == 124, f"got {exit_code}")
            check("A2: state phase=timed_out with exit_code=124",
                  bool(state) and state.get("phase") == "timed_out" and state.get("exit_code") == 124,
                  f"phase={state.get('phase') if state else None}")
            check("A3: TIMEOUT event in runtime.log",
                  any("TIMEOUT" in line for line in runtime_log_lines(gc, sid)))
            assert_pid_gone((state or {}).get("pid"), "A4: timed-out CLI process reaped")
            no_job_or_control_files(gc, "A5: no leftover job/control files after timeout")

# =====================================================================
# B. GigaCode bridge: cooperative cancel via control file
# =====================================================================
with tempfile.TemporaryDirectory(prefix="worker-rel-b-") as tmpdir:
    sandbox = Path(tmpdir)
    sid = str(uuid.uuid4())
    executable = fake_cli(sandbox, "sleeper", SLEEPER_BODY)
    with sandboxed(gc, "cache", sandbox, executable=executable):
        thread, result = run_in_thread(lambda: gc.run_gigacode(
            sid, ["--session-id", sid], "test", 0, job_id="job-b",
        ))
        state_seen = wait_for(lambda: (gc._load_state(sid) or {}).get("pid"), 5)
        check("B0: running state with pid appeared", bool(state_seen))
        gc._request_cancel(sid, "job-b")
        thread.join(10)
        check("B0b: worker returned after cancel", bool(result) and result[0][0] == "ok",
              repr(result))
        if result and result[0][0] == "ok":
            exit_code, _output, stderr = result[0][1]
            state = gc._load_state(sid)
            check("B1: cancel exits -15", exit_code == -15, f"got {exit_code}")
            check("B2: cancel summary mentions manual cancellation", "manually cancelled" in stderr)
            check("B3: state phase=cancelled",
                  bool(state) and state.get("phase") == "cancelled",
                  f"phase={state.get('phase') if state else None}")
            check("B4: control file removed after cancel",
                  not gc._control_path(sid, "job-b").exists())
            check("B5: CANCEL event in runtime.log",
                  any("CANCEL" in line for line in runtime_log_lines(gc, sid)))
            assert_pid_gone((state or {}).get("pid"), "B6: cancelled CLI process reaped")
            no_job_or_control_files(gc, "B7: no leftover job/control files after cancel")

# =====================================================================
# C. _terminate_process_tree escalates to SIGKILL and reaps
# =====================================================================
if IS_POSIX:
    with tempfile.TemporaryDirectory(prefix="worker-rel-c-") as tmpdir:
        sandbox = Path(tmpdir)
        ready_file = sandbox / "ignorer.ready"
        executable = fake_cli(sandbox, "term-ignorer", TERM_IGNORER_BODY)
        proc = subprocess.Popen(
            [executable, str(ready_file)], cwd=sandbox,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        # The SIGTERM handler must be installed before the group kill, or the
        # child dies from the default action and the test proves nothing.
        check("C0: ignorer installed its SIGTERM handler",
              wait_for(ready_file.is_file, 5), "ready file missing")
        started = time.monotonic()
        gc._terminate_process_tree(proc)
        duration = time.monotonic() - started
        check("C1: SIGTERM-ignoring child killed via SIGKILL", proc.returncode == -9,
              f"returncode={proc.returncode}")
        check("C2: escalation finished within the TERM+KILL grace bound",
              duration < TERMINATE_UPPER_BOUND_SEC, f"took {duration:.1f}s")
        try:
            os.kill(proc.pid, 0)
            check("C3: child reaped, pid gone", False, "os.kill succeeded")
        except OSError:
            check("C3: child reaped, pid gone", True)
else:
    print("SKIP C (POSIX only)")

# =====================================================================
# D. Timeout kills the whole process group (no orphaned grandchildren)
# =====================================================================
if IS_POSIX:
    with tempfile.TemporaryDirectory(prefix="worker-rel-d-") as tmpdir:
        sandbox = Path(tmpdir)
        sid = str(uuid.uuid4())
        pid_file = sandbox / "grandchild.pid"
        executable = fake_cli(sandbox, "spawner", spawner_body(pid_file))
        with sandboxed(gc, "cache", sandbox, executable=executable):
            thread, result = run_in_thread(lambda: gc.run_gigacode(
                sid, ["--session-id", sid], "test", 1, job_id="job-d",
            ))
            thread.join(10)
            check("D0: spawner timed out",
                  bool(result) and result[0][0] == "ok" and result[0][1][0] == 124,
                  repr(result))
            grandchild = None
            try:
                grandchild = int(pid_file.read_text().strip())
            except (OSError, ValueError):
                check("D1: grandchild pid recorded", False, "pid file missing")
            if grandchild:
                assert_pid_gone(grandchild, "D2: grandchild killed with the process group")
else:
    print("SKIP D (POSIX only)")

# =====================================================================
# E. GigaCode bridge: owner loss persists evidence and kills the tree
# =====================================================================
if IS_LINUX:
    with tempfile.TemporaryDirectory(prefix="worker-rel-e-") as tmpdir:
        sandbox = Path(tmpdir)
        sid = str(uuid.uuid4())
        executable = fake_cli(sandbox, "sleeper", SLEEPER_BODY)
        owner = {"pid": os.getpid(), "start_ticks": gc._owner_identity(os.getpid())}
        with sandboxed(gc, "cache", sandbox, executable=executable):
            thread, result = run_in_thread(lambda: gc.run_gigacode(
                sid, ["--session-id", sid], "test", 0, job_id="job-e", owner=owner,
            ))
            wait_for(lambda: (gc._load_state(sid) or {}).get("pid"), 5)
            owner["start_ticks"] = "-1"  # simulate PID reuse of the owner
            thread.join(TERMINATE_UPPER_BOUND_SEC)
            check("E0: worker returned after owner loss", bool(result) and result[0][0] == "ok",
                  repr(result))
            if result and result[0][0] == "ok":
                exit_code, _output, _stderr = result[0][1]
                state = gc._load_state(sid)
                check("E1: owner loss exits -15", exit_code == -15, f"got {exit_code}")
                check("E2: state cancel_reason=owner_disconnected",
                      bool(state) and state.get("cancel_reason") == "owner_disconnected",
                      f"cancel_reason={state.get('cancel_reason') if state else None}")
                evidence = (state or {}).get("owner_loss") or {}
                check("E3: state embeds MCP_OWNER_LOST evidence",
                      evidence.get("event") == "MCP_OWNER_LOST",
                      f"evidence keys={sorted(evidence)[:6]}")
                check("E4: evidence classified for bridge restart",
                      evidence.get("classification") == "owner_disappeared_possible_bridge_restart")
                disk_events = json_events(runtime_log_lines(gc, sid))
                check("E5: JSON evidence persisted to runtime.log before termination",
                      any(item.get("event") == "MCP_OWNER_LOST" for item in disk_events),
                      f"json events={[item.get('event') for item in disk_events]}")
                assert_pid_gone((state or {}).get("pid"), "E6: CLI killed on owner loss")
else:
    print("SKIP E (Linux only)")

# =====================================================================
# F. Einherjar bridge: timeout, cancel, owner loss via _run_turn
# =====================================================================
if IS_LINUX:
    def ein_spec(sandbox: Path, sid: str, job_id: str, executable: str,
                 timeout_sec: int, owner: dict | None) -> dict:
        job_path = sandbox / f"{sid}.{job_id}.job.json"
        job_path.write_text("{}", encoding="utf-8")
        return {
            "session_id": sid, "job_id": job_id, "backend": "reliability-fake",
            "backend_config": {"start": [executable]},
            "prompt": "test", "mode": "start", "timeout_sec": timeout_sec,
            "owner": owner, "job_path": str(job_path),
        }

    with tempfile.TemporaryDirectory(prefix="worker-rel-f-") as tmpdir:
        sandbox = Path(tmpdir)
        executable = fake_cli(sandbox, "sleeper", SLEEPER_BODY)
        saved_poll = ein.POLL_INTERVAL_SEC
        ein.POLL_INTERVAL_SEC = FAST_POLL

        # F1: timeout
        sid = str(uuid.uuid4())
        thread, result = run_in_thread(lambda: ein._run_turn(dict(
            ein_spec(sandbox, sid, "job-f1", executable, 1, None))))
        thread.join(10)
        check("F1a: einherjar timeout returns", bool(result) and result[0][0] == "ok", repr(result))
        if result and result[0][0] == "ok":
            state = ein._load_state(sid)
            check("F1b: phase=finished with exit_code=124",
                  bool(state) and state.get("phase") == "finished" and state.get("exit_code") == 124,
                  f"phase={state.get('phase') if state else None} exit={state.get('exit_code') if state else None}")
            handoff = (state or {}).get("handoff") or {}
            blocker = (handoff.get("blockers") or [{}])[0].get("detail", "")
            check("F1c: timeout handoff is FAILED with timeout evidence",
                  handoff.get("status") == "FAILED" and "timeout" in blocker.lower(),
                  f"handoff={json.dumps(handoff)[:200]}")
            no_job_or_control_files(ein, "F1d: job spec cleaned after timeout")
            check("F1e: END recorded in runtime.log",
                  any("END" in line for line in runtime_log_lines(ein, sid)))

        # F2: cancel
        sid2 = str(uuid.uuid4())
        thread, result = run_in_thread(lambda: ein._run_turn(dict(
            ein_spec(sandbox, sid2, "job-f2", executable, 0, None))))
        wait_for(lambda: (ein._load_state(sid2) or {}).get("phase") == "running", 5)
        ein._request_cancel(sid2, "job-f2")
        thread.join(10)
        check("F2a: einherjar cancel returns", bool(result) and result[0][0] == "ok", repr(result))
        if result and result[0][0] == "ok":
            state = ein._load_state(sid2)
            check("F2b: cancelled exit -15", state.get("exit_code") == -15,
                  f"exit={state.get('exit_code')}")
            check("F2c: control file removed",
                  not ein._control_path(sid2, "job-f2").exists())
            assert_pid_gone(state.get("pid"), "F2d: cancelled CLI reaped")
            no_job_or_control_files(ein, "F2e: no leftover files after cancel")

        # F3: owner loss
        sid3 = str(uuid.uuid4())
        owner = {"pid": os.getpid(), "start_ticks": ein._owner_identity(os.getpid())}
        thread, result = run_in_thread(lambda: ein._run_turn(dict(
            ein_spec(sandbox, sid3, "job-f3", executable, 0, owner))))
        wait_for(lambda: (ein._load_state(sid3) or {}).get("phase") == "running", 5)
        owner["start_ticks"] = "-1"
        thread.join(TERMINATE_UPPER_BOUND_SEC)
        check("F3a: einherjar owner loss returns", bool(result) and result[0][0] == "ok",
              repr(result))
        if result and result[0][0] == "ok":
            state = ein._load_state(sid3)
            check("F3b: owner-loss exit -15 with FAILED handoff",
                  state.get("exit_code") == -15
                  and (state.get("handoff") or {}).get("status") == "FAILED",
                  f"exit={state.get('exit_code')}")
            check("F3c: OWNER_LOST logged",
                  any("OWNER_LOST" in line for line in runtime_log_lines(ein, sid3)))
            assert_pid_gone(state.get("pid"), "F3d: CLI killed on owner loss")

        ein.POLL_INTERVAL_SEC = saved_poll
else:
    print("SKIP F (Linux only)")

# =====================================================================
# G. Dead worker detection: status reports FAILED, not RUNNING
# =====================================================================
with tempfile.TemporaryDirectory(prefix="worker-rel-g-") as tmpdir:
    sandbox = Path(tmpdir)
    gone = dead_pid()
    live = os.getpid()

    # GigaCode
    sid = str(uuid.uuid4())
    with sandboxed(gc, "cache-g", sandbox):
        gc._write_state(sid, {"phase": "running", "session_id": sid, "job_id": "job-g",
                              "pid": gone, "worker_pid": None, "elapsed_sec": 5.0})
        status = json.loads(gc.status_tool({"session_id": sid})["content"][0]["text"])
        check("G1: gigacode dead worker status is FAILED", status.get("status") == "FAILED",
              f"status={status.get('status')}")
        check("G2: FAILED carries evidence blocker",
              bool(status.get("blockers")) and "phase=running" in status["blockers"][0].get("evidence", ""),
              f"blockers={json.dumps(status.get('blockers'))[:150]}")
        gc._write_state(sid, {**gc._load_state(sid), "pid": live, "worker_pid": live})
        status = json.loads(gc.status_tool({"session_id": sid})["content"][0]["text"])
        check("G3: gigacode live worker status is RUNNING", status.get("status") == "RUNNING",
              f"status={status.get('status')}")
        gc._state_path(sid).unlink(missing_ok=True)

    # Einherjar
    sid = str(uuid.uuid4())
    with sandboxed(ein, "cache-e-g", sandbox, poll=None):
        ein._write_state(sid, {"phase": "running", "session_id": sid, "job_id": "job-g",
                               "pid": gone, "worker_pid": None, "elapsed_sec": 5.0,
                               "backend": "reliability-fake", "startup_confirmed": True})
        status = json.loads(ein.status_tool({"session_id": sid})["content"][0]["text"])
        check("G4: einherjar dead worker status is FAILED", status.get("status") == "FAILED",
              f"status={status.get('status')}")
        ein._write_state(sid, {**ein._load_state(sid), "pid": live, "worker_pid": live})
        status = json.loads(ein.status_tool({"session_id": sid})["content"][0]["text"])
        check("G5: einherjar live worker status is RUNNING/STARTING",
              status.get("status") in {"RUNNING", "STARTING"}, f"status={status.get('status')}")
        ein._state_path(sid).unlink(missing_ok=True)

# =====================================================================
# H. Restart gating: live sessions are rejected, dead sessions accept a
#    new job end-to-end through the real detached worker process.
#    The detached child re-imports the server module, so it derives
#    CACHE_ROOT from XDG_CACHE_HOME; scenarios here stay on the module's
#    env-derived cache root instead of patching it.
# =====================================================================
if IS_POSIX:
    bin_dir = SANDBOX / "rel-path-bin"
    bin_dir.mkdir(exist_ok=True)
    finisher = bin_dir / "gigacode"
    finisher.write_text("#!/usr/bin/env python3\n" + FINISHER_BODY, encoding="utf-8")
    finisher.chmod(0o755)
    saved_path = os.environ.get("PATH")
    worker_path = str(bin_dir) if not saved_path else str(bin_dir) + os.pathsep + saved_path

    def handoff_result_ok(result, label: str) -> None:
        check(label,
              isinstance(result, dict) and (
                  (result.get("handoff") or {}).get("status") == "FAILED"
                  if "handoff" in result else result.get("status") == "FAILED"
              ),
              f"result={json.dumps(result)[:200]}")

    # H1: a live fake state blocks a second job
    sid = str(uuid.uuid4())
    gc._write_state(sid, {"phase": "running", "session_id": sid, "job_id": "job-h-live",
                          "pid": os.getpid(), "worker_pid": os.getpid()})
    try:
        gc.launch_detached_job(sid, ["--session-id", sid], "test", 0)
        check("H1: live session blocks a second job", False, "no ValueError raised")
    except ValueError as exc:
        check("H1: live session blocks a second job", "already has a running" in str(exc),
              f"exc={exc}")
    gc._state_path(sid).unlink(missing_ok=True)

    # H2: a cancelled (dead) session accepts a new job end-to-end; the
    # detached worker runs, parses the finisher handoff, and cleans up.
    sid = str(uuid.uuid4())
    gc._write_state(sid, {"phase": "cancelled", "session_id": sid, "job_id": "job-h-old",
                          "pid": dead_pid(), "worker_pid": None})
    os.environ["PATH"] = worker_path
    try:
        with patch.object(gc, "_find_chat_path", return_value=None):
            result = gc.launch_detached_job(sid, ["--session-id", sid], "test", 0)
    finally:
        if saved_path is not None:
            os.environ["PATH"] = saved_path
    handoff_result_ok(result, "H2: restart after cancel returns the worker handoff")
    state = gc._load_state(sid)
    check("H3: restarted session finished with handoff",
          bool(state) and state.get("phase") == "finished"
          and (state.get("handoff") or {}).get("status") == "FAILED",
          f"phase={state.get('phase') if state else None}")
    no_job_or_control_files(gc, "H4: detached worker cleaned its job spec")
    check("H5: HANDOFF recorded in runtime.log",
          any("HANDOFF" in line for line in runtime_log_lines(gc, sid)))
    gc._state_path(sid).unlink(missing_ok=True)
    for leftover in gc.CACHE_ROOT.glob(f"{sid}.*"):
        leftover.unlink(missing_ok=True)

    # H6: einherjar launch_job accepts a dead session end-to-end.
    sid = str(uuid.uuid4())
    ein._write_state(sid, {"phase": "finished", "session_id": sid, "job_id": "job-h-ein-old",
                           "pid": dead_pid(), "worker_pid": None,
                           "backend": "reliability-fake"})
    try:
        result = ein.launch_job(sid, "reliability-fake", {"start": [str(finisher)]},
                                "test", 0, "start")
    finally:
        pass
    handoff_result_ok(result, "H6: einherjar restart returns the worker handoff")
    state = ein._load_state(sid)
    check("H7: einherjar restarted session finished",
          bool(state) and state.get("phase") == "finished",
          f"phase={state.get('phase') if state else None}")
    no_job_or_control_files(ein, "H8: einherjar worker cleaned its job spec")
    ein._state_path(sid).unlink(missing_ok=True)
    for leftover in ein.CACHE_ROOT.glob(f"{sid}.*"):
        leftover.unlink(missing_ok=True)
else:
    print("SKIP H (POSIX only)")

# =====================================================================
# I. Reliability fixes: PID-reuse guard, artifact pruning, corrupt
#    state reporting, owner-loss evidence parity, chat-path cache, RSS.
# =====================================================================
if IS_LINUX:
    with tempfile.TemporaryDirectory(prefix="worker-rel-i-") as tmpdir:
        sandbox = Path(tmpdir)
        live = os.getpid()
        real_ticks = gc._pid_start_ticks(live)

        # I1: a reused PID must not resurrect a finished worker's RUNNING status
        sid = str(uuid.uuid4())
        with sandboxed(gc, "cache-i", sandbox):
            gc._write_state(sid, {"phase": "running", "session_id": sid, "job_id": "job-i1",
                                  "pid": live, "pid_start_ticks": "-1",  # mismatch: PID reuse
                                  "worker_pid": None, "elapsed_sec": 5.0})
            status = json.loads(gc.status_tool({"session_id": sid})["content"][0]["text"])
            check("I1a: gigacode reused PID reports FAILED, not RUNNING",
                  status.get("status") == "FAILED", f"status={status.get('status')}")
            gc._write_state(sid, {**gc._load_state(sid), "pid_start_ticks": real_ticks})
            status = json.loads(gc.status_tool({"session_id": sid})["content"][0]["text"])
            check("I1b: matching start ticks keep RUNNING", status.get("status") == "RUNNING",
                  f"status={status.get('status')}")
            gc._write_state(sid, {**gc._load_state(sid), "pid_start_ticks": None})
            status = json.loads(gc.status_tool({"session_id": sid})["content"][0]["text"])
            check("I1c: legacy state without ticks stays RUNNING (backward compat)",
                  status.get("status") == "RUNNING", f"status={status.get('status')}")
            gc._state_path(sid).unlink(missing_ok=True)

        sid = str(uuid.uuid4())
        with sandboxed(ein, "cache-i-ein", sandbox, poll=None):
            ein._write_state(sid, {"phase": "running", "session_id": sid, "job_id": "job-i2",
                                   "pid": live, "pid_start_ticks": "-1",
                                   "worker_pid": None, "elapsed_sec": 5.0,
                                   "backend": "reliability-fake", "startup_confirmed": True})
            status = json.loads(ein.status_tool({"session_id": sid})["content"][0]["text"])
            check("I2: einherjar reused PID reports FAILED, not RUNNING",
                  status.get("status") == "FAILED", f"status={status.get('status')}")
            ein._state_path(sid).unlink(missing_ok=True)
else:
    print("SKIP I1-I2 (Linux only)")

with tempfile.TemporaryDirectory(prefix="worker-rel-i3-") as tmpdir:
    sandbox = Path(tmpdir)
    # I3: stale artifacts are pruned, lifecycle files never are
    for module, cache_name in ((gc, "cache-i3-gc"), (ein, "cache-i3-ein")):
        with sandboxed(module, cache_name, sandbox, poll=None):
            stale = time.time() - 2 * module._artifact_retention_sec()
            stale_files = [
                module.CACHE_ROOT / "00000000-0000-0000-0000-000000000000.turn.stdout",
                module.CACHE_ROOT / "00000000-0000-0000-0000-000000000000.turn.stderr",
                module.CACHE_ROOT / "00000000-0000-0000-0000-000000000000.r1.worker.log",
                module.CACHE_ROOT / "00000000-0000-0000-0000-000000000000.runtime.log",
            ]
            for item in stale_files:
                item.write_text("stale", encoding="utf-8")
                os.utime(item, (stale, stale))
            keep_files = [
                module.CACHE_ROOT / "00000000-0000-0000-0000-000000000000.state.json",
                module.CACHE_ROOT / "00000000-0000-0000-0000-000000000000.j1.job.json",
                module.CACHE_ROOT / "00000000-0000-0000-0000-000000000000.j1.control.json",
            ]
            for item in keep_files:
                item.write_text("{}", encoding="utf-8")
                os.utime(item, (stale, stale))
            fresh = module.CACHE_ROOT / "11111111-1111-1111-1111-111111111111.turn.stdout"
            fresh.write_text("fresh", encoding="utf-8")
            removed = module._prune_worker_artifacts()
            tag = "gigacode" if module is gc else "einherjar"
            check(f"I3a[{tag}]: stale artifacts pruned",
                  removed == len(stale_files) and not any(f.exists() for f in stale_files),
                  f"removed={removed}")
            check(f"I3b[{tag}]: state/job/control files survive pruning",
                  all(f.exists() for f in keep_files))
            check(f"I3c[{tag}]: fresh artifacts survive", fresh.exists())
            os.environ["HARR_WORKER_RETENTION_SEC"] = "0"
            try:
                check(f"I3d[{tag}]: retention=0 disables pruning",
                      module._prune_worker_artifacts() == 0)
            finally:
                os.environ.pop("HARR_WORKER_RETENTION_SEC", None)

# I4: corrupt state is reported as a STATE_CORRUPT event, status stays UNKNOWN
with tempfile.TemporaryDirectory(prefix="worker-rel-i4-") as tmpdir:
    sandbox = Path(tmpdir)
    for module, cache_name, tag in ((gc, "cache-i4-gc", "gigacode"), (ein, "cache-i4-ein", "einherjar")):
        with sandboxed(module, cache_name, sandbox, poll=None):
            sid = str(uuid.uuid4())
            module._state_path(sid).write_text("{not json at all", encoding="utf-8")
            loaded = module._load_state(sid)
            check(f"I4a[{tag}]: corrupt state loads as None", loaded is None)
            events = json_events(runtime_log_lines(module, sid))
            corrupt = [item for item in events if item.get("event") == "STATE_CORRUPT"]
            check(f"I4b[{tag}]: STATE_CORRUPT event recorded with path and error",
                  bool(corrupt) and corrupt[0].get("path", "").endswith(".state.json")
                  and bool(corrupt[0].get("error")),
                  f"events={[item.get('event') for item in events]}")
            status = json.loads(module.status_tool({"session_id": sid})["content"][0]["text"])
            check(f"I4c[{tag}]: status remains UNKNOWN for corrupt state",
                  status.get("status") == "UNKNOWN", f"status={status.get('status')}")

# I5: einherjar owner-loss evidence parity with the gigacode bridge
if IS_LINUX:
    with tempfile.TemporaryDirectory(prefix="worker-rel-i5-") as tmpdir:
        sandbox = Path(tmpdir)
        sid = str(uuid.uuid4())
        executable = fake_cli(sandbox, "sleeper", SLEEPER_BODY)
        owner = {"pid": os.getpid(), "start_ticks": ein._owner_identity(os.getpid())}
        saved_poll = ein.POLL_INTERVAL_SEC
        ein.POLL_INTERVAL_SEC = FAST_POLL
        with sandboxed(ein, "cache-i5", sandbox, poll=None):
            job_path = sandbox / f"{sid}.job-i5.job.json"
            job_path.write_text("{}", encoding="utf-8")
            thread, result = run_in_thread(lambda: ein._run_turn({
                "session_id": sid, "job_id": "job-i5", "backend": "reliability-fake",
                "backend_config": {"start": [executable]}, "prompt": "test",
                "mode": "start", "timeout_sec": 0, "owner": owner,
                "job_path": str(job_path),
            }))
            wait_for(lambda: (ein._load_state(sid) or {}).get("phase") == "running", 5)
            owner["start_ticks"] = "-1"
            thread.join(TERMINATE_UPPER_BOUND_SEC)
            check("I5a: einherjar owner loss returns", bool(result) and result[0][0] == "ok",
                  repr(result))
            state = ein._load_state(sid) or {}
            evidence = state.get("owner_loss") or {}
            check("I5b: state embeds MCP_OWNER_LOST evidence",
                  evidence.get("event") == "MCP_OWNER_LOST"
                  and evidence.get("classification") == "owner_disappeared_possible_bridge_restart",
                  f"evidence={json.dumps(evidence)[:150]}")
            check("I5c: state cancel_reason=owner_disconnected",
                  state.get("cancel_reason") == "owner_disconnected",
                  f"cancel_reason={state.get('cancel_reason')}")
            disk_events = json_events(runtime_log_lines(ein, sid))
            check("I5d: JSON OWNER_LOST event persisted to runtime.log",
                  any(item.get("event") == "MCP_OWNER_LOST" for item in disk_events),
                  f"events={[item.get('event') for item in disk_events]}")
        ein.POLL_INTERVAL_SEC = saved_poll
else:
    print("SKIP I5 (Linux only)")

# I6: chat-path cache returns stable paths and re-globs after invalidation
with tempfile.TemporaryDirectory(prefix="worker-rel-i6-") as tmpdir:
    sandbox = Path(tmpdir)
    sid = str(uuid.uuid4())
    chat = sandbox / ".gigacode" / "projects" / "ws" / "chats" / f"{sid}.jsonl"
    chat.parent.mkdir(parents=True, exist_ok=True)
    chat.touch()
    with patch.object(gc.Path, "home", return_value=sandbox):
        first = gc._find_chat_path(sid)
        check("I6a: chat path discovered", first == chat, f"got {first}")
        second = gc._find_chat_path(sid)
        check("I6b: cached path is stable", second == chat)
        chat.unlink()
        chat.parent.rmdir()
        check("I6c: missing chat falls back to a fresh glob (None)",
              gc._find_chat_path(sid) is None)

# I7: RSS instrumentation emits structured events for the agent CLI
if IS_LINUX:
    with tempfile.TemporaryDirectory(prefix="worker-rel-i7-") as tmpdir:
        sandbox = Path(tmpdir)
        sid = str(uuid.uuid4())
        executable = fake_cli(sandbox, "sleeper", SLEEPER_BODY)
        saved_poll = ein.POLL_INTERVAL_SEC
        saved_rss = ein.RSS_LOG_INTERVAL_SEC
        ein.POLL_INTERVAL_SEC = FAST_POLL
        ein.RSS_LOG_INTERVAL_SEC = 0.2
        with sandboxed(ein, "cache-i7", sandbox, poll=None):
            job_path = sandbox / f"{sid}.job-i7.job.json"
            job_path.write_text("{}", encoding="utf-8")
            thread, result = run_in_thread(lambda: ein._run_turn({
                "session_id": sid, "job_id": "job-i7", "backend": "reliability-fake",
                "backend_config": {"start": [executable]}, "prompt": "test",
                "mode": "start", "timeout_sec": 2, "owner": None,
                "job_path": str(job_path),
            }))
            thread.join(15)
            check("I7a: rss-monitored run returns", bool(result) and result[0][0] == "ok",
                  repr(result))
            rss_events = [item for item in json_events(runtime_log_lines(ein, sid))
                          if item.get("event") == "RSS"]
            check("I7b: RSS events recorded for the CLI process",
                  bool(rss_events) and all(isinstance(item.get("rss_kb"), int) for item in rss_events),
                  f"rss events={len(rss_events)}")
        ein.POLL_INTERVAL_SEC = saved_poll
        ein.RSS_LOG_INTERVAL_SEC = saved_rss
else:
    print("SKIP I7 (Linux only)")

_TMP.cleanup()
print(f"\nWorker reliability tests: {tests_passed} passed, {tests_failed} failed")
raise SystemExit(1 if tests_failed else 0)
