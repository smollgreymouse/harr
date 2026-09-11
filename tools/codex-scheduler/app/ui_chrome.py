#!/usr/bin/env python3
from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QResizeEvent
from PyQt6.QtWidgets import QApplication, QStyle, QTabBar, QToolButton, QWidget


# Standard widgets keep the active platform QStyle.  QSS is intentionally
# limited to application structure and the few "flat" controls that make up
# the OpenCode-like chrome.
APP_QSS = r"""
QWidget#sidebar {
    border-right: 1px solid palette(mid);
}
QPushButton#newTaskButton {
    text-align: left;
    border: 1px solid transparent;
    background: transparent;
}
QPushButton#newTaskButton:hover {
    background: palette(alternate-base);
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
QComboBox[chromeRole="selector"] {
    border: 1px solid transparent;
    background: transparent;
    padding: 4px 24px 4px 7px;
}
QComboBox[chromeRole="selector"]:hover {
    border: 1px solid palette(mid);
    background: palette(alternate-base);
}
QComboBox[chromeRole="selector"]:focus {
    border: 1px solid palette(highlight);
}
QToolButton[chromeRole="tabClose"],
QToolButton[chromeRole="tabPlus"],
QToolButton[chromeRole="sidebarToggle"] {
    border: 1px solid transparent;
    background: transparent;
    padding: 2px;
}
QToolButton[chromeRole="tabClose"]:hover,
QToolButton[chromeRole="tabPlus"]:hover,
QToolButton[chromeRole="sidebarToggle"]:hover {
    border: 1px solid palette(mid);
    background: palette(alternate-base);
}
"""


def install_app_chrome(app: QApplication) -> None:
    app.setStyleSheet(APP_QSS)


class TabCloseButton(QToolButton):
    """Small close button using the current platform's standard close icon."""

    def __init__(self, on_click: Callable[[], None], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("chromeRole", "tabClose")
        self.setAutoRaise(True)
        self.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarCloseButton))
        self.setIconSize(QSize(12, 12))
        self.setFixedSize(20, 20)
        self.setToolTip("Close tab")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(on_click)


class PlusTabBar(QTabBar):
    """System QToolButton placed immediately after the last real tab."""

    plusClicked = pyqtSignal()
    PLUS_WIDTH = 28

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setExpanding(False)
        self.setDrawBase(False)
        self.setDocumentMode(True)

        self.plus_button = QToolButton(self)
        self.plus_button.setProperty("chromeRole", "tabPlus")
        self.plus_button.setAutoRaise(True)
        self.plus_button.setText("+")
        self.plus_button.setToolTip("New task")
        self.plus_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.plus_button.clicked.connect(self.plusClicked.emit)
        QTimer.singleShot(0, self._position_plus)

    def _position_plus(self) -> None:
        if self.count():
            last = self.tabRect(self.count() - 1)
            left = last.right() + 4
        else:
            left = 2
        height = max(22, min(28, self.height() - 2))
        top = max(0, (self.height() - height) // 2)
        self.plus_button.setGeometry(left, top, self.PLUS_WIDTH, height)
        self.plus_button.raise_()
        self.plus_button.show()

    def sizeHint(self) -> QSize:
        hint = super().sizeHint()
        return QSize(hint.width() + self.PLUS_WIDTH + 6, hint.height())

    def minimumSizeHint(self) -> QSize:
        hint = super().minimumSizeHint()
        return QSize(hint.width() + self.PLUS_WIDTH + 6, hint.height())

    def tabLayoutChange(self) -> None:
        super().tabLayoutChange()
        QTimer.singleShot(0, self._position_plus)

    def tabInserted(self, index: int) -> None:
        super().tabInserted(index)
        QTimer.singleShot(0, self._position_plus)

    def tabRemoved(self, index: int) -> None:
        super().tabRemoved(index)
        QTimer.singleShot(0, self._position_plus)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._position_plus()


def set_tab_close_button(tab_bar: QTabBar, index: int, callback: Callable[[], None]) -> TabCloseButton:
    button = TabCloseButton(callback, tab_bar)
    tab_bar.setTabButton(index, QTabBar.ButtonPosition.RightSide, button)
    return button
