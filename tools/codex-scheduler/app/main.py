#!/usr/bin/env python3
from __future__ import annotations

import signal
import sys

try:
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication
except ImportError as exc:
    raise SystemExit("PyQt6 is required. On Ubuntu: sudo apt install python3-pyqt6") from exc

# Keep the task page focused on task behavior while the session selector owns
# the presentation/UUID split.  TaskPage resolves SessionComboBox from its
# module globals when a page is instantiated, so installing the selector here
# is explicit and avoids duplicating session-state logic in the page itself.
import task_page_native
from session_selector import SessionComboBox
from system_theme import install_system_theme
from tray_workflow import TrayWorkflow
from ui_chrome import install_app_chrome
from workspace import APP_NAME, MainWindow

task_page_native.SessionComboBox = SessionComboBox


def main() -> int:
    # Do not force QT_QPA_PLATFORMTHEME.  On GNOME that can select
    # qgnomeplatform even when it cannot resolve a color-scheme name, producing
    # `qt.qpa.qgnomeplatform: Could not find color scheme ""`.  Qt keeps its
    # platform-native style and system_theme.py normalizes only the palette
    # when GNOME's documented color-scheme preference says dark.
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)
    app._harr_system_theme = install_system_theme(app)  # type: ignore[attr-defined]
    install_app_chrome(app)

    window = MainWindow()
    window._tray_workflow = TrayWorkflow(window)  # type: ignore[attr-defined]
    window.show()

    def request_quit(_signum: int, _frame: object) -> None:
        # Python delivers Unix signals on the main thread. Queue the actual Qt
        # shutdown instead of raising KeyboardInterrupt from an arbitrary Qt
        # slot (for example refresh_all), which PyQt may print and then keep
        # running. This also makes IDE Stop/SIGTERM deterministic.
        QTimer.singleShot(0, window.quit_app)

    signal.signal(signal.SIGINT, request_quit)
    signal.signal(signal.SIGTERM, request_quit)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
