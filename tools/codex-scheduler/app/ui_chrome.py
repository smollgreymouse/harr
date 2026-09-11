#!/usr/bin/env python3
from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QMouseEvent, QPainter, QPaintEvent, QPalette
from PyQt6.QtWidgets import QApplication, QTabBar, QToolButton, QWidget


# Keep this deliberately small. Standard widgets are drawn by the current
# platform QStyle (GTK platform theme on GNOME when available). The stylesheet
# only supplies structural chrome that has no native desktop equivalent.
APP_QSS = r"""
QWidget#sidebar {
    border-right: 1px solid palette(mid);
}
QPushButton#newTaskButton {
    text-align: left;
}
QLabel#emptyHint, QLabel#sidebarStatus {
    color: palette(mid);
}
QLabel#taskStatus {
    padding: 2px 4px;
}
QFrame#messageBubble {
    border-radius: 7px;
}
QTabWidget::pane {
    border: 0;
}
QTabBar::tab {
    padding-left: 7px;
    padding-right: 5px;
}
QToolButton[chromeRole="tabClose"] {
    min-width: 18px;
    max-width: 18px;
    min-height: 18px;
    max-height: 18px;
    padding: 0;
    border: 0;
    font-size: 15px;
}
QToolButton[chromeRole="tabClose"]:hover {
    border-radius: 4px;
    background: palette(alternate-base);
}
"""


def install_app_chrome(app: QApplication) -> None:
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
    """Adds a compact + hit target immediately after the last real tab."""

    plusClicked = pyqtSignal()
    PLUS_WIDTH = 28

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setExpanding(False)
        self.setDrawBase(False)
        self.setDocumentMode(True)
        self.setMouseTracking(True)

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
            painter.drawRoundedRect(rect, 4, 4)
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
