#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

try:
    from PyQt6.QtCore import QPoint, Qt, QTimer
    from PyQt6.QtGui import QAction, QCloseEvent, QIcon
    from PyQt6.QtWidgets import (
        QApplication,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMenu,
        QMessageBox,
        QPushButton,
        QSplitter,
        QSystemTrayIcon,
        QTabWidget,
        QToolButton,
        QTreeWidget,
        QTreeWidgetItem,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:
    raise SystemExit("PyQt6 is required. On Ubuntu 24.04: sudo apt install python3-pyqt6") from exc

from system_theme import install_system_theme
from task_page import STATUS_ICON, TaskPage, task_display_title, task_status_text
from task_store import ACTIVE_STATUSES, FINISHED_STATUSES, TaskStore

APP_NAME = "Harr Codex Scheduler"
TASK_ID_ROLE = int(Qt.ItemDataRole.UserRole)


class MainWindow(QMainWindow):
    def __init__(self, store: TaskStore | None = None) -> None:
        super().__init__()
        self.store = store or TaskStore()
        self.setWindowTitle(APP_NAME)
        self.resize(1120, 780)
        self._quitting = False
        self._page_by_id: dict[str, TaskPage] = {}

        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.splitter.setChildrenCollapsible(False)
        self.setCentralWidget(self.splitter)
        self._build_sidebar()
        self._build_workspace()
        self.splitter.setSizes([270, 850])

        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(1200)
        self.refresh_timer.timeout.connect(self.refresh_all)
        self.refresh_timer.start()

        self.setup_tray()
        self.restore_workspace()
        self.refresh_sidebar()
        self.apply_workspace_style()

    def _build_sidebar(self) -> None:
        sidebar = QWidget(self)
        sidebar.setObjectName("sidebar")
        sidebar.setMinimumWidth(215)
        sidebar.setMaximumWidth(390)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(10, 10, 8, 10)
        layout.setSpacing(8)

        header = QHBoxLayout()
        self.new_button = QPushButton("＋ New task", sidebar)
        self.new_button.setObjectName("newTaskButton")
        self.new_button.clicked.connect(self.new_task)
        self.tasks_button = QToolButton(sidebar)
        self.tasks_button.setText("☰")
        self.tasks_button.setToolTip("All tasks")
        self.tasks_menu = QMenu(self.tasks_button)
        self.tasks_menu.aboutToShow.connect(self.rebuild_tasks_menu)
        self.tasks_button.setMenu(self.tasks_menu)
        self.tasks_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        header.addWidget(self.new_button, 1)
        header.addWidget(self.tasks_button)
        layout.addLayout(header)

        self.search = QLineEdit(sidebar)
        self.search.setPlaceholderText("Search tasks")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh_sidebar)
        layout.addWidget(self.search)

        self.task_tree = QTreeWidget(sidebar)
        self.task_tree.setHeaderHidden(True)
        self.task_tree.setRootIsDecorated(False)
        self.task_tree.setIndentation(12)
        self.task_tree.setUniformRowHeights(False)
        self.task_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.task_tree.customContextMenuRequested.connect(self.open_task_context_menu)
        self.task_tree.itemClicked.connect(self.tree_item_clicked)
        layout.addWidget(self.task_tree, 1)

        self.sidebar_status = QLabel("", sidebar)
        self.sidebar_status.setObjectName("sidebarStatus")
        layout.addWidget(self.sidebar_status)
        self.sidebar = sidebar
        self.splitter.addWidget(sidebar)

    def _build_workspace(self) -> None:
        host = QWidget(self)
        layout = QVBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.tabs = QTabWidget(host)
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(lambda _index: self.save_ui_state())
        self.tabs.tabBar().tabMoved.connect(lambda _from, _to: self.save_ui_state())

        corner = QWidget(self.tabs)
        corner_layout = QHBoxLayout(corner)
        corner_layout.setContentsMargins(0, 0, 4, 0)
        corner_layout.setSpacing(2)
        plus = QToolButton(corner); plus.setText("＋"); plus.setToolTip("New task"); plus.clicked.connect(self.new_task)
        menu = QToolButton(corner); menu.setText("⋮"); menu.setToolTip("All tasks")
        menu.setMenu(self.tasks_menu); menu.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        corner_layout.addWidget(plus); corner_layout.addWidget(menu)
        self.tabs.setCornerWidget(corner, Qt.Corner.TopRightCorner)

        self.empty_hint = QLabel("Create a task with ＋ New task or reopen one from the sidebar", host)
        self.empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_hint.setObjectName("emptyHint")
        layout.addWidget(self.tabs, 1)
        layout.addWidget(self.empty_hint)
        self.workspace = host
        self.splitter.addWidget(host)
        self.update_empty_hint()

    def apply_workspace_style(self) -> None:
        self.setStyleSheet(
            """
            QWidget#sidebar { border-right: 1px solid palette(mid); }
            QPushButton#newTaskButton { text-align: left; padding: 7px 9px; border: 0; }
            QPushButton#newTaskButton:hover { background: palette(alternate-base); }
            QTreeWidget { border: 0; outline: 0; background: transparent; }
            QTreeWidget::item { padding: 5px 4px; border-radius: 5px; }
            QTreeWidget::item:selected { background: palette(highlight); color: palette(highlighted-text); }
            QTabWidget::pane { border: 0; }
            QTabBar::tab { padding: 8px 12px; border: 0; min-width: 110px; }
            QTabBar::tab:selected { background: palette(base); }
            QLineEdit, QTextEdit, QComboBox { padding: 6px; }
            QLabel#emptyHint, QLabel#sidebarStatus { color: palette(mid); }
            QLabel#taskStatus { padding: 4px 7px; }
            """
        )

    def setup_tray(self) -> None:
        icon = QIcon.fromTheme("utilities-terminal")
        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip(APP_NAME)
        menu = QMenu(self)
        show_action = QAction("Show", self); show_action.triggered.connect(self.restore)
        new_action = QAction("New task", self); new_action.triggered.connect(self.new_task)
        quit_action = QAction("Quit", self); quit_action.triggered.connect(self.quit_app)
        menu.addAction(show_action)
        menu.addAction(new_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.restore() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()

    def restore_workspace(self) -> None:
        ui = self.store.load_ui()
        opened = False
        for task_id in ui.get("open_task_ids", []):
            if self.store.load(str(task_id)) is not None:
                self.open_task(str(task_id), make_current=False)
                opened = True
        current = ui.get("current_task_id")
        if current and str(current) in self._page_by_id:
            page = self._page_by_id[str(current)]
            self.tabs.setCurrentWidget(page)
        if not opened and not self.store.list():
            self.new_task()
        self.update_empty_hint()

    def new_task(self) -> None:
        task = self.store.new_draft()
        self.open_task(str(task["id"]), make_current=True)
        self.refresh_sidebar()

    def open_task(self, task_id: str, *, make_current: bool = True) -> None:
        if task_id in self._page_by_id:
            if make_current:
                self.tabs.setCurrentWidget(self._page_by_id[task_id])
            return
        task = self.store.load(task_id)
        if task is None:
            return
        page = TaskPage(self.store, task, self.task_changed, self.tabs)
        self._page_by_id[task_id] = page
        index = self.tabs.addTab(page, self.tab_title(task))
        self.tabs.setTabToolTip(index, self.tab_tooltip(task))
        if make_current:
            self.tabs.setCurrentIndex(index)
        self.update_empty_hint()
        self.save_ui_state()

    def tab_title(self, task: dict) -> str:
        status = str(task.get("status") or "draft")
        return f"{STATUS_ICON.get(status, '•')} {task_display_title(task, 28)}"

    def tab_tooltip(self, task: dict) -> str:
        bits = [task_status_text(task)]
        if task.get("session"):
            bits.append(str(task["session"]))
        if task.get("scheduled"):
            bits.append(str(task["scheduled"]))
        return "\n".join(bits)

    def close_tab(self, index: int) -> None:
        page = self.tabs.widget(index)
        if not isinstance(page, TaskPage):
            self.tabs.removeTab(index)
            return
        task_id = page.task_id
        task = self.store.load(task_id)
        self.tabs.removeTab(index)
        self._page_by_id.pop(task_id, None)
        page.deleteLater()
        if task is not None and self.store.is_empty_draft(task):
            self.store.delete(task_id, delete_log=True, delete_answer=False)
        self.save_ui_state()
        self.refresh_sidebar()
        self.update_empty_hint()

    def close_task_tab_by_id(self, task_id: str, *, preserve_task: bool = True) -> None:
        page = self._page_by_id.get(task_id)
        if page is None:
            return
        index = self.tabs.indexOf(page)
        if index < 0:
            return
        if preserve_task:
            self.tabs.removeTab(index)
            self._page_by_id.pop(task_id, None)
            page.deleteLater()
            self.save_ui_state()
            self.update_empty_hint()
        else:
            self.close_tab(index)

    def task_changed(self, task_id: str) -> None:
        task = self.store.load(task_id)
        if task is None:
            return
        page = self._page_by_id.get(task_id)
        if page is not None:
            index = self.tabs.indexOf(page)
            if index >= 0:
                self.tabs.setTabText(index, self.tab_title(task))
                self.tabs.setTabToolTip(index, self.tab_tooltip(task))
        self.refresh_sidebar()

    def refresh_all(self) -> None:
        self.refresh_sidebar()
        for task_id, page in list(self._page_by_id.items()):
            task = self.store.load(task_id)
            if task is None:
                self.close_task_tab_by_id(task_id, preserve_task=True)
                continue
            index = self.tabs.indexOf(page)
            if index >= 0:
                self.tabs.setTabText(index, self.tab_title(task))

    def refresh_sidebar(self) -> None:
        query = self.search.text().strip().lower() if hasattr(self, "search") else ""
        tasks = self.store.list()
        self.task_tree.blockSignals(True)
        self.task_tree.clear()
        active_root = self._add_group("ACTIVE")
        history_root = self._add_group("HISTORY")
        active_count = 0
        history_count = 0
        for task in tasks:
            haystack = " ".join([
                str(task.get("session") or ""),
                str(task.get("prompt") or ""),
                str(task.get("cwd") or ""),
                str(task.get("model") or ""),
                str(task.get("status") or ""),
            ]).lower()
            if query and query not in haystack:
                continue
            status = str(task.get("status") or "draft")
            root = active_root if status in ACTIVE_STATUSES else history_root
            if root is active_root:
                active_count += 1
            else:
                history_count += 1
            self._add_task_item(root, task)
        active_root.setText(0, f"ACTIVE  {active_count}")
        history_root.setText(0, f"HISTORY  {history_count}")
        active_root.setExpanded(True)
        history_root.setExpanded(True)
        self.task_tree.blockSignals(False)
        self.sidebar_status.setText(f"{len(tasks)} task{'s' if len(tasks) != 1 else ''}")

    def _add_group(self, text: str) -> QTreeWidgetItem:
        item = QTreeWidgetItem([text])
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        font = item.font(0); font.setBold(True); item.setFont(0, font)
        self.task_tree.addTopLevelItem(item)
        return item

    def _add_task_item(self, root: QTreeWidgetItem, task: dict) -> None:
        title = task_display_title(task, 34)
        status = str(task.get("status") or "draft")
        model = str(task.get("model") or "").removeprefix("gpt-5.6-").title()
        when = str(task.get("scheduled") or "")
        when = when.replace("T", " ")[:16] if when else "unscheduled"
        text = f"{STATUS_ICON.get(status, '•')}  {title}\n    {model} · {when}"
        item = QTreeWidgetItem([text])
        item.setData(0, TASK_ID_ROLE, str(task["id"]))
        item.setToolTip(0, self.tab_tooltip(task))
        root.addChild(item)

    def tree_item_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        task_id = item.data(0, TASK_ID_ROLE)
        if task_id:
            self.open_task(str(task_id))

    def open_task_context_menu(self, pos: QPoint) -> None:
        item = self.task_tree.itemAt(pos)
        if item is None:
            return
        task_id = item.data(0, TASK_ID_ROLE)
        if not task_id:
            return
        task = self.store.load(str(task_id))
        if task is None:
            return
        menu = QMenu(self)
        self.populate_task_actions(menu, task)
        menu.exec(self.task_tree.viewport().mapToGlobal(pos))

    def rebuild_tasks_menu(self) -> None:
        self.tasks_menu.clear()
        new_action = self.tasks_menu.addAction("＋ New task")
        new_action.triggered.connect(self.new_task)
        self.tasks_menu.addSeparator()
        active_menu = self.tasks_menu.addMenu("Active")
        history_menu = self.tasks_menu.addMenu("History")
        tasks = self.store.list()
        active = [task for task in tasks if task.get("status") in ACTIVE_STATUSES]
        history = [task for task in tasks if task.get("status") in FINISHED_STATUSES]
        if not active:
            empty = active_menu.addAction("No active tasks"); empty.setEnabled(False)
        for task in active:
            sub = active_menu.addMenu(self.tab_title(task))
            self.populate_task_actions(sub, task)
        if not history:
            empty = history_menu.addAction("No finished tasks"); empty.setEnabled(False)
        for task in history:
            sub = history_menu.addMenu(self.tab_title(task))
            self.populate_task_actions(sub, task)
        if any(task.get("status") in {"scheduled", "running", "cancelling"} for task in active):
            self.tasks_menu.addSeparator()
            cancel_all = self.tasks_menu.addAction("Cancel all active jobs…")
            cancel_all.triggered.connect(self.cancel_all_active)

    def populate_task_actions(self, menu: QMenu, task: dict) -> None:
        task_id = str(task["id"])
        open_action = menu.addAction("Open")
        open_action.triggered.connect(lambda _checked=False, tid=task_id: self.open_task(tid))
        if task_id in self._page_by_id:
            close_action = menu.addAction("Close tab")
            close_action.triggered.connect(lambda _checked=False, tid=task_id: self.close_task_tab_by_id(tid, preserve_task=True))
        status = str(task.get("status") or "draft")
        if status in {"scheduled", "running", "cancelling"}:
            menu.addSeparator()
            cancel = menu.addAction("Cancel task…")
            cancel.triggered.connect(lambda _checked=False, tid=task_id: self.cancel_task(tid))
            return
        menu.addSeparator()
        delete_data = menu.addAction("Delete task data…")
        delete_data.setToolTip("Delete scheduler metadata and internal JSONL log; keep exported answer")
        delete_data.triggered.connect(lambda _checked=False, tid=task_id: self.delete_task(tid, delete_answer=False))
        if task.get("answer"):
            delete_all = menu.addAction("Delete task + saved answer…")
            delete_all.triggered.connect(lambda _checked=False, tid=task_id: self.delete_task(tid, delete_answer=True))

    def cancel_task(self, task_id: str) -> None:
        task = self.store.load(task_id)
        if task is None or task.get("status") not in {"scheduled", "running", "cancelling"}:
            return
        if QMessageBox.question(
            self,
            APP_NAME,
            f"Cancel task “{task_display_title(task, 52)}”?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.store.cancel(task_id)
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, str(exc))
            return
        page = self._page_by_id.get(task_id)
        if page is not None:
            page.refresh_from_store()
        self.refresh_sidebar()

    def cancel_all_active(self) -> None:
        jobs = [task for task in self.store.active() if task.get("status") in {"scheduled", "running", "cancelling"}]
        if not jobs:
            return
        if QMessageBox.question(
            self,
            APP_NAME,
            f"Cancel {len(jobs)} active Codex task(s)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        errors: list[str] = []
        for task in jobs:
            try:
                self.store.cancel(str(task["id"]))
            except Exception as exc:
                errors.append(f"{task_display_title(task)}: {exc}")
        self.refresh_all()
        if errors:
            QMessageBox.warning(self, APP_NAME, "\n".join(errors))

    def delete_task(self, task_id: str, *, delete_answer: bool) -> None:
        task = self.store.load(task_id)
        if task is None:
            return
        if task.get("status") in {"scheduled", "running", "cancelling"}:
            QMessageBox.warning(self, APP_NAME, "Cancel the active task before deleting it.")
            return
        extra = "\nThe exported answer file will also be deleted." if delete_answer and task.get("answer") else "\nAny exported answer file will be kept."
        if QMessageBox.question(
            self,
            APP_NAME,
            f"Delete scheduler data for “{task_display_title(task, 52)}”?{extra}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        self.close_task_tab_by_id(task_id, preserve_task=True)
        try:
            self.store.delete(task_id, delete_log=True, delete_answer=delete_answer)
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, str(exc))
            return
        self.refresh_sidebar()
        self.save_ui_state()

    def save_ui_state(self) -> None:
        ids: list[str] = []
        for index in range(self.tabs.count()):
            page = self.tabs.widget(index)
            if isinstance(page, TaskPage):
                ids.append(page.task_id)
        current = self.tabs.currentWidget()
        current_id = current.task_id if isinstance(current, TaskPage) else None
        self.store.save_ui(ids, current_id)

    def update_empty_hint(self) -> None:
        empty = self.tabs.count() == 0
        self.tabs.setVisible(not empty)
        self.empty_hint.setVisible(empty)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.save_ui_state()
        if not self._quitting and QSystemTrayIcon.isSystemTrayAvailable():
            self.hide()
            event.ignore()
            return
        event.accept()

    def restore(self) -> None:
        self.showNormal(); self.show(); self.raise_(); self.activateWindow()

    def quit_app(self) -> None:
        self._quitting = True
        self.save_ui_state()
        self.tray.hide()
        QApplication.instance().quit()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)
    app._harr_system_theme = install_system_theme(app)  # type: ignore[attr-defined]
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
