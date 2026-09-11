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


def _is_dark(color: QColor) -> bool:
    return color.lightness() < 128


def _is_light(color: QColor) -> bool:
    return color.lightness() >= 128


def palette_has_complete_dark_surfaces(palette: QPalette) -> bool:
    """Reject the common GNOME/Qt half-dark palette.

    A palette is only considered dark when both top-level windows and editable
    / item-view / button surfaces are dark, with readable light foregrounds.
    Checking Window alone is insufficient: qgtk3 can return a dark Window with
    a white Base, which produces exactly the mixed UI we want to avoid.
    """
    surface_roles = (
        QPalette.ColorRole.Window,
        QPalette.ColorRole.Base,
        QPalette.ColorRole.AlternateBase,
        QPalette.ColorRole.Button,
        QPalette.ColorRole.ToolTipBase,
    )
    text_roles = (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
        QPalette.ColorRole.ToolTipText,
    )
    for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
        if not all(_is_dark(palette.color(group, role)) for role in surface_roles):
            return False
        if not all(_is_light(palette.color(group, role)) for role in text_roles):
            return False
    return True


def system_prefers_dark(app: QApplication) -> bool:
    override = _env_override()
    if override is not None:
        return override

    # GNOME's public preference is authoritative on GNOME. Some Qt platform
    # plugins expose ColorScheme.Dark while still supplying a mixed palette.
    gnome = _gnome_prefers_dark()
    if gnome is not None:
        return gnome

    qt = _qt_prefers_dark(app)
    if qt is not None:
        return qt

    palette = app.palette()
    return _is_dark(palette.color(QPalette.ColorRole.Window))


def _set_group_palette(
    palette: QPalette,
    group: QPalette.ColorGroup,
    *,
    window: QColor,
    base: QColor,
    alternate: QColor,
    button: QColor,
    text: QColor,
    muted: QColor,
    highlight: QColor,
) -> None:
    roles: dict[QPalette.ColorRole, QColor] = {
        QPalette.ColorRole.Window: window,
        QPalette.ColorRole.WindowText: text,
        QPalette.ColorRole.Base: base,
        QPalette.ColorRole.AlternateBase: alternate,
        QPalette.ColorRole.ToolTipBase: alternate,
        QPalette.ColorRole.ToolTipText: text,
        QPalette.ColorRole.Text: text,
        QPalette.ColorRole.Button: button,
        QPalette.ColorRole.ButtonText: text,
        QPalette.ColorRole.BrightText: QColor(255, 255, 255),
        QPalette.ColorRole.PlaceholderText: muted,
        QPalette.ColorRole.Highlight: highlight,
        QPalette.ColorRole.HighlightedText: QColor(255, 255, 255),
        QPalette.ColorRole.Light: QColor(76, 77, 81),
        QPalette.ColorRole.Midlight: QColor(61, 62, 66),
        QPalette.ColorRole.Mid: QColor(72, 73, 77),
        QPalette.ColorRole.Dark: QColor(20, 21, 23),
        QPalette.ColorRole.Shadow: QColor(8, 9, 10),
        QPalette.ColorRole.Link: highlight.lighter(125),
        QPalette.ColorRole.LinkVisited: QColor(190, 140, 235),
    }
    for role, color in roles.items():
        palette.setColor(group, role, color)


def complete_dark_palette(source: QPalette) -> QPalette:
    """Create one coherent dark palette for every standard Qt widget.

    QStyle still owns widget geometry and painting. We only make the color
    contract complete, so views/editors/menus/buttons cannot fall back to a
    light Base role while the application window is dark.
    """
    palette = QPalette(source)
    highlight = source.color(QPalette.ColorGroup.Active, QPalette.ColorRole.Highlight)
    if not highlight.isValid() or highlight.lightness() < 55:
        highlight = QColor(53, 132, 228)

    active = dict(
        window=QColor(34, 35, 38),
        base=QColor(27, 28, 31),
        alternate=QColor(42, 43, 47),
        button=QColor(47, 48, 52),
        text=QColor(238, 238, 240),
        muted=QColor(154, 155, 160),
        highlight=highlight,
    )
    _set_group_palette(palette, QPalette.ColorGroup.Active, **active)
    _set_group_palette(palette, QPalette.ColorGroup.Inactive, **active)

    disabled = dict(active)
    disabled["text"] = QColor(126, 127, 132)
    disabled["muted"] = QColor(104, 105, 110)
    disabled["button"] = QColor(39, 40, 43)
    disabled["highlight"] = QColor(70, 76, 86)
    _set_group_palette(palette, QPalette.ColorGroup.Disabled, **disabled)
    return palette


class SystemThemeWatcher:
    def __init__(self, app: QApplication) -> None:
        self.app = app
        self._platform_light_palette = QPalette(app.style().standardPalette())
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
        current = self.app.palette()

        if desired_dark:
            # Do not trust Window alone. Keep a native platform palette only
            # when every important surface role is already coherently dark.
            if force or not palette_has_complete_dark_surfaces(current):
                self.app.setPalette(complete_dark_palette(current))
        else:
            # Restore the platform/style palette when returning to light mode.
            if force or _is_dark(current.color(QPalette.ColorRole.Window)):
                self.app.setPalette(QPalette(self.app.style().standardPalette()))
                self._platform_light_palette = QPalette(self.app.palette())

        self._last_requested = desired_dark


def install_system_theme(app: QApplication) -> SystemThemeWatcher:
    watcher = SystemThemeWatcher(app)
    watcher.start()
    return watcher
