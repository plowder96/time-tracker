"""Scrollable, in-memory dashboard prototype."""

from dataclasses import dataclass

from PySide6.QtCore import QEvent, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QAbstractScrollArea


@dataclass(frozen=True)
class DemoBlock:
    weekday: int
    start_minute: int
    end_minute: int
    description: str


class WeekGrid(QAbstractScrollArea):
    """Draw a seven-day, 24-hour grid without storage or editing behavior."""

    viewport_resized = Signal()

    gutter_width = 64
    hour_height = 64
    hours_per_day = 24

    def __init__(self, parent=None):
        super().__init__(parent)
        self.blocks = [
            DemoBlock(1, 9 * 60, 10 * 60, "Sample block"),
            DemoBlock(0, 14 * 60, 14 * 60 + 30, "Sample half block"),
            DemoBlock(4, 20 * 60, 21 * 60 + 30, "Sample Exercise"),
            DemoBlock(2, 12 * 60 + 15, 12 * 60 + 16, "One minute"),
        ]
        self.setMinimumSize(420, 320)
        self.setFrameShape(QAbstractScrollArea.Shape.NoFrame)
        self.viewport().installEventFilter(self)
        self.verticalScrollBar().valueChanged.connect(self.viewport().update)
        self._update_scroll_range()
        self.verticalScrollBar().setValue(8 * self.hour_height)

    def column_edges(self) -> list[int]:
        width = max(0, self.viewport().width() - self.gutter_width)
        return [self.gutter_width + width * index // 7 for index in range(8)]

    def block_rect(self, block: DemoBlock) -> QRectF:
        """Return block bounds in unscrolled content coordinates."""
        edges = self.column_edges()
        left, right = edges[block.weekday], edges[block.weekday + 1]
        top = block.start_minute * self.hour_height / 60
        bottom = block.end_minute * self.hour_height / 60
        return QRectF(left + 2, top, max(0, right - left - 4), bottom - top)

    def _update_scroll_range(self) -> None:
        scrollbar = self.verticalScrollBar()
        scrollbar.setRange(0, max(0, self.hours_per_day * self.hour_height - self.viewport().height()))
        scrollbar.setPageStep(self.viewport().height())
        scrollbar.setSingleStep(self.hour_height)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_scroll_range()

    def eventFilter(self, watched, event) -> bool:
        if watched is self.viewport() and event.type() == QEvent.Type.Resize:
            self.viewport_resized.emit()
        return super().eventFilter(watched, event)

    def wheelEvent(self, event) -> None:
        # Touchpads can send pixel deltas without angle deltas. Qt's default
        # scroll-area handler does not move the scrollbar for those events.
        pixel_y = event.pixelDelta().y()
        if pixel_y:
            scrollbar = self.verticalScrollBar()
            scrollbar.setValue(scrollbar.value() - pixel_y)
            event.accept()
        else:
            super().wheelEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self.viewport())
        painter.fillRect(self.viewport().rect(), QColor("#f8f9fa"))
        painter.translate(0, -self.verticalScrollBar().value())

        content_height = self.hours_per_day * self.hour_height
        edges = self.column_edges()
        painter.setPen(QPen(QColor("#d8dde2")))
        for x in edges:
            painter.drawLine(x, 0, x, content_height)
        for hour in range(self.hours_per_day + 1):
            y = hour * self.hour_height
            painter.drawLine(self.gutter_width, y, self.viewport().width(), y)
            if hour < self.hours_per_day:
                painter.setPen(QColor("#505a64"))
                painter.drawText(
                    QRect(4, y + 3, self.gutter_width - 12, 20),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    f"{hour:02d}:00",
                )
                painter.setPen(QPen(QColor("#d8dde2")))

        for block in self.blocks:
            rect = self.block_rect(block)
            painter.fillRect(rect, QColor("#c9dce9"))
            if rect.height() >= 4:
                painter.setPen(QPen(QColor("#26415a")))
                painter.drawRect(rect.adjusted(0.5, 0.5, -0.5, -0.5))
            if rect.height() >= painter.fontMetrics().height() + 4:
                painter.setPen(QColor("#26415a"))
                painter.drawText(
                    rect.adjusted(5, 2, -5, -2),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                    block.description,
                )
