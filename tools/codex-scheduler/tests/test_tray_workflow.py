#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("HARR_CODEX_THEME", "dark")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QMenu

import task_page_native as task_page_module
import tray_workflow as tray_module
import workspace as workspace_module
from task_store import TaskStore
from tray_workflow import QuickScheduleDialog, TrayWorkflow
from workspace import MainWindow


def submenu(menu: QMenu, prefix: str) -> QMenu:
    for action in menu.actions():
        child = action.menu()
        if child is not None and action.text().startswith(prefix):
            return child
    raise AssertionError(f"submenu not found: {prefix}")


def main() -> int:
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        project = root / "project"
        project.mkdir()
        sessions = [
            {"id": "session-forest-123456", "name": "Natural forest pass", "preview": "forest", "cwd": str(project)},
            {"id": "session-road-654321", "name": "Road cleanup", "preview": "roads", "cwd": str(project)},
        ]
        workspace_module.list_codex_sessions = lambda **_kwargs: sessions
        task_page_module.resolve_session_cwd = lambda _session: project

        store = TaskStore(root / "state")
        window = MainWindow(store)
        window.refresh_codex_sessions()
        controller = TrayWorkflow(window)
        controller.rebuild()

        sessions_menu = submenu(controller.menu, "Schedule for session")
        visible = [action.text() for action in sessions_menu.actions() if not action.isSeparator()]
        assert "Natural forest pass" in visible
        assert "Road cleanup" in visible
        assert not any("session-forest-123456" in text for text in visible)
        forest_action = next(action for action in sessions_menu.actions() if action.text() == "Natural forest pass")
        assert "session-forest-123456" in forest_action.toolTip()

        active_menu = submenu(controller.menu, "Active tasks")
        assert active_menu.title() == "Active tasks (0)"

        task = store.new_draft()
        task = store.patch(
            str(task["id"]),
            status="scheduled",
            session="session-forest-123456",
            prompt="Continue natural forest implementation",
            scheduled="2026-09-15T20:30:00+03:00",
            cwd=str(project),
        )
        controller.rebuild()
        active_menu = submenu(controller.menu, "Active tasks")
        assert active_menu.title() == "Active tasks (1)"
        active_actions = [action for action in active_menu.actions() if not action.isSeparator() and action.isEnabled()]
        assert len(active_actions) == 1
        assert "Continue natural forest implementation" in active_actions[0].text()
        active_actions[0].trigger()
        assert str(task["id"]) in window._page_by_id

        original_schedule = tray_module.schedule_quick_task
        try:
            def fake_schedule(store_arg, *, session_id, prompt, run_time, **_kwargs):
                created = store_arg.new_draft()
                return store_arg.patch(
                    str(created["id"]),
                    status="scheduled",
                    session=session_id,
                    prompt=prompt,
                    scheduled=run_time.toString(Qt.DateFormat.ISODate),
                    cwd=str(project),
                )

            tray_module.schedule_quick_task = fake_schedule
            dialog = QuickScheduleDialog(store, sessions[1])
            assert dialog.windowTitle() == "Schedule Codex task"
            assert dialog.when.text()
            assert dialog.prompt.placeholderText() == "What should Codex do?"
            dialog.prompt.setPlainText("Fix the road edge cases")
            dialog.schedule_now()
            assert dialog.result() == dialog.DialogCode.Accepted
            assert dialog.scheduled_task is not None
            assert dialog.scheduled_task["session"] == "session-road-654321"
            assert dialog.scheduled_task["prompt"] == "Fix the road edge cases"
            dialog.close()
        finally:
            tray_module.schedule_quick_task = original_schedule

        window.refresh_timer.stop()
        window.session_refresh_timer.stop()
        for page in list(window._page_by_id.values()):
            page.poll_timer.stop()
        window._quitting = True
        window.tray.hide()
        window.close()
        app.processEvents()

    print("tray quick-schedule + active-task menu tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
