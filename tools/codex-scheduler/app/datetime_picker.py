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
    QSizePolicy,
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
    """Click-first vertical numeric stepper with one consistent column width."""

    WIDTH = 54
    BUTTON_HEIGHT = 26
    VALUE_HEIGHT = 30

    def __init__(self, minimum: int, maximum: int, value: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(self.WIDTH)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self.plus = QToolButton(self)
        self.plus.setText("+")
        self.plus.setToolTip("Increase")
        self.plus.setFixedSize(self.WIDTH, self.BUTTON_HEIGHT)

        self.value = QSpinBox(self)
        self.value.setRange(minimum, maximum)
        self.value.setValue(value)
        self.value.setWrapping(True)
        self.value.setReadOnly(True)
        self.value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.value.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.value.setFixedSize(self.WIDTH, self.VALUE_HEIGHT)

        self.minus = QToolButton(self)
        self.minus.setText("−")
        self.minus.setToolTip("Decrease")
        self.minus.setFixedSize(self.WIDTH, self.BUTTON_HEIGHT)

        self.plus.clicked.connect(self.value.stepUp)
        self.minus.clicked.connect(self.value.stepDown)
        layout.addWidget(self.plus)
        layout.addWidget(self.value)
        layout.addWidget(self.minus)


class ScheduleTimeDialog(QDialog):
    """Compact native-widget date/time chooser."""

    LABEL_WIDTH = 42

    def __init__(self, initial: QDateTime, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Choose run time")
        self.setModal(True)
        self.setMinimumWidth(350)
        if not initial.isValid() or initial <= QDateTime.currentDateTime():
            initial = default_run_time()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(9)

        date_row = QHBoxLayout()
        date_row.setSpacing(8)
        date_label = QLabel("Date", self)
        date_label.setFixedWidth(self.LABEL_WIDTH)
        date_row.addWidget(date_label)
        self.date = QDateEdit(initial.date(), self)
        self.date.setLocale(QLocale.system())
        self.date.setCalendarPopup(True)
        self.date.setMinimumDate(QDateTime.currentDateTime().date())
        self.date.setDisplayFormat(QLocale.system().dateFormat(QLocale.FormatType.ShortFormat))
        self.date.setMinimumHeight(30)
        calendar = self.date.calendarWidget()
        if calendar is not None:
            calendar.setLocale(QLocale.system())
            calendar.setFirstDayOfWeek(Qt.DayOfWeek.Monday)
        date_row.addWidget(self.date, 1)
        outer.addLayout(date_row)

        quick = QHBoxLayout()
        quick.setSpacing(6)
        today = QPushButton("Today", self)
        tomorrow = QPushButton("Tomorrow", self)
        reset = QPushButton("Now + 5:02", self)
        for button in (today, tomorrow, reset):
            button.setMinimumHeight(30)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        today.clicked.connect(lambda: self.date.setDate(QDateTime.currentDateTime().date()))
        tomorrow.clicked.connect(lambda: self.date.setDate(QDateTime.currentDateTime().date().addDays(1)))
        reset.clicked.connect(self.use_reset_time)
        quick.addWidget(today, 1)
        quick.addWidget(tomorrow, 1)
        quick.addWidget(reset, 1)
        outer.addLayout(quick)

        time_row = QHBoxLayout()
        time_row.setSpacing(8)
        time_label = QLabel("Time", self)
        time_label.setFixedWidth(self.LABEL_WIDTH)
        time_row.addWidget(time_label)
        time_row.addStretch(1)
        self.hours = NumberStepper(0, 23, initial.time().hour(), self)
        colon = QLabel(":", self)
        colon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        colon.setFixedWidth(12)
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
