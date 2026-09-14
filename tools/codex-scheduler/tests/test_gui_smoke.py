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
from datetime_picker import NumberStepper, ScheduleTimeDialog, default_run_time
from system_theme import install_system_theme, palette_has_complete_dark_surfaces
from task_page_native import TaskPage
from task_store import TaskStore
from ui_chrome import PlusTabBar, install_app_chrome
from workspace import MainWindow


def main() -> int:
    app = QApplication.instance() or QApplication([])

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
            {"id": "session-newest", "name": "Newest", "preview": "Newest preview", "cwd": str(project), "updatedAt": 300},
            {"id": "session-older", "name": None, "preview": "Older", "cwd": str(project), "updatedAt": 200},
        ]
        workspace_module.list_codex_sessions = lambda **_kwargs: sessions
        task_page_module.resolve_session_cwd = lambda _session: project

        store = TaskStore(root / "state")
        window = MainWindow(store)
        window.refresh_codex_sessions()

        tab_bar = window.tabs.tabBar()
        assert isinstance(tab_bar, PlusTabBar)
        assert tab_bar.minimumHeight() == PlusTabBar.BAR_HEIGHT
        assert tab_bar.maximumHeight() == PlusTabBar.BAR_HEIGHT
        assert tab_bar.plus_button.text() == "+"
        assert window.task_tree.topLevelItem(0).isExpanded()
        assert not window.task_tree.topLevelItem(1).isExpanded()

        page = window.tabs.widget(0)
        assert isinstance(page, TaskPage)
        assert (page.model.currentText(), page.reasoning.currentText(), page.speed.currentText()) == ("Terra", "High", "Standard")
        assert page.session.isEditable()
        assert page.session.session_id() == "session-newest"
        assert page.prompt.palette().color(QPalette.ColorRole.Base).lightness() < 128
        assert window.task_tree.palette().color(QPalette.ColorRole.Base).lightness() < 128

        assert page._scheduled_time is not None
        delta = QDateTime.currentDateTime().secsTo(page._scheduled_time)
        assert 5 * 3600 + 60 <= delta <= 5 * 3600 + 3 * 60

        picker = ScheduleTimeDialog(default_run_time())
        assert isinstance(picker.date, QDateEdit)
        assert picker.date.calendarPopup()
        assert picker.date.calendarWidget().firstDayOfWeek() == Qt.DayOfWeek.Monday
        assert isinstance(picker.hours, NumberStepper)
        assert picker.hours.minimumWidth() == NumberStepper.WIDTH
        assert picker.hours.maximumWidth() == NumberStepper.WIDTH
        before = picker.minutes.value.value()
        picker.minutes.plus.click()
        assert picker.minutes.value.value() == (before + 1) % 60
        assert picker.buttons.button(picker.buttons.StandardButton.Ok).isEnabled()
        picker.close()

        page.session.set_session_id("pasted-session-id")
        page.set_session_choices(sessions, select_latest_if_empty=True)
        assert page.session.session_id() == "pasted-session-id"

        first_id = page.task_id
        window.new_task()
        assert window.tabs.count() == 2
        window.close_task_tab_by_id(first_id, preserve_task=True)
        assert store.load(first_id) is not None
        window.open_task(first_id)
        assert first_id in window._page_by_id

        store.patch(first_id, status="completed")
        window.refresh_all()
        window.rebuild_tasks_menu()
        assert any(action.text() == "History" for action in window.tasks_menu.actions())

        window.refresh_timer.stop()
        window.session_refresh_timer.stop()
        for task_page in list(window._page_by_id.values()):
            task_page.poll_timer.stop()
        window._quitting = True
        window.tray.hide()
        window.close()
        app.processEvents()

    watcher.timer.stop()
    print("GUI polished-chrome + dark-theme + picker smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
