#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
EXECUTOR_DIR = ROOT / "common" / "executor"
sys.path.insert(0, str(EXECUTOR_DIR))
import service  # noqa: E402


def run(*args: str, cwd: Path | None = None) -> None:
    subprocess.run(args, cwd=cwd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def make_fake(path: Path) -> None:
    path.write_text(
        r'''#!/usr/bin/env python3
import json, os, pathlib, sys, time
args = sys.argv[1:]
if args == ["--version"]:
    print("codex-cli fake")
    raise SystemExit(0)
repo = pathlib.Path(args[args.index("--cd") + 1])
last = pathlib.Path(args[args.index("--output-last-message") + 1])
prompt = sys.stdin.read()
resume = "resume" in args
session = args[args.index("resume") + 1] if resume else "0199-service-session"
print(json.dumps({"type":"thread.started","thread_id":session}))
base = {
    "protocol":"harr.executor.v1",
    "current_step":None,
    "completed_steps":["B001"],
    "summary":"done",
    "changed_files":[],
    "validation":[{"check":"unit","status":"PASS","detail":"ok"}],
    "blocker":None,
}
if "SLOW_EXECUTOR" in prompt:
    time.sleep(30)
    packet = dict(base, state="DONE")
elif "VIOLATE_SCOPE" in prompt:
    (repo / "outside.txt").write_text("bad\n", encoding="utf-8")
    packet = dict(base, state="DONE", changed_files=["outside.txt"])
elif "MISSING_VALIDATION" in prompt:
    (repo / "src" / "a.txt").write_text("changed missing validation\n", encoding="utf-8")
    packet = dict(base, state="DONE", changed_files=["src/a.txt"], validation=[])
elif not resume:
    packet = {
        "protocol":"harr.executor.v1",
        "state":"BLOCKED",
        "current_step":"B001",
        "completed_steps":[],
        "summary":"planner decision needed",
        "changed_files":[],
        "validation":[],
        "blocker":{
            "class":"UNSPECIFIED_DESIGN_DECISION",
            "step":"B001",
            "fact":"fixture requires a fixed value",
            "decision_needed":"choose the prescribed value",
            "evidence":["src/a.txt"],
        },
    }
else:
    (repo / "src" / "a.txt").write_text("changed by luna\n", encoding="utf-8")
    packet = dict(base, state="DONE", changed_files=["src/a.txt"])
last.write_text(json.dumps(packet), encoding="utf-8")
print(json.dumps({"type":"turn.completed","usage":{"input_tokens":100,"cached_input_tokens":10,"output_tokens":20,"reasoning_output_tokens":3}}))
''',
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def wait_terminal(svc: service.ExecutorService, run_id: str, sequence: int) -> dict:
    current = svc.wait(run_id=run_id, after_sequence=sequence, timeout_seconds=10)
    assert current["sequence"] > sequence, current
    return current


with tempfile.TemporaryDirectory() as tmp_raw:
    tmp = Path(tmp_raw)
    fake = tmp / "codex"
    make_fake(fake)
    repo = tmp / "repo"
    repo.mkdir()
    run("git", "init", "-q", str(repo))
    run("git", "config", "user.email", "fixture@example.invalid", cwd=repo)
    run("git", "config", "user.name", "Fixture", cwd=repo)
    (repo / "src").mkdir()
    (repo / "src" / "a.txt").write_text("initial\n", encoding="utf-8")
    run("git", "add", ".", cwd=repo)
    run("git", "commit", "-qm", "fixture", cwd=repo)

    old_path = os.environ.get("PATH", "")
    old_state = os.environ.get("HARR_EXECUTOR_STATE")
    os.environ["PATH"] = f"{tmp}{os.pathsep}{old_path}"
    os.environ["HARR_EXECUTOR_STATE"] = str(tmp / "state")
    try:
        svc = service.ExecutorService()

        started = svc.start(
            repo_root=str(repo),
            task_label="blocked-resume",
            execution_contract="# HARR EXECUTOR CONTRACT v1\nNORMAL_EXECUTOR",
            allowed_paths=["src/a.txt"],
            required_steps=["B001"],
            required_validation=["unit"],
        )
        assert started["state"] == "RUNNING" and started["sequence"] == 1
        blocked = wait_terminal(svc, started["run_id"], 1)
        assert blocked["state"] == "BLOCKED" and blocked["sequence"] == 2
        try:
            svc.continue_run(run_id=started["run_id"], expected_sequence=1, resolution_delta="use fixed value")
            raise AssertionError("stale resolution was accepted")
        except RuntimeError as exc:
            assert "stale blocker resolution" in str(exc)
        resumed = svc.continue_run(run_id=started["run_id"], expected_sequence=2, resolution_delta="# HARR PLANNER RESOLUTION v1\nUse the fixed fixture value.")
        assert resumed["state"] == "RUNNING" and resumed["sequence"] == 3
        done = wait_terminal(svc, started["run_id"], 3)
        assert done["state"] == "DONE", done
        assert done["workspace"]["changed_paths"] == ["src/a.txt"]
        assert done["workspace"]["out_of_scope"] == []
        assert done["usage"]["total"]["input_tokens"] == 200
        assert (repo / "src" / "a.txt").read_text(encoding="utf-8") == "changed by luna\n"

        run("git", "checkout", "--", "src/a.txt", cwd=repo)
        violated = svc.start(
            repo_root=str(repo), task_label="scope", execution_contract="VIOLATE_SCOPE",
            allowed_paths=["src/a.txt"], required_steps=["B001"], required_validation=["unit"],
        )
        violated = wait_terminal(svc, violated["run_id"], 1)
        assert violated["state"] == "FAILED_GUARDRAIL", violated
        assert violated["workspace"]["out_of_scope"] == ["outside.txt"]
        (repo / "outside.txt").unlink()

        missing = svc.start(
            repo_root=str(repo), task_label="validation", execution_contract="MISSING_VALIDATION",
            allowed_paths=["src/a.txt"], required_steps=["B001"], required_validation=["unit"],
        )
        missing = wait_terminal(svc, missing["run_id"], 1)
        assert missing["state"] == "FAILED_PROTOCOL", missing
        assert "missing PASS validation: unit" in (missing["error"] or "")
        run("git", "checkout", "--", "src/a.txt", cwd=repo)

        slow = svc.start(
            repo_root=str(repo), task_label="slow", execution_contract="SLOW_EXECUTOR",
            allowed_paths=["src/a.txt"], required_steps=["B001"], required_validation=["unit"],
        )
        try:
            svc.start(
                repo_root=str(repo), task_label="second-writer", execution_contract="NORMAL_EXECUTOR",
                allowed_paths=["src/a.txt"], required_steps=["B001"], required_validation=["unit"],
            )
            raise AssertionError("second writer was accepted")
        except RuntimeError as exc:
            assert "active Harr executor" in str(exc)
        svc.cancel(run_id=slow["run_id"])
        cancelled = wait_terminal(svc, slow["run_id"], 1)
        assert cancelled["state"] == "CANCELLED", cancelled
    finally:
        os.environ["PATH"] = old_path
        if old_state is None:
            os.environ.pop("HARR_EXECUTOR_STATE", None)
        else:
            os.environ["HARR_EXECUTOR_STATE"] = old_state

print("executor service state/guard/resume: PASS")
