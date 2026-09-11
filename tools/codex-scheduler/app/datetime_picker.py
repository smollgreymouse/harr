#!/usr/bin/env python3
from __future__ import annotations

from PyQt6.QtCore import QDateTime, QLocale, Qt, QTime
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QCalendarWidget,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

RESET_OFFSET_SECONDS = 5 * 60 * 60 + 2 * 60


def default_run_time() -> QDateTime:
    """Default to now + 05:02, rounded up to at(1)'s minute precision."""
    target = QDateTime.currentDateTime().addSecs(RESET_OFFSET_SECONDS)
    seconds = target.time().second()
    if seconds or target.time().msec():
        target = target.addSecs(60 - seconds)
    target.setTime(QTime(target.time().hour(), target.time().minute()))
    return target


class ScheduleTimeDialog(QDialog):
    """Native-widget date/time chooser.

    No custom clock face is painted here: QCalendarWidget and QTimeEdit are
    deliberately left to the active platform QStyle so GNOME/GTK integration
    can control their look, arrows, focus rings and dark theme.
    """

    def __init__(self, initial: QDateTime, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Choose run time")
        self.setModal(True)
        if not initial.isValid() or initial <= QDateTime.currentDateTime():
            initial = default_run_time()

        outer = QVBoxLayout(self)
        chooser = QHBoxLayout()

        self.calendar = QCalendarWidget(self)
        self.calendar.setLocale(QLocale.system())
        self.calendar.setFirstDayOfWeek(Qt.DayOfWeek.Monday)
        self.calendar.setMinimumDate(QDateTime.currentDateTime().date())
        self.calendar.setSelectedDate(initial.date())
        self.calendar.setGridVisible(False)
        chooser.addWidget(self.calendar, 3)

        time_side = QVBoxLayout()
        time_side.addWidget(QLabel("Time"))
        self.time = QTimeEdit(initial.time(), self)
        self.time.setDisplayFormat("HH:mm")
        self.time.setKeyboardTracking(False)
        self.time.setAccelerated(True)
        self.time.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.UpDownArrows)
        self.time.setMinimumWidth(120)
        time_side.addWidget(self.time)

        reset = QPushButton("Now + 5:02", self)
        reset.setToolTip("Use the next Codex five-hour reset window")
        reset.clicked.connect(self.use_reset_time)
        time_side.addWidget(reset)
        time_side.addStretch(1)
        chooser.addLayout(time_side, 1)
        outer.addLayout(chooser)

        self.summary = QLabel(self)
        self.summary.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self.summary)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        outer.addWidget(self.buttons)

        self.calendar.selectionChanged.connect(self.refresh_summary)
        self.time.timeChanged.connect(self.refresh_summary)
        self.refresh_summary()

    def selected_date_time(self) -> QDateTime:
        return QDateTime(self.calendar.selectedDate(), self.time.time())

    def use_reset_time(self) -> None:
        target = default_run_time()
        self.calendar.setSelectedDate(target.date())
        self.time.setTime(target.time())
        self.refresh_summary()

    def refresh_summary(self) -> None:
        selected = self.selected_date_time()
        if selected > QDateTime.currentDateTime():
            seconds = QDateTime.currentDateTime().secsTo(selected)
            hours, remainder = divmod(max(0, seconds), 3600)
            minutes = remainder // 60
            self.summary.setText(f"{selected.toString('dd.MM.yyyy HH:mm')}  ·  in {hours}h {minutes:02d}m")
            self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True)
        else:
            self.summary.setText("Choose a future date and time")
            self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)

    def accept(self) -> None:
        selected = self.selected_date_time()
        if not selected.isValid() or selected <= QDateTime.currentDateTime():
            QMessageBox.warning(self, "Harr Codex Scheduler", "Run time must be in the future.")
            return
        super().accept()
