#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["HARR_CODEX_THEME"] = "dark"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from PyQt6.QtCore import QDateTime
from PyQt6.QtGui import QPalette
from PyQt6.QtWidgets import QApplication, QCalendarWidget
import main as main_module
import task_page as task_page_module
from main import MainWindow
from system_theme import install_system_theme
from task_page import ScheduleTimeDialog, TaskPage, default_run_time
from task_store import TaskStore


def main() -> int:
    app = QApplication.instance() or QApplication([])
    watcher = install_system_theme(app)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        project = root / "project"
        project.mkdir()
        sessions = [
            {"id": "session-newest", "name": "Newest task", "preview": "Newest preview", "cwd": str(project), "updatedAt": 300},
            {"id": "session-older", "name": None, "preview": "Older task", "cwd": str(project), "updatedAt": 200},
        ]
        main_module.list_codex_sessions = lambda **_kwargs: sessions
        task_page_module.resolve_session_cwd = lambda _session: project

        store = TaskStore(root / "state")
        window = MainWindow(store)
        window.refresh_codex_sessions()
        assert window.tabs.count() == 1
        assert window.new_button.text().endswith("New task")
        assert window.search.placeholderText() == "Search tasks"

        page = window.tabs.widget(0)
        assert isinstance(page, TaskPage)
        assert page.model.currentText() == "Terra"
        assert page.reasoning.currentText() == "High"
        assert page.speed.currentText() == "Standard"
        assert page.session.isEditable()
        assert page.session.session_id() == "session-newest"
        assert page.session.count() == 2
        assert page.when.isReadOnly()
        assert page.when.text()
        assert page.prompt.placeholderText() == "What should Codex do?"
        assert page.project_button.text() == "⋮"
        assert page.save_button.isCheckable()
        assert page.save_button.text() == "Save final answer…"

        # Default schedule is the Codex reset window: now + 05:02, rounded
        # up to a whole minute because at -t is minute-granular.
        assert page._scheduled_time is not None
        delta = QDateTime.currentDateTime().secsTo(page._scheduled_time)
        assert 5 * 3600 + 60 <= delta <= 5 * 3600 + 3 * 60, delta

        # The picker itself is click-first: no always-visible full calendar,
        # 24 hour buttons and 5-minute buttons with +/-1 adjustment.
        picker = ScheduleTimeDialog(default_run_time())
        assert len(picker._hour_buttons) == 24
        assert len(picker._minute_buttons) == 12
        assert not picker.findChildren(QCalendarWidget)
        assert picker.ok_button.isEnabled()
        picker.set_minute(17)
        assert picker.selected_date_time().time().minute() == 17
        picker.shift_minutes(1)
        assert picker.selected_date_time().time().minute() == 18
        picker.close()

        # Dropdown still accepts an arbitrary pasted ID and keeps it while
        # the recent-session list is refreshed.
        page.session.set_session_id("pasted-session-id")
        page.set_session_choices(sessions, select_latest_if_empty=True)
        assert page.session.session_id() == "pasted-session-id"

        session = "01a08c7c-df16-74c3-9357-a6cac183895c"
        page.session.set_session_id(session)
        scheduled = QDateTime.currentDateTime().addSecs(3600)
        page.set_scheduled_time(scheduled)
        page._resolved_cwd = project
        time_part = scheduled.toString("yyyyMMdd-HHmm")
        expected = project / f"codex-{session}-{time_part}.md"
        assert page.default_answer_path() == expected
        expected.touch()
        unique = expected.with_name(expected.stem + "-2.md")
        assert page.default_answer_path() == unique
        page.set_save_button_state(unique)
        page.persist_draft()
        assert page.save_button.isChecked()
        assert page.save_button.toolTip() == str(unique)

        first_id = page.task_id
        window.new_task()
        assert window.tabs.count() == 2
        second = window.tabs.currentWidget()
        assert isinstance(second, TaskPage)
        assert second.task_id != first_id
        assert second.session.session_id() == "session-newest"

        # Closing a tab hides the task; persistent task state remains and can
        # be reopened from the OpenCode-style sidebar/history.
        window.tabs.setCurrentWidget(page)
        first_index = window.tabs.indexOf(page)
        window.close_tab(first_index)
        assert store.load(first_id) is not None
        assert first_id not in window._page_by_id
        window.open_task(first_id)
        assert first_id in window._page_by_id

        store.patch(first_id, status="completed")
        window.refresh_all()
        window.rebuild_tasks_menu()
        assert any(action.text() == "History" for action in window.tasks_menu.actions())
        assert any(action.text() == "↻ Refresh Codex sessions" for action in window.tasks_menu.actions())

        palette = app.palette()
        assert palette.color(QPalette.ColorRole.Window).lightness() < palette.color(QPalette.ColorRole.WindowText).lightness()
        assert palette.color(QPalette.ColorRole.Base).lightness() < 128

        window.refresh_timer.stop()
        window.session_refresh_timer.stop()
        for task_page in list(window._page_by_id.values()):
            task_page.poll_timer.stop()
        window._quitting = True
        window.tray.hide()
        window.close()
        app.processEvents()

    watcher.timer.stop()
    print("GUI multi-task + recent sessions + reset-time picker + dark-theme smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
