#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import subprocess
import sys


def _package_installed(name: str) -> bool:
    """Best-effort Debian/Ubuntu package probe before Qt is imported."""
    if shutil.which("dpkg-query") is None:
        return False
    try:
        proc = subprocess.run(
            ["dpkg-query", "-W", "-f=${db:Status-Status}", name],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=1,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0 and proc.stdout.strip() == "installed"


# Pick the GNOME-specific Qt platform theme before importing Qt. Do not force
# Qt's generic GTK3 platform theme: on modern GNOME/libadwaita it can report a
# dark window palette while leaving view/editor surfaces light. QGnomePlatform
# is designed specifically to map GNOME settings onto Qt widgets. If it is not
# installed, leave platform-theme selection alone; system_theme.py still
# normalizes the complete application palette when GNOME requests dark mode.
if sys.platform.startswith("linux"):
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
    if (
        "GNOME" in desktop
        and not os.environ.get("QT_QPA_PLATFORMTHEME")
        and _package_installed("qgnomeplatform-qt6")
    ):
        os.environ["QT_QPA_PLATFORMTHEME"] = "gnome"

try:
    from PyQt6.QtWidgets import QApplication
except ImportError as exc:
    raise SystemExit(
        "PyQt6 is required. On Ubuntu: sudo apt install python3-pyqt6 qgnomeplatform-qt6"
    ) from exc

from system_theme import install_system_theme
from ui_chrome import install_app_chrome
from workspace import APP_NAME, MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)

    app._harr_system_theme = install_system_theme(app)  # type: ignore[attr-defined]
    install_app_chrome(app)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
