#!/usr/bin/env python3
from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QResizeEvent
from PyQt6.QtWidgets import QApplication, QStyle, QTabBar, QToolButton, QWidget


# Keep application styling limited to workspace chrome and geometry. Standard
# input widgets still use the active platform QStyle and application palette.
APP_QSS = r"""
QWidget#sidebar {
    border: 0;
}
QSplitter::handle:horizontal {
    width: 1px;
    margin: 0;
    background: palette(mid);
}

QPushButton#newTaskButton {
    text-align: left;
    border: 1px solid transparent;
    background: transparent;
    min-height: 28px;
    max-height: 28px;
    padding: 0 6px;
}
QPushButton#newTaskButton:hover {
    background: palette(alternate-base);
    border-radius: 4px;
}
QLabel#emptyHint, QLabel#sidebarStatus {
    color: palette(mid);
}
QLabel#taskStatus {
    padding: 0 4px;
}

QTreeWidget {
    border: 0;
    outline: 0;
    background: transparent;
}
QScrollArea {
    border: 0;
    background: transparent;
}
QFrame#messageBubble {
    border-radius: 7px;
}

QTabWidget::pane {
    border: 0;
    top: 0;
}
QTabBar {
    border: 0;
    min-height: 34px;
    max-height: 34px;
}
QTabBar::tab {
    border: 0;
    background: transparent;
    min-height: 28px;
    max-height: 28px;
    margin-top: 3px;
    margin-bottom: 3px;
    padding: 0 6px 0 9px;
}
QTabBar::tab:selected {
    background: palette(alternate-base);
    border-radius: 5px;
}
QTabBar::tab:hover {
    background: palette(alternate-base);
    border-radius: 5px;
}

QComboBox {
    min-height: 28px;
}
QComboBox[chromeRole="selector"] {
    border: 1px solid transparent;
    background: transparent;
    min-width: 108px;
    max-width: 108px;
    min-height: 28px;
    max-height: 28px;
    padding: 0 24px 0 7px;
}
QComboBox[chromeRole="selector"]:hover {
    border: 1px solid palette(mid);
    background: palette(alternate-base);
    border-radius: 4px;
}
QComboBox[chromeRole="selector"]:focus {
    border: 1px solid palette(highlight);
    border-radius: 4px;
}

QLineEdit,
QPushButton {
    min-height: 28px;
}

QToolButton[chromeRole="tabClose"],
QToolButton[chromeRole="tabPlus"],
QToolButton[chromeRole="sidebarToggle"] {
    border: 1px solid transparent;
    background: transparent;
    min-width: 28px;
    max-width: 28px;
    min-height: 28px;
    max-height: 28px;
    padding: 0;
}
QToolButton[chromeRole="tabClose"] {
    min-width: 18px;
    max-width: 18px;
    min-height: 18px;
    max-height: 18px;
}
QToolButton[chromeRole="tabClose"]:hover,
QToolButton[chromeRole="tabPlus"]:hover,
QToolButton[chromeRole="sidebarToggle"]:hover {
    border: 1px solid palette(mid);
    background: palette(alternate-base);
    border-radius: 4px;
}
"""


def install_app_chrome(app: QApplication) -> None:
    app.setStyleSheet(APP_QSS)


class TabCloseButton(QToolButton):
    def __init__(self, on_click: Callable[[], None], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("chromeRole", "tabClose")
        self.setAutoRaise(True)
        self.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarCloseButton))
        self.setIconSize(QSize(10, 10))
        self.setFixedSize(18, 18)
        self.setToolTip("Close tab")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(on_click)


class PlusTabBar(QTabBar):
    plusClicked = pyqtSignal()
    BAR_HEIGHT = 34
    PLUS_WIDTH = 28

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setExpanding(False)
        self.setDrawBase(False)
        self.setDocumentMode(True)
        self.setFixedHeight(self.BAR_HEIGHT)

        self.plus_button = QToolButton(self)
        self.plus_button.setProperty("chromeRole", "tabPlus")
        self.plus_button.setAutoRaise(True)
        self.plus_button.setText("+")
        self.plus_button.setToolTip("New task")
        self.plus_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.plus_button.setFixedSize(self.PLUS_WIDTH, 28)
        self.plus_button.clicked.connect(self.plusClicked.emit)
        QTimer.singleShot(0, self._position_plus)

    def _position_plus(self) -> None:
        if self.count():
            last = self.tabRect(self.count() - 1)
            left = last.right() + 3
        else:
            left = 2
        height = 28
        top = (self.BAR_HEIGHT - height) // 2
        self.plus_button.move(left, top)
        self.plus_button.raise_()
        self.plus_button.show()

    def sizeHint(self) -> QSize:
        hint = super().sizeHint()
        return QSize(hint.width() + self.PLUS_WIDTH + 5, self.BAR_HEIGHT)

    def minimumSizeHint(self) -> QSize:
        hint = super().minimumSizeHint()
        return QSize(hint.width() + self.PLUS_WIDTH + 5, self.BAR_HEIGHT)

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
