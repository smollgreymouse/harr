#!/usr/bin/env python3
from __future__ import annotations

import os
import sys

# Platform theme selection must happen before importing Qt. On GNOME prefer
# Ubuntu's Qt 6 GTK platform theme when the user has not explicitly selected
# another Qt theme. This lets QStyle draw standard controls from the desktop
# theme instead of the application trying to imitate GTK itself.
if sys.platform.startswith("linux"):
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
    if "GNOME" in desktop and not os.environ.get("QT_QPA_PLATFORMTHEME"):
        os.environ["QT_QPA_PLATFORMTHEME"] = "gtk3"

try:
    from PyQt6.QtWidgets import QApplication
except ImportError as exc:
    raise SystemExit("PyQt6 is required. On Ubuntu: sudo apt install python3-pyqt6") from exc

from system_theme import install_system_theme
from ui_chrome import install_app_chrome
from workspace import APP_NAME, MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)

    # Native platform QStyle owns standard controls. The watcher is only a
    # fallback for GNOME installations where Qt still fails to expose the
    # desktop light/dark preference through its palette/style hints.
    app._harr_system_theme = install_system_theme(app)  # type: ignore[attr-defined]
    install_app_chrome(app)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
