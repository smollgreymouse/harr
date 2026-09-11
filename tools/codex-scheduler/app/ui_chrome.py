#!/usr/bin/env python3
from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QPoint, QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QMouseEvent, QPainter, QPaintEvent, QPalette
from PyQt6.QtWidgets import QApplication, QStyle, QTabBar, QToolButton, QWidget


APP_QSS = r"""
/* App-wide chrome. Keep colors palette-driven so system light/dark palettes
   can change underneath this stylesheet without maintaining two themes. */
QWidget {
    font-size: 13px;
}

QMainWindow, QDialog {
    background: palette(window);
}

QToolTip {
    border: 1px solid palette(mid);
    border-radius: 6px;
    padding: 5px 7px;
    background: palette(tool-tip-base);
    color: palette(tool-tip-text);
}

/* OpenCode-like ghost controls: no visible box until hover/focus. */
QComboBox {
    min-height: 26px;
    padding: 3px 24px 3px 7px;
    border: 1px solid transparent;
    border-radius: 6px;
    background: transparent;
}
QComboBox:hover {
    border-color: palette(mid);
    background: palette(alternate-base);
}
QComboBox:focus, QComboBox:on {
    border-color: palette(highlight);
    background: palette(base);
}
QComboBox:disabled {
    color: palette(mid);
    background: transparent;
}
QComboBox::drop-down {
    width: 20px;
    border: 0;
    background: transparent;
}
QComboBox QAbstractItemView {
    border: 1px solid palette(mid);
    border-radius: 7px;
    padding: 4px;
    outline: 0;
    background: palette(base);
    selection-background-color: palette(highlight);
    selection-color: palette(highlighted-text);
}

QLineEdit, QTextEdit {
    border: 1px solid palette(mid);
    border-radius: 7px;
    padding: 6px 8px;
    background: palette(base);
    selection-background-color: palette(highlight);
    selection-color: palette(highlighted-text);
}
QLineEdit:hover, QTextEdit:hover {
    border-color: palette(dark);
}
QLineEdit:focus, QTextEdit:focus {
    border-color: palette(highlight);
}
QLineEdit:read-only {
    background: palette(alternate-base);
}

QPushButton, QToolButton {
    min-height: 26px;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 3px 8px;
    background: transparent;
}
QPushButton:hover, QToolButton:hover {
    border-color: palette(mid);
    background: palette(alternate-base);
}
QPushButton:pressed, QToolButton:pressed,
QPushButton:checked, QToolButton:checked {
    border-color: palette(mid);
    background: palette(base);
}
QPushButton:disabled, QToolButton:disabled {
    color: palette(mid);
    border-color: transparent;
    background: transparent;
}
QPushButton[chromeRole="primary"] {
    border-color: palette(highlight);
    background: palette(highlight);
    color: palette(highlighted-text);
    font-weight: 600;
}
QPushButton[chromeRole="primary"]:hover {
    border-color: palette(highlight);
}
QPushButton[chromeRole="danger"], QToolButton[chromeRole="danger"] {
    color: palette(bright-text);
}
QToolButton[chromeRole="tabClose"] {
    min-width: 18px;
    max-width: 18px;
    min-height: 18px;
    max-height: 18px;
    padding: 0;
    border: 0;
    border-radius: 4px;
    font-size: 15px;
}
QToolButton[chromeRole="tabClose"]:hover {
    border: 0;
    background: palette(alternate-base);
}
QPushButton#newTaskButton {
    text-align: left;
    padding-left: 8px;
}

QMenu {
    border: 1px solid palette(mid);
    border-radius: 7px;
    padding: 5px;
    background: palette(base);
}
QMenu::item {
    border-radius: 5px;
    padding: 6px 24px 6px 9px;
}
QMenu::item:selected {
    background: palette(alternate-base);
}
QMenu::separator {
    height: 1px;
    margin: 4px 7px;
    background: palette(mid);
}

QTabWidget::pane {
    border: 0;
}
QTabBar {
    background: transparent;
}
QTabBar::tab {
    min-height: 27px;
    min-width: 72px;
    padding: 4px 7px;
    margin: 2px 1px 0 1px;
    border: 0;
    border-radius: 6px 6px 0 0;
    background: transparent;
}
QTabBar::tab:hover {
    background: palette(alternate-base);
}
QTabBar::tab:selected {
    background: palette(base);
}

QTreeWidget {
    border: 0;
    outline: 0;
    background: transparent;
}
QTreeWidget::item {
    padding: 5px 4px;
    border-radius: 5px;
}
QTreeWidget::item:hover {
    background: palette(alternate-base);
}
QTreeWidget::item:selected {
    background: palette(highlight);
    color: palette(highlighted-text);
}

QWidget#sidebar {
    border-right: 1px solid palette(mid);
}
QLabel#emptyHint, QLabel#sidebarStatus {
    color: palette(mid);
}
QLabel#taskStatus {
    padding: 3px 6px;
}
QFrame#messageBubble {
    border-radius: 8px;
}

QScrollArea {
    border: 0;
    background: transparent;
}
QScrollBar:vertical {
    width: 10px;
    margin: 0;
    border: 0;
    background: transparent;
}
QScrollBar::handle:vertical {
    min-height: 24px;
    margin: 2px;
    border-radius: 3px;
    background: palette(mid);
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    height: 0;
    background: transparent;
}
QScrollBar:horizontal {
    height: 10px;
    margin: 0;
    border: 0;
    background: transparent;
}
QScrollBar::handle:horizontal {
    min-width: 24px;
    margin: 2px;
    border-radius: 3px;
    background: palette(mid);
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    width: 0;
    background: transparent;
}

QSplitter::handle {
    background: transparent;
}
QSplitter::handle:hover {
    background: palette(mid);
}

QCalendarWidget QToolButton {
    min-height: 25px;
}
"""


def install_app_chrome(app: QApplication) -> None:
    """Install one palette-aware chrome stylesheet for the whole app."""
    app.setStyleSheet(APP_QSS)


class TabCloseButton(QToolButton):
    def __init__(self, on_click: Callable[[], None], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setText("×")
        self.setProperty("chromeRole", "tabClose")
        self.setToolTip("Close tab")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(on_click)


class PlusTabBar(QTabBar):
    """Tab bar that paints a compact + immediately after the last tab."""

    plusClicked = pyqtSignal()
    PLUS_WIDTH = 28

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setExpanding(False)
        self.setDrawBase(False)
        self.setDocumentMode(True)

    def _plus_rect(self) -> QRect:
        if self.count():
            last = self.tabRect(self.count() - 1)
            left = last.right() + 3
        else:
            left = 2
        height = max(24, self.height() - 3)
        return QRect(left, 2, self.PLUS_WIDTH, height)

    def sizeHint(self) -> QSize:
        hint = super().sizeHint()
        return QSize(hint.width() + self.PLUS_WIDTH + 5, hint.height())

    def minimumSizeHint(self) -> QSize:
        hint = super().minimumSizeHint()
        return QSize(hint.width() + self.PLUS_WIDTH + 5, hint.height())

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        rect = self._plus_rect()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if rect.contains(self.mapFromGlobal(self.cursor().pos())):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self.palette().brush(QPalette.ColorRole.AlternateBase))
            painter.drawRoundedRect(rect, 5, 5)
        painter.setPen(self.palette().color(QPalette.ColorRole.Text))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "+")

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._plus_rect().contains(event.position().toPoint()):
            self.plusClicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        self.update(self._plus_rect())
        super().mouseMoveEvent(event)


def set_tab_close_button(tab_bar: QTabBar, index: int, callback: Callable[[], None]) -> TabCloseButton:
    button = TabCloseButton(callback, tab_bar)
    tab_bar.setTabButton(index, QTabBar.ButtonPosition.RightSide, button)
    return button
