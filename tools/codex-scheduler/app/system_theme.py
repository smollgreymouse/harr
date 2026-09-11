from __future__ import annotations

import os
import shutil
import subprocess
from typing import Optional

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication


def _env_override() -> Optional[bool]:
    value = os.environ.get("HARR_CODEX_THEME", "system").strip().lower()
    if value == "dark":
        return True
    if value == "light":
        return False
    return None


def _gnome_prefers_dark() -> Optional[bool]:
    if shutil.which("gsettings") is None:
        return None

    try:
        proc = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=1,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    if proc.returncode != 0:
        return None
    value = proc.stdout.strip().strip("'\"").lower()
    if value == "prefer-dark":
        return True
    if value in {"default", "prefer-light"}:
        return False
    return None


def _qt_prefers_dark(app: QApplication) -> Optional[bool]:
    try:
        scheme = app.styleHints().colorScheme()
        color_scheme = getattr(Qt, "ColorScheme", None)
        if color_scheme is not None:
            if scheme == color_scheme.Dark:
                return True
            if scheme == color_scheme.Light:
                return False
    except (AttributeError, RuntimeError):
        pass
    return None


def system_prefers_dark(app: QApplication) -> bool:
    override = _env_override()
    if override is not None:
        return override

    # GNOME's Qt platform integration does not always propagate prefer-dark to
    # QStyleHints. Prefer the desktop's public GSettings value when available.
    gnome = _gnome_prefers_dark()
    if gnome is not None:
        return gnome

    qt = _qt_prefers_dark(app)
    if qt is not None:
        return qt

    palette = app.palette()
    return palette.color(QPalette.ColorRole.Window).lightness() < 128


def _dark_palette(source: QPalette) -> QPalette:
    palette = QPalette(source)
    window = QColor(36, 36, 36)
    base = QColor(30, 30, 30)
    alternate = QColor(46, 46, 46)
    text = QColor(238, 238, 238)
    disabled = QColor(145, 145, 145)

    palette.setColor(QPalette.ColorRole.Window, window)
    palette.setColor(QPalette.ColorRole.WindowText, text)
    palette.setColor(QPalette.ColorRole.Base, base)
    palette.setColor(QPalette.ColorRole.AlternateBase, alternate)
    palette.setColor(QPalette.ColorRole.ToolTipBase, alternate)
    palette.setColor(QPalette.ColorRole.ToolTipText, text)
    palette.setColor(QPalette.ColorRole.Text, text)
    palette.setColor(QPalette.ColorRole.Button, alternate)
    palette.setColor(QPalette.ColorRole.ButtonText, text)
    palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.PlaceholderText, disabled)

    # Keep the platform/accent highlight supplied by Qt instead of inventing a
    # separate application accent colour.
    highlight = source.color(QPalette.ColorRole.Highlight)
    if not highlight.isValid():
        highlight = QColor(53, 132, 228)
    palette.setColor(QPalette.ColorRole.Highlight, highlight)
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))

    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
        QPalette.ColorRole.PlaceholderText,
    ):
        palette.setColor(QPalette.ColorGroup.Disabled, role, disabled)
    return palette


class SystemThemeWatcher:
    def __init__(self, app: QApplication) -> None:
        self.app = app
        self._light_palette = QPalette(app.style().standardPalette())
        self._dark: Optional[bool] = None
        self.timer = QTimer(app)
        self.timer.setInterval(3000)
        self.timer.timeout.connect(self.refresh)

        signal = getattr(app.styleHints(), "colorSchemeChanged", None)
        if signal is not None:
            try:
                signal.connect(lambda *_: self.refresh(force=True))
            except (AttributeError, TypeError):
                pass

    def start(self) -> None:
        self.refresh(force=True)
        self.timer.start()

    def refresh(self, force: bool = False) -> None:
        dark = system_prefers_dark(self.app)
        if not force and dark == self._dark:
            return
        self._dark = dark
        self.app.setPalette(_dark_palette(self._light_palette) if dark else QPalette(self._light_palette))


def install_system_theme(app: QApplication) -> SystemThemeWatcher:
    watcher = SystemThemeWatcher(app)
    watcher.start()
    return watcher
