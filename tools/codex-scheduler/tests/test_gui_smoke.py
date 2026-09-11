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
from PyQt6.QtWidgets import QApplication
from main import MainWindow
from system_theme import install_system_theme
from task_page import TaskPage
from task_store import TaskStore


def main() -> int:
    app = QApplication.instance() or QApplication([])
    watcher = install_system_theme(app)

    with tempfile.TemporaryDirectory() as tmp:
        store = TaskStore(Path(tmp) / "state")
        window = MainWindow(store)
        assert window.tabs.count() == 1
        assert window.new_button.text().endswith("New task")
        assert window.search.placeholderText() == "Search tasks"

        page = window.tabs.widget(0)
        assert isinstance(page, TaskPage)
        assert page.model.currentText() == "Terra"
        assert page.reasoning.currentText() == "High"
        assert page.speed.currentText() == "Standard"
        assert page.session.placeholderText() == "Session ID"
        assert page.when.isReadOnly()
        assert page.prompt.placeholderText() == "What should Codex do?"
        assert page.project_button.text() == "⋮"
        assert page.save_button.isCheckable()
        assert page.save_button.text() == "Save final answer…"

        first_id = page.task_id
        page.session.setText("01a08c7c-df16-74c3-9357-a6cac183895c")
        page.prompt.setPlainText("Implement the worker pool test")
        scheduled = QDateTime.currentDateTime().addSecs(3600)
        page.set_scheduled_time(scheduled)
        project = Path(tmp) / "project"
        project.mkdir()
        page._resolved_cwd = project
        time_part = scheduled.toString("yyyyMMdd-HHmm")
        expected = project / f"codex-01a08c7c-df16-74c3-9357-a6cac183895c-{time_part}.md"
        assert page.default_answer_path() == expected
        expected.touch()
        unique = expected.with_name(expected.stem + "-2.md")
        assert page.default_answer_path() == unique
        page.set_save_button_state(unique)
        page.persist_draft()
        assert page.save_button.isChecked()
        assert page.save_button.toolTip() == str(unique)

        window.new_task()
        assert window.tabs.count() == 2
        second = window.tabs.currentWidget()
        assert isinstance(second, TaskPage)
        second_id = second.task_id
        assert second_id != first_id

        # Closing a non-empty tab only hides it; task state remains available
        # from the sidebar/history model and can be reopened.
        window.tabs.setCurrentWidget(page)
        first_index = window.tabs.indexOf(page)
        window.close_tab(first_index)
        assert store.load(first_id) is not None
        assert first_id not in window._page_by_id
        window.open_task(first_id)
        assert first_id in window._page_by_id

        # An untouched draft is disposable when its tab is closed.
        second_page = window._page_by_id[second_id]
        second_index = window.tabs.indexOf(second_page)
        window.close_tab(second_index)
        assert store.load(second_id) is None

        store.patch(first_id, status="completed")
        window.refresh_all()
        window.rebuild_tasks_menu()
        assert any(action.text() == "History" for action in window.tasks_menu.actions())

        palette = app.palette()
        assert palette.color(QPalette.ColorRole.Window).lightness() < palette.color(QPalette.ColorRole.WindowText).lightness()
        assert palette.color(QPalette.ColorRole.Base).lightness() < 128

        window.refresh_timer.stop()
        for task_page in list(window._page_by_id.values()):
            task_page.poll_timer.stop()
        window._quitting = True
        window.tray.hide()
        window.close()
        app.processEvents()

    watcher.timer.stop()
    print("GUI multi-task workspace + persistence + dark-theme smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
