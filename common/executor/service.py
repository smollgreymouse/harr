#!/usr/bin/env python3
from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codex_cli import CodexCliAdapter, CodexCliCancelled, CodexCliResult, DEFAULT_MODEL, DEFAULT_REASONING, PROTOCOL

TERMINAL_STATES = {"DONE", "FAILED_EXECUTION", "FAILED_PROTOCOL", "FAILED_GUARDRAIL", "CANCELLED"}


def _state_root() -> Path:
    override = os.environ.get("HARR_EXECUTOR_STATE")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(local) / "HarrState" / "executor"
    xdg = os.environ.get("XDG_STATE_HOME")
    return (Path(xdg) if xdg else Path.home() / ".local" / "state") / "harr" / "executor"


def _private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        try:
            path.chmod(0o700)
        except OSError:
            pass


def _write_private(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if os.name != "nt":
        try:
            path.chmod(0o600)
        except OSError:
            pass


def _canonical_git_root(path: str) -> Path:
    requested = Path(path).expanduser().resolve()
    if not requested.is_dir():
        raise ValueError(f"repo_root is not a directory: {requested}")
    proc = subprocess.run(
        ["git", "-C", str(requested), "rev-parse", "--show-toplevel"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=15,
    )
    if proc.returncode != 0:
        raise ValueError(f"repo_root is not a Git worktree: {requested}")
    root = Path(proc.stdout.strip()).resolve()
    if root != requested:
        raise ValueError(f"repo_root must be the Git worktree root: {root}")
    return root


def _normalize_scope(items: list[str]) -> tuple[str, ...]:
    if not items:
        raise ValueError("allowed_paths must not be empty")
    result: list[str] = []
    for raw in items:
        value = raw.replace("\\", "/").strip()
        if not value or value.startswith("/"):
            raise ValueError(f"invalid allowed path: {raw!r}")
        parts = [part for part in value.split("/") if part not in ("", ".")]
        if not parts or ".." in parts:
            raise ValueError(f"invalid allowed path: {raw!r}")
        normalized = "/".join(parts)
        if value.endswith("/"):
            normalized += "/"
        if normalized not in result:
            result.append(normalized)
    return tuple(result)


def _scope_allows(path: str, patterns: tuple[str, ...]) -> bool:
    normalized = path.replace("\\", "/")
    for pattern in patterns:
        if pattern.endswith("/") and normalized.startswith(pattern):
            return True
        if any(char in pattern for char in "*?[") and fnmatch.fnmatchcase(normalized, pattern):
            return True
        if normalized == pattern:
            return True
    return False


def _fingerprint(path: Path) -> str:
    try:
        if path.is_symlink():
            return "symlink:" + os.readlink(path)
        if not path.exists():
            return "missing"
        if path.is_dir():
            return "directory"
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return "sha256:" + digest.hexdigest()
    except OSError as exc:
        return f"error:{exc.__class__.__name__}:{exc}"


def workspace_snapshot(root: Path) -> dict[str, tuple[str, str]]:
    proc = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=30,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode(errors="replace").strip() or "git status failed")
    chunks = proc.stdout.split(b"\0")
    result: dict[str, tuple[str, str]] = {}
    index = 0
    while index < len(chunks):
        raw = chunks[index]
        index += 1
        if not raw:
            continue
        text = os.fsdecode(raw)
        if len(text) < 4 or text[2] != " ":
            continue
        code = text[:2]
        paths = [text[3:]]
        if ("R" in code or "C" in code) and index < len(chunks) and chunks[index]:
            paths.append(os.fsdecode(chunks[index]))
            index += 1
        for rel in paths:
            rel = rel.replace("\\", "/")
            result[rel] = (code, _fingerprint(root / Path(rel)))
    return result


def workspace_delta(before: dict[str, tuple[str, str]], after: dict[str, tuple[str, str]]) -> list[str]:
    return sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path))


@dataclass
class ExecutorRun:
    run_id: str
    task_label: str
    repo_root: Path
    execution_contract: str
    allowed_paths: tuple[str, ...]
    required_steps: tuple[str, ...]
    required_validation: tuple[str, ...]
    model: str
    reasoning_effort: str
    baseline: dict[str, tuple[str, str]]
    run_dir: Path
    sequence: int = 1
    plan_revision: int = 1
    state: str = "RUNNING"
    session_id: str | None = None
    current_step: str | None = None
    completed_steps: list[str] = field(default_factory=list)
    summary: str = "executor started"
    blocker: dict[str, Any] | None = None
    validation: list[dict[str, Any]] = field(default_factory=list)
    workspace: dict[str, Any] = field(default_factory=lambda: {"changed_paths": [], "out_of_scope": []})
    latest_usage: dict[str, int] = field(default_factory=dict)
    usage_total: dict[str, int] = field(default_factory=dict)
    artifacts: list[str] = field(default_factory=list)
    error: str | None = None
    cancel_event: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None
    condition: threading.Condition = field(default_factory=lambda: threading.Condition(threading.RLock()))


class ExecutorService:
    def __init__(self, *, model: str | None = None, reasoning_effort: str | None = None, state_root: Path | None = None) -> None:
        if os.environ.get("HARR_EXECUTOR_CHILD") == "1":
            raise RuntimeError("executor bridge is disabled inside an executor child")
        self.model = model or os.environ.get("HARR_EXECUTOR_MODEL", DEFAULT_MODEL)
        self.reasoning_effort = reasoning_effort or os.environ.get("HARR_EXECUTOR_REASONING", DEFAULT_REASONING)
        self.state_root = state_root or _state_root()
        _private_dir(self.state_root / "runs")
        self._runs: dict[str, ExecutorRun] = {}
        self._workspace_owners: dict[Path, str] = {}
        self._lock = threading.RLock()

    def start(self, *, repo_root: str, task_label: str, execution_contract: str, allowed_paths: list[str], required_steps: list[str], required_validation: list[str]) -> dict[str, Any]:
        if not task_label.strip():
            raise ValueError("task_label must not be empty")
        if not execution_contract.strip():
            raise ValueError("execution_contract must not be empty")
        if len(execution_contract) > 200_000:
            raise ValueError("execution_contract exceeds 200000 characters")
        root = _canonical_git_root(repo_root)
        scope = _normalize_scope(allowed_paths)
        run_id = "bld_" + uuid.uuid4().hex[:16]
        run_dir = self.state_root / "runs" / run_id
        _private_dir(run_dir)
        baseline = workspace_snapshot(root)
        run = ExecutorRun(
            run_id=run_id,
            task_label=task_label.strip(),
            repo_root=root,
            execution_contract=execution_contract,
            allowed_paths=scope,
            required_steps=tuple(dict.fromkeys(required_steps)),
            required_validation=tuple(dict.fromkeys(required_validation)),
            model=self.model,
            reasoning_effort=self.reasoning_effort,
            baseline=baseline,
            run_dir=run_dir,
        )
        with self._lock:
            owner = self._workspace_owners.get(root)
            if owner:
                raise RuntimeError(f"worktree already has an active Harr executor: {owner}")
            self._workspace_owners[root] = run_id
            self._runs[run_id] = run
        _write_private(run_dir / "execution-contract-r1.md", execution_contract.rstrip() + "\n")
        self._record(run)
        self._launch(run, resolution_delta=None)
        return self.snapshot(run_id)

    def continue_run(self, *, run_id: str, expected_sequence: int, resolution_delta: str) -> dict[str, Any]:
        run = self._get(run_id)
        if not resolution_delta.strip():
            raise ValueError("resolution_delta must not be empty")
        with run.condition:
            if run.state != "BLOCKED":
                raise RuntimeError(f"run {run_id} is not BLOCKED (state={run.state})")
            if run.sequence != expected_sequence:
                raise RuntimeError(f"stale blocker resolution: expected sequence {run.sequence}, got {expected_sequence}")
            if not run.session_id:
                raise RuntimeError("BLOCKED run has no resumable Codex session id")
            run.plan_revision += 1
            run.sequence += 1
            run.state = "RUNNING"
            run.summary = "planner resolution accepted; executor resumed"
            run.blocker = None
            run.error = None
            run.cancel_event = threading.Event()
            _write_private(run.run_dir / f"resolution-r{run.plan_revision}.md", resolution_delta.rstrip() + "\n")
            self._record(run)
            run.condition.notify_all()
        self._launch(run, resolution_delta=resolution_delta)
        return self.snapshot(run_id)

    def wait(self, *, run_id: str, after_sequence: int = 0, timeout_seconds: float = 30.0) -> dict[str, Any]:
        run = self._get(run_id)
        timeout_seconds = max(0.0, min(float(timeout_seconds), 45.0))
        deadline = time.monotonic() + timeout_seconds
        with run.condition:
            while run.sequence <= after_sequence and time.monotonic() < deadline:
                run.condition.wait(timeout=max(0.0, deadline - time.monotonic()))
        return self.snapshot(run_id)

    def cancel(self, *, run_id: str) -> dict[str, Any]:
        run = self._get(run_id)
        with run.condition:
            if run.state in TERMINAL_STATES:
                return self.snapshot(run_id)
            if run.state == "BLOCKED":
                run.state = "CANCELLED"
                run.sequence += 1
                run.summary = "cancelled while blocked"
                self._release_workspace(run)
                self._record(run)
                run.condition.notify_all()
                return self.snapshot(run_id)
            run.cancel_event.set()
            run.summary = "cancellation requested"
            self._record(run)
        return self.snapshot(run_id)

    def inspect(self, *, run_id: str, artifact: str, offset: int = 0, max_chars: int = 12000) -> dict[str, Any]:
        run = self._get(run_id)
        if artifact not in run.artifacts and artifact not in {"execution-contract-r1.md", *[f"resolution-r{i}.md" for i in range(2, run.plan_revision + 1)]}:
            raise ValueError(f"unknown artifact for {run_id}: {artifact}")
        if Path(artifact).name != artifact:
            raise ValueError("artifact must be a simple file name")
        path = run.run_dir / artifact
        if not path.is_file():
            raise ValueError(f"artifact is unavailable: {artifact}")
        text = path.read_text(encoding="utf-8", errors="replace")
        offset = max(0, int(offset))
        max_chars = max(1, min(int(max_chars), 20000))
        return {"run_id": run_id, "artifact": artifact, "offset": offset, "text": text[offset: offset + max_chars], "next_offset": min(len(text), offset + max_chars), "complete": offset + max_chars >= len(text)}

    def snapshot(self, run_id: str) -> dict[str, Any]:
        run = self._get(run_id)
        with run.condition:
            return {
                "protocol": PROTOCOL,
                "run_id": run.run_id,
                "sequence": run.sequence,
                "state": run.state,
                "plan_revision": run.plan_revision,
                "task_label": run.task_label,
                "backend": "codex-cli",
                "model": run.model,
                "reasoning_effort": run.reasoning_effort,
                "current_step": run.current_step,
                "completed_steps": list(run.completed_steps),
                "summary": run.summary,
                "blocker": run.blocker,
                "validation": list(run.validation),
                "workspace": dict(run.workspace),
                "usage": {"latest": dict(run.latest_usage), "total": dict(run.usage_total)},
                "artifacts": list(run.artifacts),
                "error": run.error,
            }

    def _get(self, run_id: str) -> ExecutorRun:
        with self._lock:
            run = self._runs.get(run_id)
        if not run:
            raise KeyError(f"unknown executor run: {run_id}")
        return run

    def _launch(self, run: ExecutorRun, *, resolution_delta: str | None) -> None:
        def worker() -> None:
            adapter = CodexCliAdapter(model=run.model, reasoning_effort=run.reasoning_effort)
            try:
                if resolution_delta is None:
                    result = adapter.start(repo_root=run.repo_root, execution_contract=run.execution_contract, cancel_event=run.cancel_event)
                else:
                    assert run.session_id is not None
                    result = adapter.resume(repo_root=run.repo_root, session_id=run.session_id, resolution_delta=resolution_delta, cancel_event=run.cancel_event)
            except CodexCliCancelled:
                self._finish_cancelled(run)
            except Exception as exc:
                self._finish_error(run, exc)
            else:
                self._finish_result(run, result)

        thread = threading.Thread(target=worker, name=f"harr-executor-{run.run_id}", daemon=True)
        run.thread = thread
        thread.start()

    def _finish_result(self, run: ExecutorRun, result: CodexCliResult) -> None:
        events_name = f"events-r{run.plan_revision}.ndjson"
        stderr_name = f"stderr-r{run.plan_revision}.txt"
        _write_private(run.run_dir / events_name, "".join(json.dumps(event, ensure_ascii=False) + "\n" for event in result.stdout_events))
        _write_private(run.run_dir / stderr_name, result.stderr)
        with run.condition:
            run.artifacts.extend(name for name in (events_name, stderr_name) if name not in run.artifacts)
            run.session_id = result.session_id
            run.latest_usage = dict(result.usage)
            for key, value in result.usage.items():
                run.usage_total[key] = run.usage_total.get(key, 0) + value
            packet = result.packet
            run.current_step = packet.get("current_step")
            run.completed_steps = list(packet.get("completed_steps", []))
            run.validation = list(packet.get("validation", []))
            run.blocker = packet.get("blocker")
            run.summary = packet.get("summary", "")
            model_state = str(packet.get("state"))
            after = workspace_snapshot(run.repo_root)
            changed_paths = workspace_delta(run.baseline, after)
            out_of_scope = [path for path in changed_paths if not _scope_allows(path, run.allowed_paths)]
            reported = sorted(str(path).replace("\\", "/") for path in packet.get("changed_files", []))
            run.workspace = {"changed_paths": changed_paths, "out_of_scope": out_of_scope, "reported_changed_files": reported}
            if out_of_scope:
                run.state = "FAILED_GUARDRAIL"
                run.error = "executor changed paths outside allowed scope: " + ", ".join(out_of_scope)
            elif model_state == "DONE":
                missing_steps = [step for step in run.required_steps if step not in set(run.completed_steps)]
                passed = {str(item.get("check")) for item in run.validation if item.get("status") == "PASS"}
                missing_validation = [check for check in run.required_validation if check not in passed]
                if missing_steps or missing_validation:
                    run.state = "FAILED_PROTOCOL"
                    details: list[str] = []
                    if missing_steps:
                        details.append("missing completed steps: " + ", ".join(missing_steps))
                    if missing_validation:
                        details.append("missing PASS validation: " + ", ".join(missing_validation))
                    run.error = "; ".join(details)
                else:
                    run.state = "DONE"
            elif model_state == "BLOCKED":
                run.state = "BLOCKED"
                if not isinstance(run.blocker, dict):
                    run.state = "FAILED_PROTOCOL"
                    run.error = "BLOCKED packet has no blocker"
            elif model_state in {"FAILED_EXECUTION", "FAILED_PROTOCOL", "CANCELLED"}:
                run.state = model_state
            else:
                run.state = "FAILED_PROTOCOL"
                run.error = f"unexpected model state: {model_state}"
            run.sequence += 1
            if run.state in TERMINAL_STATES:
                self._release_workspace(run)
            self._record(run)
            run.condition.notify_all()

    def _finish_cancelled(self, run: ExecutorRun) -> None:
        with run.condition:
            run.state = "CANCELLED"
            run.sequence += 1
            run.summary = "Codex executor process cancelled"
            run.error = None
            self._release_workspace(run)
            self._record(run)
            run.condition.notify_all()

    def _finish_error(self, run: ExecutorRun, exc: Exception) -> None:
        with run.condition:
            run.state = "FAILED_EXECUTION"
            run.sequence += 1
            run.summary = "Codex executor failed"
            run.error = f"{exc.__class__.__name__}: {exc}"
            self._release_workspace(run)
            self._record(run)
            run.condition.notify_all()

    def _release_workspace(self, run: ExecutorRun) -> None:
        with self._lock:
            if self._workspace_owners.get(run.repo_root) == run.run_id:
                del self._workspace_owners[run.repo_root]

    def _record(self, run: ExecutorRun) -> None:
        payload = self.snapshot(run.run_id) if run.run_id in self._runs else {
            "protocol": PROTOCOL,
            "run_id": run.run_id,
            "sequence": run.sequence,
            "state": run.state,
        }
        _write_private(run.run_dir / "run.json", json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
