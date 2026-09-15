#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QDateTime, Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from datetime_picker import ScheduleTimeDialog, default_run_time
from session_cwd import SessionResolutionError, resolve_session_cwd
from task_page_native import STATUS_ICON, task_display_title
from task_store import ACTIVE_STATUSES, TaskStore

APP_NAME = "Harr Codex Scheduler"


def session_title(session: dict[str, Any]) -> str:
    value = " ".join(str(session.get("name") or session.get("preview") or "Codex session").split())
    return value or "Codex session"


def session_menu_label(session: dict[str, Any], duplicate_names: set[str]) -> str:
    title = session_title(session)
    label = title
    if title in duplicate_names:
        cwd = str(session.get("cwd") or "")
        project = Path(cwd).name if cwd else ""
        if project:
            label = f"{title} · {project}"
    return label if len(label) <= 64 else label[:63] + "…"


def active_task_menu_label(task: dict[str, Any]) -> str:
    status = str(task.get("status") or "draft")
    title = task_display_title(task, 46)
    scheduled = str(task.get("scheduled") or "")
    when = scheduled.replace("T", " ")[5:16] if scheduled else ""
    suffix = f" · {when}" if when else ""
    return f"{STATUS_ICON.get(status, '•')} {title}{suffix}"


def schedule_quick_task(
    store: TaskStore,
    *,
    session_id: str,
    prompt: str,
    run_time: QDateTime,
    model: str = "gpt-5.6-terra",
    reasoning: str = "high",
    speed: str = "standard",
) -> dict[str, Any]:
    session_id = session_id.strip()
    prompt = prompt.strip()
    if not session_id or not prompt:
        raise RuntimeError("Session and prompt are required.")
    if not run_time.isValid() or run_time <= QDateTime.currentDateTime():
        raise RuntimeError("Run time must be in the future.")

    try:
        cwd = resolve_session_cwd(session_id)
    except SessionResolutionError as exc:
        raise RuntimeError(f"Cannot safely resolve the session working directory:\n{exc}") from exc

    task = store.new_draft()
    task_id = str(task["id"])
    task_path = store.task_path(task_id)
    log_path = Path(str(task.get("log") or store.jobs_dir / f"{task_id}.jsonl"))
    scheduler = Path(__file__).resolve().parents[1] / "bin" / "codex-schedule"
    timestamp = run_time.toString("yyyyMMddHHmm")
    args = [
        str(scheduler),
        "--model", model,
        "--reasoning", reasoning,
        "--speed", speed,
        "--timestamp", timestamp,
        "--session", session_id,
        "--prompt", prompt,
        "--log-json", str(log_path),
        "--task-state", str(task_path),
    ]
    proc = subprocess.run(args, text=True, capture_output=True)
    combined = (proc.stdout + proc.stderr).strip()
    if proc.returncode != 0:
        store.delete(task_id, delete_log=True, delete_answer=False)
        raise RuntimeError(combined or f"Scheduler failed with exit code {proc.returncode}")

    match = re.search(r"\bjob\s+(\d+)\b", combined)
    return store.patch(
        task_id,
        status="scheduled",
        at_job=match.group(1) if match else None,
        model=model,
        reasoning=reasoning,
        speed=speed,
        session=session_id,
        prompt=prompt,
        scheduled=run_time.toString(Qt.DateFormat.ISODate),
        cwd=str(cwd),
        log=str(log_path),
        answer=None,
        cancel_requested=False,
        error=None,
    )


class QuickScheduleDialog(QDialog):
    """Small tray-first composer: session is fixed, only time + prompt are edited."""

    def __init__(self, store: TaskStore, session: dict[str, Any], parent=None) -> None:
        super().__init__(parent)
        self.store = store
        self.session = session
        self.session_id = str(session.get("id") or "").strip()
        self._run_time = default_run_time()
        self.scheduled_task: dict[str, Any] | None = None

        self.setWindowTitle("Schedule Codex task")
        self.setModal(True)
        self.resize(460, 280)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        title = QLabel(session_title(session), self)
        font = title.font()
        font.setBold(True)
        title.setFont(font)
        title.setToolTip(self._session_tooltip())
        root.addWidget(title)

        time_row = QHBoxLayout()
        time_row.addWidget(QLabel("Run at", self))
        self.when = QPushButton(self)
        self.when.clicked.connect(self.choose_time)
        time_row.addWidget(self.when, 1)
        root.addLayout(time_row)

        self.prompt = QTextEdit(self)
        self.prompt.setPlaceholderText("What should Codex do?")
        self.prompt.setMinimumHeight(130)
        root.addWidget(self.prompt, 1)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        ok = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok.setText("Schedule")
        self.buttons.accepted.connect(self.schedule_now)
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)

        self._refresh_when()
        self.prompt.setFocus()

    def _session_tooltip(self) -> str:
        bits = [self.session_id]
        cwd = str(self.session.get("cwd") or "").strip()
        if cwd:
            bits.append(cwd)
        return "\n".join(bits)

    def choose_time(self) -> None:
        dialog = ScheduleTimeDialog(self._run_time, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._run_time = dialog.selected_date_time()
        self._refresh_when()

    def _refresh_when(self) -> None:
        self.when.setText(self._run_time.toString("dd.MM.yyyy  HH:mm"))

    def schedule_now(self) -> None:
        prompt = self.prompt.toPlainText().strip()
        if not prompt:
            QMessageBox.warning(self, APP_NAME, "Enter what Codex should do.")
            return
        try:
            self.scheduled_task = schedule_quick_task(
                self.store,
                session_id=self.session_id,
                prompt=prompt,
                run_time=self._run_time,
            )
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, str(exc))
            return
        self.accept()


class TrayWorkflow:
    """Dynamic tray menu for scheduling and opening tasks without showing the main window."""

    def __init__(self, window) -> None:
        self.window = window
        self.menu = window.tray.contextMenu() or QMenu(window)
        window.tray.setContextMenu(self.menu)
        self.menu.aboutToShow.connect(self.rebuild)
        self.rebuild()

    def rebuild(self) -> None:
        self.menu.clear()

        show_action = self.menu.addAction("Open main window")
        show_action.triggered.connect(self.window.restore)
        self.menu.addSeparator()

        sessions_menu = self.menu.addMenu("Schedule for session")
        sessions = list(self.window._session_choices)
        names: dict[str, int] = {}
        for session in sessions:
            title = session_title(session)
            names[title] = names.get(title, 0) + 1
        duplicate_names = {name for name, count in names.items() if count > 1}
        if not sessions:
            empty = sessions_menu.addAction("No Codex sessions loaded")
            empty.setEnabled(False)
        else:
            for session in sessions[:30]:
                session_id = str(session.get("id") or "").strip()
                if not session_id:
                    continue
                action = sessions_menu.addAction(session_menu_label(session, duplicate_names))
                tooltip = session_id
                cwd = str(session.get("cwd") or "").strip()
                if cwd:
                    tooltip += f"\n{cwd}"
                action.setToolTip(tooltip)
                action.triggered.connect(
                    lambda _checked=False, selected=dict(session): self.open_quick_schedule(selected)
                )
        sessions_menu.addSeparator()
        refresh = sessions_menu.addAction("↻ Refresh sessions")
        refresh.triggered.connect(self.window.refresh_codex_sessions)

        active = [
            task for task in self.window.store.list()
            if task.get("status") in ACTIVE_STATUSES and not self.window.store.is_empty_draft(task)
        ]
        active_menu = self.menu.addMenu(f"Active tasks ({len(active)})")
        if not active:
            empty = active_menu.addAction("No active tasks")
            empty.setEnabled(False)
        else:
            for task in active:
                task_id = str(task["id"])
                action = active_menu.addAction(active_task_menu_label(task))
                action.setToolTip(self.window.tab_tooltip(task))
                action.triggered.connect(
                    lambda _checked=False, tid=task_id: self.open_task_in_main_window(tid)
                )

        self.menu.addSeparator()
        quit_action = self.menu.addAction("Quit")
        quit_action.triggered.connect(self.window.quit_app)

    def open_quick_schedule(self, session: dict[str, Any]) -> None:
        dialog = QuickScheduleDialog(self.window.store, session, self.window)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.scheduled_task is None:
            return
        task = dialog.scheduled_task
        self.window.refresh_all()
        when = str(task.get("scheduled") or "").replace("T", " ")[:16]
        self.window.tray.showMessage(
            APP_NAME,
            f"Scheduled: {task_display_title(task, 48)}\n{when}",
        )

    def open_task_in_main_window(self, task_id: str) -> None:
        self.window.restore()
        self.window.open_task(task_id, make_current=True)
        self.window.refresh_all()
