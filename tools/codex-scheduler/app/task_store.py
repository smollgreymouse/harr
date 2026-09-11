#!/usr/bin/env python3
from __future__ import annotations

import fcntl
import json
import os
import signal
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ACTIVE_STATUSES = {"draft", "scheduled", "running", "cancelling"}
FINISHED_STATUSES = {"completed", "failed", "cancelled"}
ALL_STATUSES = ACTIVE_STATUSES | FINISHED_STATUSES


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def app_state_dir() -> Path:
    base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
    root = base / "harr-codex-scheduler"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temp_name, path)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def update_task_file(path: Path, patch: dict[str, Any]) -> dict[str, Any]:
    """Merge a patch into one task file under a per-task advisory lock."""
    path = Path(path)
    lock_path = path.with_suffix(path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        current: dict[str, Any] = {}
        if path.exists():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    current = loaded
            except (OSError, json.JSONDecodeError):
                current = {}
        current.update(patch)
        current["updated_at"] = utc_now()
        _atomic_write_json(path, current)
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    return current


class TaskStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root is not None else app_state_dir()
        self.tasks_dir = self.root / "tasks"
        self.jobs_dir = self.root / "jobs"
        self.ui_path = self.root / "ui.json"
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self.jobs_dir.mkdir(parents=True, exist_ok=True)

    def task_path(self, task_id: str) -> Path:
        return self.tasks_dir / f"{task_id}.json"

    def new_draft(self) -> dict[str, Any]:
        task_id = uuid.uuid4().hex
        now = utc_now()
        task: dict[str, Any] = {
            "id": task_id,
            "status": "draft",
            "created_at": now,
            "updated_at": now,
            "model": "gpt-5.6-terra",
            "reasoning": "high",
            "speed": "standard",
            "session": "",
            "scheduled": None,
            "cwd": None,
            "prompt": "",
            "at_job": None,
            "pid": None,
            "log": str(self.jobs_dir / f"{task_id}.jsonl"),
            "answer": None,
            "cancel_requested": False,
            "error": None,
            "started_at": None,
            "finished_at": None,
        }
        _atomic_write_json(self.task_path(task_id), task)
        return task

    def load(self, task_id: str) -> dict[str, Any] | None:
        path = self.task_path(task_id)
        if not path.exists():
            return None
        try:
            task = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(task, dict) or task.get("id") != task_id:
            return None
        return task

    def save(self, task: dict[str, Any]) -> dict[str, Any]:
        task_id = str(task["id"])
        status = str(task.get("status", "draft"))
        if status not in ALL_STATUSES:
            raise ValueError(f"unsupported task status: {status}")
        return update_task_file(self.task_path(task_id), task)

    def patch(self, task_id: str, **patch: Any) -> dict[str, Any]:
        if "status" in patch and patch["status"] not in ALL_STATUSES:
            raise ValueError(f"unsupported task status: {patch['status']}")
        return update_task_file(self.task_path(task_id), patch)

    def list(self) -> list[dict[str, Any]]:
        tasks: list[dict[str, Any]] = []
        for path in self.tasks_dir.glob("*.json"):
            task = self.load(path.stem)
            if task is not None:
                tasks.append(task)
        tasks.sort(key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""), reverse=True)
        return tasks

    def active(self) -> list[dict[str, Any]]:
        return [task for task in self.list() if task.get("status") in ACTIVE_STATUSES]

    def finished(self) -> list[dict[str, Any]]:
        return [task for task in self.list() if task.get("status") in FINISHED_STATUSES]

    def load_ui(self) -> dict[str, Any]:
        try:
            value = json.loads(self.ui_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"open_task_ids": [], "current_task_id": None}
        return value if isinstance(value, dict) else {"open_task_ids": [], "current_task_id": None}

    def save_ui(self, open_task_ids: list[str], current_task_id: str | None) -> None:
        _atomic_write_json(self.ui_path, {
            "open_task_ids": list(dict.fromkeys(open_task_ids)),
            "current_task_id": current_task_id,
            "updated_at": utc_now(),
        })

    def cancel(self, task_id: str, atrm_bin: str | None = None) -> dict[str, Any]:
        task = self.load(task_id)
        if task is None:
            raise KeyError(task_id)
        status = str(task.get("status"))
        if status not in {"scheduled", "running", "cancelling"}:
            return task

        self.patch(task_id, cancel_requested=True, status="cancelling")
        if status == "scheduled" and task.get("at_job"):
            atrm = atrm_bin or os.environ.get("ATRM_BIN", "atrm")
            proc = subprocess.run([atrm, str(task["at_job"])], text=True, capture_output=True)
            if proc.returncode == 0:
                return self.patch(task_id, status="cancelled", finished_at=utc_now(), pid=None)

        current = self.load(task_id) or task
        pid = current.get("pid")
        if pid:
            try:
                os.killpg(int(pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
            except PermissionError as exc:
                raise RuntimeError(f"cannot terminate running task {task_id}: {exc}") from exc
            return self.patch(task_id, status="cancelling", cancel_requested=True)

        if status == "scheduled":
            raise RuntimeError("at job could not be removed and the task has not reported a running pid")
        return self.patch(task_id, status="cancelling", cancel_requested=True)

    def delete(self, task_id: str, *, delete_log: bool = True, delete_answer: bool = False) -> None:
        task = self.load(task_id)
        if task is None:
            return
        if task.get("status") in {"scheduled", "running", "cancelling"}:
            raise RuntimeError("cancel an active task before deleting it")

        paths: list[Path] = []
        if delete_log and task.get("log"):
            paths.append(Path(str(task["log"])).expanduser())
        if delete_answer and task.get("answer"):
            paths.append(Path(str(task["answer"])).expanduser())
        for path in paths:
            try:
                path.unlink()
            except FileNotFoundError:
                pass

        task_path = self.task_path(task_id)
        try:
            task_path.unlink()
        except FileNotFoundError:
            pass
        try:
            task_path.with_suffix(task_path.suffix + ".lock").unlink()
        except FileNotFoundError:
            pass

    @staticmethod
    def is_empty_draft(task: dict[str, Any]) -> bool:
        return (
            task.get("status") == "draft"
            and not str(task.get("session") or "").strip()
            and not str(task.get("prompt") or "").strip()
            and not task.get("scheduled")
            and not task.get("answer")
        )
