#!/usr/bin/env python3
from __future__ import annotations

from PyQt6.QtCore import QDateTime, QLocale, Qt, QTime
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QToolButton,
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


class NumberStepper(QWidget):
    """Click-first numeric stepper built only from standard Qt widgets."""

    def __init__(self, minimum: int, maximum: int, value: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self.plus = QToolButton(self)
        self.plus.setText("+")
        self.plus.setToolTip("Increase")
        self.value = QSpinBox(self)
        self.value.setRange(minimum, maximum)
        self.value.setValue(value)
        self.value.setWrapping(True)
        self.value.setReadOnly(True)
        self.value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.value.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.value.setMinimumWidth(58)
        self.minus = QToolButton(self)
        self.minus.setText("−")
        self.minus.setToolTip("Decrease")

        self.plus.clicked.connect(self.value.stepUp)
        self.minus.clicked.connect(self.value.stepDown)
        layout.addWidget(self.plus)
        layout.addWidget(self.value)
        layout.addWidget(self.minus)


class ScheduleTimeDialog(QDialog):
    """Compact native-widget date/time chooser.

    The calendar is a standard QDateEdit popup rather than an always-visible
    calendar.  Hours/minutes use QSpinBox plus system QToolButtons, so the
    frequent operation is click-first without a custom-painted clock widget.
    """

    def __init__(self, initial: QDateTime, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Choose run time")
        self.setModal(True)
        if not initial.isValid() or initial <= QDateTime.currentDateTime():
            initial = default_run_time()

        outer = QVBoxLayout(self)
        outer.setSpacing(10)

        date_row = QHBoxLayout()
        date_row.addWidget(QLabel("Date"))
        self.date = QDateEdit(initial.date(), self)
        self.date.setLocale(QLocale.system())
        self.date.setCalendarPopup(True)
        self.date.setMinimumDate(QDateTime.currentDateTime().date())
        self.date.setDisplayFormat(QLocale.system().dateFormat(QLocale.FormatType.ShortFormat))
        calendar = self.date.calendarWidget()
        if calendar is not None:
            calendar.setLocale(QLocale.system())
            # Match the user's expected RU/EU week layout even on a machine
            # whose locale is temporarily different.
            calendar.setFirstDayOfWeek(Qt.DayOfWeek.Monday)
        date_row.addWidget(self.date, 1)
        outer.addLayout(date_row)

        quick = QHBoxLayout()
        today = QPushButton("Today", self)
        tomorrow = QPushButton("Tomorrow", self)
        reset = QPushButton("Now + 5:02", self)
        today.clicked.connect(lambda: self.date.setDate(QDateTime.currentDateTime().date()))
        tomorrow.clicked.connect(lambda: self.date.setDate(QDateTime.currentDateTime().date().addDays(1)))
        reset.clicked.connect(self.use_reset_time)
        quick.addWidget(today)
        quick.addWidget(tomorrow)
        quick.addStretch(1)
        quick.addWidget(reset)
        outer.addLayout(quick)

        time_row = QHBoxLayout()
        time_row.addWidget(QLabel("Time"))
        time_row.addStretch(1)
        self.hours = NumberStepper(0, 23, initial.time().hour(), self)
        colon = QLabel(":", self)
        colon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.minutes = NumberStepper(0, 59, initial.time().minute(), self)
        time_row.addWidget(self.hours)
        time_row.addWidget(colon)
        time_row.addWidget(self.minutes)
        time_row.addStretch(1)
        outer.addLayout(time_row)

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

        self.date.dateChanged.connect(self.refresh_summary)
        self.hours.value.valueChanged.connect(self.refresh_summary)
        self.minutes.value.valueChanged.connect(self.refresh_summary)
        self.refresh_summary()

    def selected_date_time(self) -> QDateTime:
        return QDateTime(
            self.date.date(),
            QTime(self.hours.value.value(), self.minutes.value.value()),
        )

    def use_reset_time(self) -> None:
        target = default_run_time()
        self.date.setDate(target.date())
        self.hours.value.setValue(target.time().hour())
        self.minutes.value.setValue(target.time().minute())
        self.refresh_summary()

    def refresh_summary(self) -> None:
        selected = self.selected_date_time()
        ok = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        if selected.isValid() and selected > QDateTime.currentDateTime():
            seconds = QDateTime.currentDateTime().secsTo(selected)
            hours, remainder = divmod(max(0, seconds), 3600)
            minutes = remainder // 60
            self.summary.setText(f"{selected.toString('dd.MM.yyyy HH:mm')}  ·  in {hours}h {minutes:02d}m")
            ok.setEnabled(True)
        else:
            self.summary.setText("Choose a future date and time")
            ok.setEnabled(False)

    def accept(self) -> None:
        selected = self.selected_date_time()
        if not selected.isValid() or selected <= QDateTime.currentDateTime():
            QMessageBox.warning(self, "Harr Codex Scheduler", "Run time must be in the future.")
            return
        super().accept()
