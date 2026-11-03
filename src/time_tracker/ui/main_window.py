"""Main window and week controls for the dashboard prototype."""

from datetime import date, timedelta

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMainWindow, QPushButton, QVBoxLayout, QWidget

from time_tracker.ui.week_grid import WeekGrid


def sunday_of(day: date) -> date:
    return day - timedelta(days=(day.weekday() + 1) % 7)


class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Time Tracker")
        self.resize(1100, 720)
        self.week_start = sunday_of(date.today())

        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        toolbar = QHBoxLayout()
        self.previous_button = QPushButton("Previous week")
        self.today_button = QPushButton("Today")
        self.next_button = QPushButton("Next week")
        self.week_label = QLabel()
        toolbar.addWidget(self.previous_button)
        toolbar.addWidget(self.today_button)
        toolbar.addWidget(self.next_button)
        toolbar.addStretch()
        toolbar.addWidget(self.week_label)
        layout.addLayout(toolbar)

        self.header = QWidget(central)
        self.header.setFixedHeight(32)
        self.day_labels = [QLabel(self.header) for _ in range(7)]
        for label in self.day_labels:
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.header)

        self.grid = WeekGrid(central)
        layout.addWidget(self.grid, 1)
        self.grid.viewport_resized.connect(self._align_day_labels)
        self.setCentralWidget(central)

        self.previous_button.clicked.connect(lambda: self._change_week(-7))
        self.next_button.clicked.connect(lambda: self._change_week(7))
        self.today_button.clicked.connect(self._show_today)
        self._refresh_headers()

    def _align_day_labels(self) -> None:
        edges = self.grid.column_edges()
        for index, label in enumerate(self.day_labels):
            label.setGeometry(edges[index], 0, edges[index + 1] - edges[index], self.header.height())

    def _change_week(self, days: int) -> None:
        self.week_start += timedelta(days=days)
        self._refresh_headers()

    def _show_today(self) -> None:
        self.week_start = sunday_of(date.today())
        self._refresh_headers()

    def _refresh_headers(self) -> None:
        self.week_label.setText(f"Week of {self.week_start:%B %d, %Y}")
        for index, label in enumerate(self.day_labels):
            day = self.week_start + timedelta(days=index)
            label.setText(day.strftime("%a %d"))
