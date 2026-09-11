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


def palette_is_dark(palette: QPalette) -> bool:
    return palette.color(QPalette.ColorRole.Window).lightness() < palette.color(QPalette.ColorRole.WindowText).lightness()


def system_prefers_dark(app: QApplication) -> bool:
    override = _env_override()
    if override is not None:
        return override
    qt = _qt_prefers_dark(app)
    if qt is not None:
        return qt
    gnome = _gnome_prefers_dark()
    if gnome is not None:
        return gnome
    return palette_is_dark(app.palette())


def _dark_palette(source: QPalette) -> QPalette:
    """Last-resort palette for Qt builds that ignore GNOME prefer-dark.

    Standard widgets are still painted by the current QStyle; this only fixes
    the color roles when the platform theme failed to supply dark ones.
    """
    palette = QPalette(source)
    window = QColor(36, 36, 36)
    base = QColor(30, 30, 30)
    alternate = QColor(46, 46, 46)
    text = QColor(238, 238, 238)
    disabled = QColor(145, 145, 145)
    for role, color in (
        (QPalette.ColorRole.Window, window),
        (QPalette.ColorRole.WindowText, text),
        (QPalette.ColorRole.Base, base),
        (QPalette.ColorRole.AlternateBase, alternate),
        (QPalette.ColorRole.ToolTipBase, alternate),
        (QPalette.ColorRole.ToolTipText, text),
        (QPalette.ColorRole.Text, text),
        (QPalette.ColorRole.Button, alternate),
        (QPalette.ColorRole.ButtonText, text),
        (QPalette.ColorRole.PlaceholderText, disabled),
    ):
        palette.setColor(role, color)
    highlight = source.color(QPalette.ColorRole.Highlight)
    if not highlight.isValid():
        highlight = QColor(53, 132, 228)
    palette.setColor(QPalette.ColorRole.Highlight, highlight)
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText, QPalette.ColorRole.PlaceholderText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, disabled)
    return palette


class SystemThemeWatcher:
    def __init__(self, app: QApplication) -> None:
        self.app = app
        self._platform_palette = QPalette(app.palette())
        self._last_requested: Optional[bool] = None
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
        desired_dark = system_prefers_dark(self.app)
        if not force and desired_dark == self._last_requested:
            return
        self._last_requested = desired_dark

        # If the platform theme already did the right thing, leave its palette
        # untouched. That preserves native GTK/Qt color roles and accents.
        current = self.app.palette()
        if palette_is_dark(current) == desired_dark:
            self._platform_palette = QPalette(current)
            return

        override = _env_override()
        gnome = _gnome_prefers_dark()
        if override is None and gnome is None:
            return

        if desired_dark:
            self.app.setPalette(_dark_palette(self._platform_palette))
        else:
            self.app.setPalette(QPalette(self.app.style().standardPalette()))
            self._platform_palette = QPalette(self.app.palette())


def install_system_theme(app: QApplication) -> SystemThemeWatcher:
    watcher = SystemThemeWatcher(app)
    watcher.start()
    return watcher
