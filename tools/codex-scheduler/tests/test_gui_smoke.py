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

from PyQt6.QtCore import QDateTime, Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication, QDateEdit

import task_page_native as task_page_module
import workspace as workspace_module
from datetime_picker import ScheduleTimeDialog, default_run_time
from system_theme import install_system_theme, palette_has_complete_dark_surfaces
from task_page_native import TaskPage
from task_store import TaskStore
from ui_chrome import PlusTabBar, install_app_chrome
from workspace import MainWindow


def main() -> int:
    app = QApplication.instance() or QApplication([])

    # Regression for Ubuntu/GNOME: some Qt platform themes report a dark
    # Window while keeping Base white. The application must normalize the
    # entire palette instead of treating Window alone as proof of dark mode.
    mixed = QPalette(app.palette())
    mixed.setColor(QPalette.ColorRole.Window, QColor(34, 34, 34))
    mixed.setColor(QPalette.ColorRole.WindowText, QColor(240, 240, 240))
    mixed.setColor(QPalette.ColorRole.Base, QColor(255, 255, 255))
    mixed.setColor(QPalette.ColorRole.AlternateBase, QColor(250, 250, 250))
    app.setPalette(mixed)

    watcher = install_system_theme(app)
    install_app_chrome(app)
    assert palette_has_complete_dark_surfaces(app.palette())

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        project = root / "project"
        project.mkdir()
        sessions = [
            {"id": "session-newest", "name": "Newest task", "preview": "Newest preview", "cwd": str(project), "updatedAt": 300},
            {"id": "session-older", "name": None, "preview": "Older task", "cwd": str(project), "updatedAt": 200},
        ]
        workspace_module.list_codex_sessions = lambda **_kwargs: sessions
        task_page_module.resolve_session_cwd = lambda _session: project

        store = TaskStore(root / "state")
        window = MainWindow(store)
        window.refresh_codex_sessions()

        assert window.tabs.count() == 1
        assert isinstance(window.tabs.tabBar(), PlusTabBar)
        assert window.tabs.tabBar().plus_button.text() == "+"
        assert window.new_button.text().endswith("New task")
        assert window.search.placeholderText() == "Search tasks"
        assert window.sidebar.isVisibleTo(window)

        page = window.tabs.widget(0)
        assert isinstance(page, TaskPage)
        assert page.model.currentText() == "Terra"
        assert page.reasoning.currentText() == "High"
        assert page.speed.currentText() == "Standard"
        assert page.model.property("chromeRole") == "selector"
        assert page.reasoning.property("chromeRole") == "selector"
        assert page.speed.property("chromeRole") == "selector"
        assert page.session.isEditable()
        assert page.session.session_id() == "session-newest"
        assert page.session.count() == 2
        assert page.when.text()
        assert page.prompt.placeholderText() == "What should Codex do?"
        assert page.project_button.text() == "⋮"
        assert page.save_button.isCheckable()
        assert page.save_button.text() == "Save final answer…"

        # Editable/view surfaces inherit the normalized dark Base role.
        assert page.prompt.palette().color(QPalette.ColorRole.Base).lightness() < 128
        assert window.task_tree.palette().color(QPalette.ColorRole.Base).lightness() < 128
        assert page.session.palette().color(QPalette.ColorRole.Base).lightness() < 128

        assert page._scheduled_time is not None
        delta = QDateTime.currentDateTime().secsTo(page._scheduled_time)
        assert 5 * 3600 + 60 <= delta <= 5 * 3600 + 3 * 60, delta

        picker = ScheduleTimeDialog(default_run_time())
        assert isinstance(picker.date, QDateEdit)
        assert picker.date.calendarPopup()
        calendar = picker.date.calendarWidget()
        assert calendar is not None
        assert calendar.firstDayOfWeek() == Qt.DayOfWeek.Monday
        assert not calendar.isVisible()
        before_minute = picker.minutes.value.value()
        picker.minutes.plus.click()
        assert picker.minutes.value.value() == (before_minute + 1) % 60
        assert picker.buttons.button(picker.buttons.StandardButton.Ok).isEnabled()
        assert picker.palette().color(QPalette.ColorRole.Base).lightness() < 128
        picker.close()

        page.session.set_session_id("pasted-session-id")
        page.set_session_choices(sessions, select_latest_if_empty=True)
        assert page.session.session_id() == "pasted-session-id"

        session = "01a08c7c-df16-74c3-9357-a6cac183895c"
        page.session.set_session_id(session)
        scheduled = QDateTime.currentDateTime().addSecs(3600)
        page._scheduled_time = scheduled
        page._refresh_when_button()
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

        active_root = window.task_tree.topLevelItem(0)
        history_root = window.task_tree.topLevelItem(1)
        assert active_root.isExpanded()
        assert not history_root.isExpanded()
        window.set_sidebar_visible(False)
        assert window.sidebar.isHidden()
        window.set_sidebar_visible(True)
        assert not window.sidebar.isHidden()

        first_id = page.task_id
        window.new_task()
        assert window.tabs.count() == 2
        second = window.tabs.currentWidget()
        assert isinstance(second, TaskPage)
        assert second.task_id != first_id
        assert second.session.session_id() == "session-newest"

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
        assert palette_has_complete_dark_surfaces(palette)

        window.refresh_timer.stop()
        window.session_refresh_timer.stop()
        for task_page in list(window._page_by_id.values()):
            task_page.poll_timer.stop()
        window._quitting = True
        window.tray.hide()
        window.close()
        app.processEvents()

    watcher.timer.stop()
    print("GUI multi-task + mixed-dark-palette regression + native picker smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
