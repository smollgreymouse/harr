#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

try:
    from PyQt6.QtCore import QDateTime, QEvent, Qt, QTime, QTimer
    from PyQt6.QtGui import QAction, QCloseEvent, QIcon, QPalette
    from PyQt6.QtWidgets import (
        QApplication,
        QCalendarWidget,
        QCheckBox,
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QFileDialog,
        QFrame,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMenu,
        QMessageBox,
        QPushButton,
        QScrollArea,
        QSizePolicy,
        QSystemTrayIcon,
        QTextEdit,
        QTimeEdit,
        QToolButton,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:
    raise SystemExit("PyQt6 is required. On Ubuntu 24.04: sudo apt install python3-pyqt6") from exc

from core import TranscriptEvent, parse_codex_json_line
from session_cwd import SessionResolutionError, resolve_session_cwd
from system_theme import install_system_theme

APP_NAME = "Harr Codex Scheduler"
MODELS = {"Sol": "gpt-5.6-sol", "Terra": "gpt-5.6-terra", "Luna": "gpt-5.6-luna"}
REASONING = {"Minimal": "minimal", "Low": "low", "Medium": "medium", "High": "high", "Extra High": "xhigh"}
SPEEDS = {"Standard": "standard", "Fast": "fast"}
TIME_FORMAT = "yyyy-MM-dd HH:mm"


def state_dir() -> Path:
    base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
    path = base / "harr-codex-scheduler"
    path.mkdir(parents=True, exist_ok=True)
    return path


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


class ScheduleTimeDialog(QDialog):
    def __init__(self, initial: QDateTime, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Choose run time")
        self.setModal(True)

        layout = QVBoxLayout(self)
        self.calendar = QCalendarWidget(self)
        self.calendar.setMinimumDate(QDateTime.currentDateTime().date())
        self.calendar.setSelectedDate(initial.date())
        layout.addWidget(self.calendar)

        time_row = QHBoxLayout()
        time_row.addWidget(QLabel("Time"))
        self.time = QTimeEdit(self)
        self.time.setDisplayFormat("HH:mm")
        self.time.setTime(initial.time())
        time_row.addWidget(self.time, 1)
        layout.addLayout(time_row)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def selected_date_time(self) -> QDateTime:
        return QDateTime(self.calendar.selectedDate(), self.time.time())

    def accept(self) -> None:
        selected = self.selected_date_time()
        if not selected.isValid():
            QMessageBox.warning(self, APP_NAME, "Selected date/time is invalid.")
            return
        if selected <= QDateTime.currentDateTime():
            QMessageBox.warning(self, APP_NAME, "Run time must be in the future.")
            return
        super().accept()


class MessageBubble(QFrame):
    def __init__(self, role: str, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
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


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(920, 760)
        self._quitting = False
        self._log_path: Path | None = None
        self._log_offset = 0
        self._partial = ""
        self._assistant_bubble: MessageBubble | None = None
        self._resolved_cwd: Path | None = None
        self._scheduled_time: QDateTime | None = None

        root = QWidget()
        outer = QVBoxLayout(root)

        selectors = QHBoxLayout()
        self.model = QComboBox(); self.model.addItems(MODELS.keys()); self.model.setCurrentText("Terra"); self.model.setToolTip("Model")
        self.reasoning = QComboBox(); self.reasoning.addItems(REASONING.keys()); self.reasoning.setCurrentText("High"); self.reasoning.setToolTip("Reasoning")
        self.speed = QComboBox(); self.speed.addItems(SPEEDS.keys()); self.speed.setCurrentText("Standard"); self.speed.setToolTip("Speed")
        selectors.addWidget(self.model)
        selectors.addWidget(self.reasoning)
        selectors.addWidget(self.speed)
        outer.addLayout(selectors)

        session_row = QHBoxLayout()
        self.session = QLineEdit(); self.session.setPlaceholderText("Session ID")
        self.session.textChanged.connect(self.invalidate_cwd_preview)
        self.session.editingFinished.connect(self.resolve_cwd_preview)
        self.when = QLineEdit(); self.when.setReadOnly(True); self.when.setPlaceholderText("Run at")
        self.when.setToolTip("Click to choose date and time")
        self.when.setCursor(Qt.CursorShape.PointingHandCursor)
        self.when.installEventFilter(self)
        calendar_action = self.when.addAction(QIcon.fromTheme("x-office-calendar"), QLineEdit.ActionPosition.TrailingPosition)
        calendar_action.triggered.connect(self.choose_run_time)
        session_row.addWidget(self.session, 3)
        session_row.addWidget(self.when, 2)

        self.project_menu = QMenu(self)
        self.project_path_action = QAction("Project: not resolved", self); self.project_path_action.setEnabled(False)
        self.copy_project_action = QAction("Copy project directory", self); self.copy_project_action.setEnabled(False)
        self.copy_project_action.triggered.connect(self.copy_project_directory)
        self.refresh_project_action = QAction("Refresh project directory", self); self.refresh_project_action.triggered.connect(self.resolve_cwd_preview)
        self.project_menu.addAction(self.project_path_action)
        self.project_menu.addSeparator()
        self.project_menu.addAction(self.copy_project_action)
        self.project_menu.addAction(self.refresh_project_action)
        self.project_button = QToolButton(); self.project_button.setText("⋮")
        self.project_button.setToolTip("Session project")
        self.project_button.setMenu(self.project_menu)
        self.project_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        session_row.addWidget(self.project_button)
        outer.addLayout(session_row)

        self.prompt = QTextEdit(); self.prompt.setPlaceholderText("Prompt"); self.prompt.setMinimumHeight(110)
        outer.addWidget(self.prompt)

        save_row = QWidget(); save_layout = QHBoxLayout(save_row); save_layout.setContentsMargins(0, 0, 0, 0)
        self.save = QCheckBox("Save final answer")
        self.save_path = QLineEdit(); self.save_path.setPlaceholderText("Output file"); self.save_path.setEnabled(False)
        save_button = QPushButton("Browse…"); save_button.setEnabled(False)
        self.save.toggled.connect(self.save_path.setEnabled); self.save.toggled.connect(save_button.setEnabled)
        save_button.clicked.connect(self.choose_save)
        save_layout.addWidget(self.save); save_layout.addWidget(self.save_path); save_layout.addWidget(save_button)
        outer.addWidget(save_row)

        controls = QHBoxLayout()
        self.schedule_button = QPushButton("Schedule"); self.schedule_button.clicked.connect(self.schedule)
        self.status = QLabel("Ready")
        controls.addWidget(self.schedule_button); controls.addWidget(self.status, 1)
        outer.addLayout(controls)

        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True)
        transcript = QWidget(); self.transcript_layout = QVBoxLayout(transcript); self.transcript_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(transcript); outer.addWidget(self.scroll, 1)
        self.setCentralWidget(root)

        self.poll_timer = QTimer(self); self.poll_timer.setInterval(500); self.poll_timer.timeout.connect(self.poll_log); self.poll_timer.start()
        self.setup_tray()

    def setup_tray(self) -> None:
        icon = QIcon.fromTheme("utilities-terminal")
        self.tray = QSystemTrayIcon(icon, self); self.tray.setToolTip(APP_NAME)
        menu = self.tray.contextMenu()
        if menu is None:
            menu = QMenu(self); self.tray.setContextMenu(menu)
        show_action = QAction("Show", self); show_action.triggered.connect(self.restore)
        quit_action = QAction("Quit", self); quit_action.triggered.connect(self.quit_app)
        menu.addAction(show_action); menu.addSeparator(); menu.addAction(quit_action)
        self.tray.activated.connect(lambda reason: self.restore() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        if QSystemTrayIcon.isSystemTrayAvailable(): self.tray.show()

    def eventFilter(self, watched: object, event: QEvent) -> bool:
        if watched is self.when and event.type() == QEvent.Type.MouseButtonPress:
            self.choose_run_time()
            return True
        return super().eventFilter(watched, event)

    def choose_run_time(self) -> None:
        initial = self._scheduled_time
        if initial is None or initial <= QDateTime.currentDateTime():
            initial = QDateTime.currentDateTime().addSecs(5 * 60)
            initial.setTime(QTime(initial.time().hour(), initial.time().minute()))
        dialog = ScheduleTimeDialog(initial, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.set_scheduled_time(dialog.selected_date_time())

    def set_scheduled_time(self, scheduled: QDateTime) -> None:
        if not scheduled.isValid():
            raise ValueError("invalid schedule time")
        if scheduled <= QDateTime.currentDateTime():
            raise ValueError("schedule time must be in the future")
        self._scheduled_time = scheduled
        self.when.setText(scheduled.toString(TIME_FORMAT))

    def invalidate_cwd_preview(self) -> None:
        self._resolved_cwd = None
        self.project_path_action.setText("Project: not resolved")
        self.copy_project_action.setEnabled(False)
        self.project_button.setToolTip("Session project")

    def set_resolved_cwd(self, cwd: Path) -> None:
        self._resolved_cwd = cwd
        self.project_path_action.setText(f"Project: {cwd}")
        self.copy_project_action.setEnabled(True)
        self.project_button.setToolTip(str(cwd))

    def resolve_cwd_preview(self) -> None:
        session = self.session.text().strip()
        if not session:
            self.invalidate_cwd_preview()
            return
        try:
            cwd = resolve_session_cwd(session)
        except SessionResolutionError as exc:
            self.invalidate_cwd_preview()
            self.status.setText(str(exc)[:220])
            return
        self.set_resolved_cwd(cwd)
        self.status.setText("Session directory verified")

    def copy_project_directory(self) -> None:
        if self._resolved_cwd is not None:
            QApplication.clipboard().setText(str(self._resolved_cwd))
            self.status.setText("Project directory copied")

    def default_answer_path(self) -> Path:
        session_part = safe_filename_part(self.session.text(), "session")
        scheduled = self._scheduled_time or QDateTime.currentDateTime()
        time_part = scheduled.toString("yyyyMMdd-HHmm")
        directory = self._resolved_cwd if self._resolved_cwd is not None else Path.cwd()
        return unique_path(directory / f"codex-{session_part}-{time_part}.md")

    def choose_save(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Codex answer",
            str(self.default_answer_path()),
            "Markdown (*.md);;Text (*.txt);;All files (*)",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if path:
            self.save_path.setText(path)

    def add_bubble(self, role: str, text: str) -> MessageBubble:
        bubble = MessageBubble(role, text); self.transcript_layout.addWidget(bubble)
        QTimer.singleShot(0, lambda: self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum()))
        return bubble

    def schedule(self) -> None:
        session = self.session.text().strip(); prompt = self.prompt.toPlainText().strip()
        if not session or not prompt:
            QMessageBox.warning(self, APP_NAME, "Session ID and prompt are required."); return
        scheduled = self._scheduled_time
        if scheduled is None:
            QMessageBox.warning(self, APP_NAME, "Choose a run time first."); return
        try:
            cwd = resolve_session_cwd(session)
        except SessionResolutionError as exc:
            QMessageBox.critical(self, APP_NAME, f"Cannot safely resolve the session working directory:\n{exc}"); return
        self.set_resolved_cwd(cwd)
        answer_path = Path(self.save_path.text()).expanduser() if self.save.isChecked() and self.save_path.text().strip() else None
        if self.save.isChecked() and answer_path is None:
            QMessageBox.warning(self, APP_NAME, "Choose a file for the saved answer."); return

        job_id = uuid.uuid4().hex
        jobs = state_dir() / "jobs"; jobs.mkdir(parents=True, exist_ok=True)
        log_path = jobs / f"{job_id}.jsonl"; metadata_path = jobs / f"{job_id}.json"
        scheduler = Path(__file__).resolve().parents[1] / "bin" / "codex-schedule"
        timestamp = scheduled.toString("yyyyMMddHHmm")
        args = [str(scheduler), "--model", MODELS[self.model.currentText()], "--reasoning", REASONING[self.reasoning.currentText()], "--speed", SPEEDS[self.speed.currentText()], "--timestamp", timestamp, "--session", session, "--prompt", prompt, "--log-json", str(log_path)]
        if answer_path: args += ["--save-answer", str(answer_path)]
        proc = subprocess.run(args, text=True, capture_output=True); combined = (proc.stdout + proc.stderr).strip()
        if proc.returncode != 0:
            QMessageBox.critical(self, APP_NAME, combined or f"Scheduler failed with exit code {proc.returncode}"); return
        match = re.search(r"\bjob\s+(\d+)\b", combined)
        metadata = {"id": job_id, "at_job": match.group(1) if match else None, "scheduled": scheduled.toString(Qt.DateFormat.ISODate), "session": session, "model": MODELS[self.model.currentText()], "reasoning": REASONING[self.reasoning.currentText()], "speed": SPEEDS[self.speed.currentText()], "cwd": str(cwd), "prompt": prompt, "log": str(log_path), "answer": str(answer_path) if answer_path else None}
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        self._log_path = log_path; self._log_offset = 0; self._partial = ""; self._assistant_bubble = None
        self.add_bubble("user", prompt); self.status.setText(combined or "Scheduled")

    def poll_log(self) -> None:
        if not self._log_path or not self._log_path.exists(): return
        try:
            with self._log_path.open("r", encoding="utf-8", errors="replace") as fh:
                fh.seek(self._log_offset); chunk = fh.read(); self._log_offset = fh.tell()
        except OSError:
            return
        if not chunk: return
        data = self._partial + chunk; lines = data.splitlines(keepends=True); self._partial = ""
        if lines and not lines[-1].endswith(("\n", "\r")): self._partial = lines.pop()
        for line in lines:
            for event in parse_codex_json_line(line): self.handle_event(event)

    def handle_event(self, event: TranscriptEvent) -> None:
        if event.kind == "assistant":
            if self._assistant_bubble is None: self._assistant_bubble = self.add_bubble("assistant", event.text)
            else: self._assistant_bubble.append_text(event.text)
        elif event.kind == "error": self.status.setText("Error: " + event.text)
        elif event.kind == "done": self.status.setText("Completed")
        elif event.kind == "status" and event.text: self.status.setText(event.text[:220])

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange and self.isMinimized() and QSystemTrayIcon.isSystemTrayAvailable(): QTimer.singleShot(0, self.hide)

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._quitting and QSystemTrayIcon.isSystemTrayAvailable(): self.hide(); event.ignore(); return
        event.accept()

    def restore(self) -> None:
        self.showNormal(); self.show(); self.raise_(); self.activateWindow()

    def quit_app(self) -> None:
        self._quitting = True; self.tray.hide(); QApplication.instance().quit()


def main() -> int:
    app = QApplication(sys.argv); app.setApplicationName(APP_NAME); app.setQuitOnLastWindowClosed(False)
    # Keep the watcher alive for the lifetime of QApplication so GNOME/Qt
    # theme changes are reflected without restarting the scheduler.
    app._harr_system_theme = install_system_theme(app)  # type: ignore[attr-defined]
    window = MainWindow(); window.show(); return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
