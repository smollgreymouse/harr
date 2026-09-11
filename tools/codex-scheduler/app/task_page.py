#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any, Callable

from PyQt6.QtCore import QDateTime, QEvent, QLocale, Qt, QTime, QTimer
from PyQt6.QtGui import QAction, QIcon, QPalette
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCalendarWidget,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core import TranscriptEvent, parse_codex_json_line
from session_cwd import SessionResolutionError, resolve_session_cwd
from task_store import TaskStore

APP_NAME = "Harr Codex Scheduler"
MODELS = {"Sol": "gpt-5.6-sol", "Terra": "gpt-5.6-terra", "Luna": "gpt-5.6-luna"}
REASONING = {"Minimal": "minimal", "Low": "low", "Medium": "medium", "High": "high", "Extra High": "xhigh"}
SPEEDS = {"Standard": "standard", "Fast": "fast"}
TIME_FORMAT = "yyyy-MM-dd HH:mm"
RESET_OFFSET_SECONDS = 5 * 60 * 60 + 2 * 60
STATUS_TEXT = {
    "draft": "Draft",
    "scheduled": "Scheduled",
    "running": "Running",
    "cancelling": "Cancelling…",
    "completed": "Completed",
    "failed": "Failed",
    "cancelled": "Cancelled",
}
STATUS_ICON = {
    "draft": "○",
    "scheduled": "◷",
    "running": "●",
    "cancelling": "…",
    "completed": "✓",
    "failed": "!",
    "cancelled": "×",
}


def safe_filename_part(value: str, fallback: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-._")
    return value or fallback


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    index = 2
    while True:
        candidate = path.with_name(f"{stem}-{index}{suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def default_run_time() -> QDateTime:
    target = QDateTime.currentDateTime().addSecs(RESET_OFFSET_SECONDS)
    seconds = target.time().second()
    if seconds or target.time().msec():
        target = target.addSecs(60 - seconds)
    target.setTime(QTime(target.time().hour(), target.time().minute()))
    return target


def task_display_title(task: dict, limit: int = 42) -> str:
    prompt = " ".join(str(task.get("prompt") or "").split())
    if prompt:
        return prompt if len(prompt) <= limit else prompt[: limit - 1] + "…"
    session = str(task.get("session") or "").strip()
    if session:
        short = session if len(session) <= 18 else session[:8] + "…" + session[-6:]
        return short
    return "New task"


def task_status_text(task: dict) -> str:
    status = str(task.get("status") or "draft")
    return f"{STATUS_ICON.get(status, '•')} {STATUS_TEXT.get(status, status.title())}"


class SessionComboBox(QComboBox):
    """Editable recent-session picker; pasted IDs remain valid input."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.setMaxVisibleItems(18)
        assert self.lineEdit() is not None
        self.lineEdit().setPlaceholderText("Session ID")
        self.activated.connect(self._session_activated)

    def _session_activated(self, index: int) -> None:
        session_id = self.itemData(index, Qt.ItemDataRole.UserRole)
        if isinstance(session_id, str) and session_id:
            self.setEditText(session_id)
            assert self.lineEdit() is not None
            self.lineEdit().setCursorPosition(len(session_id))

    def session_id(self) -> str:
        return self.currentText().strip()

    def set_session_id(self, value: str) -> None:
        self.setCurrentIndex(-1)
        self.setEditText(value)

    def set_sessions(self, sessions: list[dict[str, Any]], *, select_latest_if_empty: bool = False) -> None:
        current = self.session_id()
        self.blockSignals(True)
        self.clear()
        for session in sessions:
            session_id = str(session.get("id") or "").strip()
            if not session_id:
                continue
            preview = str(session.get("name") or session.get("preview") or "Codex session")
            preview = " ".join(preview.split())
            if len(preview) > 42:
                preview = preview[:41] + "…"
            cwd = str(session.get("cwd") or "")
            project = Path(cwd).name if cwd else ""
            short_id = session_id[:8] + "…" + session_id[-5:] if len(session_id) > 16 else session_id
            label = " · ".join(part for part in (preview, project, short_id) if part)
            self.addItem(label, session_id)
            index = self.count() - 1
            tooltip = session_id
            if cwd:
                tooltip += f"\n{cwd}"
            if preview:
                tooltip += f"\n{preview}"
            self.setItemData(index, tooltip, Qt.ItemDataRole.ToolTipRole)
        self.setCurrentIndex(-1)
        target = current
        if not target and select_latest_if_empty and self.count():
            candidate = self.itemData(0, Qt.ItemDataRole.UserRole)
            if isinstance(candidate, str):
                target = candidate
        self.setEditText(target)
        self.blockSignals(False)
        if target != current:
            self.editTextChanged.emit(target)


class ScheduleTimeDialog(QDialog):
    """Click-first time picker optimized for the Codex five-hour reset window."""

    def __init__(self, initial: QDateTime, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Choose run time")
        self.setModal(True)
        self._selected = QDateTime(initial if initial.isValid() else default_run_time())
        self._hour_buttons: dict[int, QPushButton] = {}
        self._minute_buttons: dict[int, QPushButton] = {}

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        self.summary = QLabel()
        self.summary.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.summary.setStyleSheet("font-size: 18px; font-weight: 600; padding: 4px;")
        layout.addWidget(self.summary)

        quick = QHBoxLayout()
        reset = QPushButton("Now + 5:02")
        reset.setToolTip("Default Codex reset window")
        reset.clicked.connect(lambda: self.set_selected(default_run_time()))
        today = QPushButton("Today")
        today.clicked.connect(lambda: self.set_date(QDateTime.currentDateTime().date()))
        tomorrow = QPushButton("Tomorrow")
        tomorrow.clicked.connect(lambda: self.set_date(QDateTime.currentDateTime().date().addDays(1)))
        other = QPushButton("Other date…")
        other.clicked.connect(self.choose_other_date)
        quick.addWidget(reset)
        quick.addStretch(1)
        quick.addWidget(today)
        quick.addWidget(tomorrow)
        quick.addWidget(other)
        layout.addLayout(quick)

        layout.addWidget(QLabel("Hour"))
        hour_grid = QGridLayout()
        hour_grid.setSpacing(4)
        self.hour_group = QButtonGroup(self)
        self.hour_group.setExclusive(True)
        for hour in range(24):
            button = QPushButton(f"{hour:02d}")
            button.setCheckable(True)
            button.setMinimumWidth(42)
            button.clicked.connect(lambda _checked=False, h=hour: self.set_hour(h))
            self.hour_group.addButton(button, hour)
            self._hour_buttons[hour] = button
            hour_grid.addWidget(button, hour // 8, hour % 8)
        layout.addLayout(hour_grid)

        minute_header = QHBoxLayout()
        minute_header.addWidget(QLabel("Minute"))
        minute_header.addStretch(1)
        minus = QPushButton("−1 min")
        plus = QPushButton("+1 min")
        minus.clicked.connect(lambda: self.shift_minutes(-1))
        plus.clicked.connect(lambda: self.shift_minutes(1))
        minute_header.addWidget(minus)
        minute_header.addWidget(plus)
        layout.addLayout(minute_header)

        minute_grid = QGridLayout()
        minute_grid.setSpacing(4)
        self.minute_group = QButtonGroup(self)
        self.minute_group.setExclusive(True)
        for position, minute in enumerate(range(0, 60, 5)):
            button = QPushButton(f"{minute:02d}")
            button.setCheckable(True)
            button.clicked.connect(lambda _checked=False, m=minute: self.set_minute(m))
            self.minute_group.addButton(button, minute)
            self._minute_buttons[minute] = button
            minute_grid.addWidget(button, position // 6, position % 6)
        layout.addLayout(minute_grid)

        self.validation = QLabel()
        self.validation.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.validation)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.ok_button = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._refresh()

    def selected_date_time(self) -> QDateTime:
        return QDateTime(self._selected)

    def set_selected(self, selected: QDateTime) -> None:
        self._selected = QDateTime(selected)
        self._refresh()

    def set_date(self, date) -> None:
        self._selected.setDate(date)
        self._refresh()

    def set_hour(self, hour: int) -> None:
        time = self._selected.time()
        self._selected.setTime(QTime(hour, time.minute()))
        self._refresh()

    def set_minute(self, minute: int) -> None:
        time = self._selected.time()
        self._selected.setTime(QTime(time.hour(), minute))
        self._refresh()

    def shift_minutes(self, delta: int) -> None:
        self._selected = self._selected.addSecs(delta * 60)
        self._refresh()

    def choose_other_date(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Choose date")
        box = QVBoxLayout(dialog)
        calendar = QCalendarWidget(dialog)
        calendar.setLocale(QLocale.system())
        calendar.setFirstDayOfWeek(Qt.DayOfWeek.Monday)
        calendar.setMinimumDate(QDateTime.currentDateTime().date())
        calendar.setSelectedDate(self._selected.date())
        box.addWidget(calendar)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        box.addWidget(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.set_date(calendar.selectedDate())

    def _refresh(self) -> None:
        self.summary.setText(self._selected.toString("dd.MM.yyyy   HH:mm"))
        hour = self._selected.time().hour()
        minute = self._selected.time().minute()
        for value, button in self._hour_buttons.items():
            button.setChecked(value == hour)
        for value, button in self._minute_buttons.items():
            button.setChecked(value == minute)
        valid = self._selected.isValid() and self._selected > QDateTime.currentDateTime()
        self.ok_button.setEnabled(valid)
        if valid:
            delta = max(0, QDateTime.currentDateTime().secsTo(self._selected))
            hours, remainder = divmod(delta, 3600)
            minutes = remainder // 60
            self.validation.setText(f"in {hours}h {minutes:02d}m")
        else:
            self.validation.setText("Choose a future time")

    def accept(self) -> None:
        if not self.ok_button.isEnabled():
            return
        super().accept()


class MessageBubble(QFrame):
    def __init__(self, role: str, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("messageBubble")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 9)
        title = QLabel("You" if role == "user" else "Codex")
        title.setStyleSheet("font-weight: 600;")
        body = QLabel(text)
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(title)
        layout.addWidget(body)
        self.body = body
        palette = self.palette()
        if role == "user":
            palette.setColor(QPalette.ColorRole.Window, palette.color(QPalette.ColorRole.Highlight))
            palette.setColor(QPalette.ColorRole.WindowText, palette.color(QPalette.ColorRole.HighlightedText))
        else:
            palette.setColor(QPalette.ColorRole.Window, palette.color(QPalette.ColorRole.AlternateBase))
            palette.setColor(QPalette.ColorRole.WindowText, palette.color(QPalette.ColorRole.Text))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

    def append_text(self, text: str) -> None:
        current = self.body.text()
        self.body.setText((current + "\n\n" + text).strip() if current else text)


class TaskPage(QWidget):
    def __init__(self, store: TaskStore, task: dict, on_changed: Callable[[str], None], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self.task_id = str(task["id"])
        self._on_changed = on_changed
        self._resolved_cwd: Path | None = Path(task["cwd"]) if task.get("cwd") else None
        self._scheduled_time: QDateTime | None = None
        self._answer_path: Path | None = Path(task["answer"]) if task.get("answer") else None
        self._log_path = Path(str(task["log"])) if task.get("log") else None
        self._log_offset = 0
        self._partial = ""
        self._assistant_bubble: MessageBubble | None = None
        self._last_status = str(task.get("status") or "draft")
        self._loading = True

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)

        top = QHBoxLayout()
        self.model = QComboBox(); self.model.addItems(MODELS.keys()); self.model.setToolTip("Model")
        self.reasoning = QComboBox(); self.reasoning.addItems(REASONING.keys()); self.reasoning.setToolTip("Reasoning")
        self.speed = QComboBox(); self.speed.addItems(SPEEDS.keys()); self.speed.setToolTip("Speed")
        self.status = QLabel(); self.status.setObjectName("taskStatus")
        top.addWidget(self.model); top.addWidget(self.reasoning); top.addWidget(self.speed); top.addStretch(1); top.addWidget(self.status)
        root.addLayout(top)

        session_row = QHBoxLayout()
        self.session = SessionComboBox()
        self.session.setToolTip("Recent Codex sessions; you can also paste any session ID")
        self.when = QLineEdit(); self.when.setReadOnly(True); self.when.setPlaceholderText("Run at")
        self.when.setToolTip("Click to choose date and time")
        self.when.setCursor(Qt.CursorShape.PointingHandCursor)
        self.when.installEventFilter(self)
        calendar_action = self.when.addAction(QIcon.fromTheme("appointment-new"), QLineEdit.ActionPosition.TrailingPosition)
        calendar_action.triggered.connect(self.choose_run_time)
        session_row.addWidget(self.session, 3); session_row.addWidget(self.when, 2)

        self.project_menu = QMenu(self)
        self.project_path_action = QAction("Project: not resolved", self); self.project_path_action.setEnabled(False)
        self.copy_project_action = QAction("Copy project directory", self); self.copy_project_action.setEnabled(False)
        self.copy_project_action.triggered.connect(self.copy_project_directory)
        self.refresh_project_action = QAction("Refresh project directory", self); self.refresh_project_action.triggered.connect(self.resolve_cwd_preview)
        self.project_menu.addAction(self.project_path_action); self.project_menu.addSeparator(); self.project_menu.addAction(self.copy_project_action); self.project_menu.addAction(self.refresh_project_action)
        self.project_button = QToolButton(); self.project_button.setText("⋮"); self.project_button.setToolTip("Session project")
        self.project_button.setMenu(self.project_menu); self.project_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        session_row.addWidget(self.project_button)
        root.addLayout(session_row)

        self.prompt = QTextEdit(); self.prompt.setPlaceholderText("What should Codex do?"); self.prompt.setMinimumHeight(100)
        root.addWidget(self.prompt)

        actions = QHBoxLayout()
        self.save_button = QPushButton("Save final answer…"); self.save_button.setCheckable(True); self.save_button.clicked.connect(self.toggle_save_answer)
        self.primary_button = QPushButton("Schedule"); self.primary_button.clicked.connect(self.primary_action)
        actions.addWidget(self.save_button); actions.addStretch(1); actions.addWidget(self.primary_button)
        root.addLayout(actions)

        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True)
        transcript = QWidget(); self.transcript_layout = QVBoxLayout(transcript); self.transcript_layout.setAlignment(Qt.AlignmentFlag.AlignTop); self.transcript_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll.setWidget(transcript); root.addWidget(self.scroll, 1)

        self._load_task(task)
        self._connect_draft_signals()
        self._loading = False
        self._rebuild_transcript(task)
        self._apply_status(task)

        self.poll_timer = QTimer(self); self.poll_timer.setInterval(600); self.poll_timer.timeout.connect(self.poll); self.poll_timer.start()

    def _load_task(self, task: dict) -> None:
        self.model.setCurrentText(next((key for key, value in MODELS.items() if value == task.get("model")), "Terra"))
        self.reasoning.setCurrentText(next((key for key, value in REASONING.items() if value == task.get("reasoning")), "High"))
        self.speed.setCurrentText(next((key for key, value in SPEEDS.items() if value == task.get("speed")), "Standard"))
        self.session.set_session_id(str(task.get("session") or ""))
        self.prompt.setPlainText(str(task.get("prompt") or ""))
        if task.get("scheduled"):
            parsed = QDateTime.fromString(str(task["scheduled"]), Qt.DateFormat.ISODate)
            if parsed.isValid():
                self._scheduled_time = parsed
                self.when.setText(parsed.toString(TIME_FORMAT))
        elif task.get("status") == "draft":
            self.set_scheduled_time(default_run_time(), persist=False)
        self.set_save_button_state(self._answer_path)
        if self._resolved_cwd is not None:
            self.set_resolved_cwd(self._resolved_cwd)

    def _connect_draft_signals(self) -> None:
        self.model.currentTextChanged.connect(self.persist_draft)
        self.reasoning.currentTextChanged.connect(self.persist_draft)
        self.speed.currentTextChanged.connect(self.persist_draft)
        self.session.editTextChanged.connect(self._session_changed)
        assert self.session.lineEdit() is not None
        self.session.lineEdit().editingFinished.connect(self.resolve_cwd_preview)
        self.session.activated.connect(lambda _index: QTimer.singleShot(0, self.resolve_cwd_preview))
        self.prompt.textChanged.connect(self.persist_draft)

    def set_session_choices(self, sessions: list[dict[str, Any]], *, select_latest_if_empty: bool = False) -> None:
        task = self.current_task()
        should_select = bool(select_latest_if_empty and task.get("status") == "draft" and not self.session.session_id())
        self.session.set_sessions(sessions, select_latest_if_empty=should_select)
        if should_select and self.session.session_id():
            self.persist_draft()
            QTimer.singleShot(0, self.resolve_cwd_preview)

    def _session_changed(self) -> None:
        self.invalidate_cwd_preview(); self.persist_draft()

    def current_task(self) -> dict:
        return self.store.load(self.task_id) or {"id": self.task_id, "status": "failed"}

    def persist_draft(self) -> None:
        if self._loading or self.current_task().get("status") != "draft":
            return
        self.store.patch(
            self.task_id,
            model=MODELS[self.model.currentText()], reasoning=REASONING[self.reasoning.currentText()], speed=SPEEDS[self.speed.currentText()],
            session=self.session.session_id(), prompt=self.prompt.toPlainText(),
            scheduled=self._scheduled_time.toString(Qt.DateFormat.ISODate) if self._scheduled_time else None,
            cwd=str(self._resolved_cwd) if self._resolved_cwd else None,
            answer=str(self._answer_path) if self._answer_path else None,
        )
        self._on_changed(self.task_id)

    def eventFilter(self, watched: object, event: QEvent) -> bool:
        if watched is self.when and event.type() == QEvent.Type.MouseButtonPress and self.current_task().get("status") == "draft":
            self.choose_run_time(); return True
        return super().eventFilter(watched, event)

    def choose_run_time(self) -> None:
        initial = self._scheduled_time
        if initial is None or initial <= QDateTime.currentDateTime():
            initial = default_run_time()
        dialog = ScheduleTimeDialog(initial, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.set_scheduled_time(dialog.selected_date_time())

    def set_scheduled_time(self, scheduled: QDateTime, *, persist: bool = True) -> None:
        if not scheduled.isValid():
            raise ValueError("invalid schedule time")
        if scheduled <= QDateTime.currentDateTime():
            raise ValueError("schedule time must be in the future")
        self._scheduled_time = scheduled
        self.when.setText(scheduled.toString(TIME_FORMAT))
        if persist:
            self.persist_draft()

    def invalidate_cwd_preview(self) -> None:
        self._resolved_cwd = None; self.project_path_action.setText("Project: not resolved"); self.copy_project_action.setEnabled(False); self.project_button.setToolTip("Session project")

    def set_resolved_cwd(self, cwd: Path) -> None:
        self._resolved_cwd = cwd; self.project_path_action.setText(f"Project: {cwd}"); self.copy_project_action.setEnabled(True); self.project_button.setToolTip(str(cwd))

    def resolve_cwd_preview(self) -> None:
        if self.current_task().get("status") != "draft":
            return
        session = self.session.session_id()
        if not session:
            self.invalidate_cwd_preview(); return
        try:
            cwd = resolve_session_cwd(session)
        except SessionResolutionError as exc:
            self.invalidate_cwd_preview(); self.status.setText(str(exc)[:180]); return
        self.set_resolved_cwd(cwd); self.persist_draft(); self.status.setText("✓ Project verified")

    def copy_project_directory(self) -> None:
        if self._resolved_cwd is not None:
            QApplication.clipboard().setText(str(self._resolved_cwd))

    def default_answer_path(self) -> Path:
        session_part = safe_filename_part(self.session.session_id(), "session")
        scheduled = self._scheduled_time or QDateTime.currentDateTime()
        time_part = scheduled.toString("yyyyMMdd-HHmm")
        directory = self._resolved_cwd if self._resolved_cwd is not None else Path.cwd()
        return unique_path(directory / f"codex-{session_part}-{time_part}.md")

    def set_save_button_state(self, path: Path | None) -> None:
        self._answer_path = path
        self.save_button.blockSignals(True); self.save_button.setChecked(path is not None); self.save_button.blockSignals(False)
        if path is None:
            self.save_button.setText("Save final answer…"); self.save_button.setToolTip("Enable saving and choose the output file")
        else:
            self.save_button.setText(f"✓ {path.name}"); self.save_button.setToolTip(str(path))

    def toggle_save_answer(self, checked: bool) -> None:
        if self.current_task().get("status") != "draft":
            self.save_button.setChecked(self._answer_path is not None); return
        if not checked:
            self.set_save_button_state(None); self.persist_draft(); return
        path, _ = QFileDialog.getSaveFileName(self, "Save Codex answer", str(self.default_answer_path()), "Markdown (*.md);;Text (*.txt);;All files (*)", options=QFileDialog.Option.DontUseNativeDialog)
        if not path:
            self.set_save_button_state(None); return
        self.set_save_button_state(Path(path).expanduser()); self.persist_draft()

    def primary_action(self) -> None:
        status = str(self.current_task().get("status") or "draft")
        if status == "draft": self.schedule()
        elif status in {"scheduled", "running", "cancelling"}: self.cancel_task()

    def schedule(self) -> None:
        session = self.session.session_id(); prompt = self.prompt.toPlainText().strip()
        if not session or not prompt:
            QMessageBox.warning(self, APP_NAME, "Session ID and prompt are required."); return
        if self._scheduled_time is None:
            QMessageBox.warning(self, APP_NAME, "Choose a run time first."); return
        try:
            cwd = resolve_session_cwd(session)
        except SessionResolutionError as exc:
            QMessageBox.critical(self, APP_NAME, f"Cannot safely resolve the session working directory:\n{exc}"); return
        self.set_resolved_cwd(cwd)
        task_path = self.store.task_path(self.task_id)
        log_path = Path(str(self.current_task().get("log") or self.store.jobs_dir / f"{self.task_id}.jsonl"))
        scheduler = Path(__file__).resolve().parents[1] / "bin" / "codex-schedule"
        timestamp = self._scheduled_time.toString("yyyyMMddHHmm")
        args = [str(scheduler), "--model", MODELS[self.model.currentText()], "--reasoning", REASONING[self.reasoning.currentText()], "--speed", SPEEDS[self.speed.currentText()], "--timestamp", timestamp, "--session", session, "--prompt", prompt, "--log-json", str(log_path), "--task-state", str(task_path)]
        if self._answer_path: args += ["--save-answer", str(self._answer_path)]
        proc = subprocess.run(args, text=True, capture_output=True); combined = (proc.stdout + proc.stderr).strip()
        if proc.returncode != 0:
            QMessageBox.critical(self, APP_NAME, combined or f"Scheduler failed with exit code {proc.returncode}"); return
        match = re.search(r"\bjob\s+(\d+)\b", combined)
        task = self.store.patch(self.task_id, status="scheduled", at_job=match.group(1) if match else None, model=MODELS[self.model.currentText()], reasoning=REASONING[self.reasoning.currentText()], speed=SPEEDS[self.speed.currentText()], session=session, prompt=prompt, scheduled=self._scheduled_time.toString(Qt.DateFormat.ISODate), cwd=str(cwd), log=str(log_path), answer=str(self._answer_path) if self._answer_path else None, cancel_requested=False, error=None)
        self._log_path = log_path; self._log_offset = 0; self._partial = ""; self._rebuild_transcript(task); self._apply_status(task); self._on_changed(self.task_id)

    def cancel_task(self) -> None:
        task = self.current_task()
        if task.get("status") not in {"scheduled", "running", "cancelling"}: return
        if QMessageBox.question(self, APP_NAME, "Cancel this Codex task?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes: return
        try:
            task = self.store.cancel(self.task_id)
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, str(exc)); return
        self._apply_status(task); self._on_changed(self.task_id)

    def add_bubble(self, role: str, text: str) -> MessageBubble:
        bubble = MessageBubble(role, text); self.transcript_layout.addWidget(bubble); QTimer.singleShot(0, lambda: self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum())); return bubble

    def _clear_transcript(self) -> None:
        while self.transcript_layout.count():
            item = self.transcript_layout.takeAt(0); widget = item.widget()
            if widget is not None: widget.deleteLater()
        self._assistant_bubble = None

    def _rebuild_transcript(self, task: dict) -> None:
        self._clear_transcript(); self._log_offset = 0; self._partial = ""
        prompt = str(task.get("prompt") or "").strip()
        if task.get("status") != "draft" and prompt: self.add_bubble("user", prompt)
        log_path = Path(str(task.get("log"))) if task.get("log") else None; self._log_path = log_path
        if log_path is None or not log_path.exists(): return
        try:
            with log_path.open("r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    for event in parse_codex_json_line(line): self.handle_event(event)
                self._log_offset = fh.tell()
        except OSError: pass

    def poll(self) -> None:
        task = self.current_task(); status = str(task.get("status") or "draft")
        if status != self._last_status: self._apply_status(task); self._on_changed(self.task_id)
        self.poll_log()

    def poll_log(self) -> None:
        if not self._log_path or not self._log_path.exists(): return
        try:
            with self._log_path.open("r", encoding="utf-8", errors="replace") as fh:
                fh.seek(self._log_offset); chunk = fh.read(); self._log_offset = fh.tell()
        except OSError: return
        if not chunk: return
        data = self._partial + chunk; lines = data.splitlines(keepends=True); self._partial = ""
        if lines and not lines[-1].endswith(("\n", "\r")): self._partial = lines.pop()
        for line in lines:
            for event in parse_codex_json_line(line): self.handle_event(event)

    def handle_event(self, event: TranscriptEvent) -> None:
        if event.kind == "assistant":
            if self._assistant_bubble is None: self._assistant_bubble = self.add_bubble("assistant", event.text)
            else: self._assistant_bubble.append_text(event.text)
        elif event.kind == "error": self.status.setText("! " + event.text[:160])
        elif event.kind == "done": self.status.setText("✓ Completed")
        elif event.kind == "status" and event.text: self.status.setText(event.text[:160])

    def _apply_status(self, task: dict) -> None:
        status = str(task.get("status") or "draft"); self._last_status = status; self.status.setText(task_status_text(task)); editable = status == "draft"
        for widget in (self.model, self.reasoning, self.speed, self.session, self.prompt, self.when, self.save_button): widget.setEnabled(editable)
        self.project_button.setEnabled(True)
        if status == "draft": self.primary_button.setText("Schedule"); self.primary_button.setEnabled(True)
        elif status in {"scheduled", "running"}: self.primary_button.setText("Cancel task"); self.primary_button.setEnabled(True)
        elif status == "cancelling": self.primary_button.setText("Cancelling…"); self.primary_button.setEnabled(False)
        else: self.primary_button.setText(STATUS_TEXT.get(status, status.title())); self.primary_button.setEnabled(False)

    def refresh_from_store(self) -> None:
        task = self.current_task(); self._apply_status(task); self._on_changed(self.task_id)

    def is_empty_draft(self) -> bool:
        return TaskStore.is_empty_draft(self.current_task())
