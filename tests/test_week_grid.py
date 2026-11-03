"""Phase 1 geometry and scrolling checks for the in-memory grid."""

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QWheelEvent
from PySide6.QtWidgets import QApplication

from time_tracker.ui.main_window import MainWindow


def grabbed_color(pixmap, x: int, y: int) -> QColor:
    """Sample a grabbed widget using logical widget coordinates."""
    scale = pixmap.devicePixelRatio()
    return pixmap.toImage().pixelColor(int((x + 0.5) * scale), int((y + 0.5) * scale))


@pytest.mark.parametrize("size", [(1100, 720), (650, 460), (1300, 800)])
def test_headers_follow_grid_columns_after_resize(qtbot, size):
    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(*size)
    window.show()
    QApplication.processEvents()

    edges = window.grid.column_edges()
    assert len(window.day_labels) == 7
    assert [(label.x(), label.width()) for label in window.day_labels] == [
        (edges[index], edges[index + 1] - edges[index]) for index in range(7)
    ]
    assert window.grid.verticalScrollBar().maximum() > 0


def test_minute_proportional_blocks_and_hour_labels(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    QApplication.processEvents()
    grid = window.grid
    minute_block = next(block for block in grid.blocks if block.description == "One minute")
    multi_hour_block = next(block for block in grid.blocks if block.description == "Sample Exercise")

    assert grid.block_rect(minute_block).height() == pytest.approx(grid.hour_height / 60)
    assert grid.block_rect(multi_hour_block).height() == pytest.approx(1.5 * grid.hour_height)

    grid.verticalScrollBar().setValue(12 * grid.hour_height)
    QApplication.processEvents()
    rect = grid.block_rect(minute_block)
    x = int(rect.center().x())
    y = int(rect.top() - grid.verticalScrollBar().value())
    assert grabbed_color(grid.viewport().grab(), x, y) == QColor("#c9dce9")

    grid.verticalScrollBar().setValue(0)
    QApplication.processEvents()
    top = grid.viewport().grab()
    assert any(
        grabbed_color(top, x, y) != QColor("#f8f9fa")
        for x in range(4, grid.gutter_width - 8)
        for y in range(3, 23)
    )
    grid.verticalScrollBar().setValue(grid.verticalScrollBar().maximum())
    QApplication.processEvents()
    bottom = grid.viewport().grab()
    viewport_height = grid.viewport().height()
    assert any(
        grabbed_color(bottom, x, y) != QColor("#f8f9fa")
        for x in range(4, grid.gutter_width - 8)
        for y in range(viewport_height - grid.hour_height, viewport_height)
    )


@pytest.mark.parametrize("pixel_delta,angle_delta", [(QPoint(0, 0), QPoint(0, -120)), (QPoint(0, -40), QPoint(0, 0))])
def test_wheel_and_touchpad_scroll_keep_headers_fixed(qtbot, pixel_delta, angle_delta):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    QApplication.processEvents()
    grid = window.grid
    scrollbar = grid.verticalScrollBar()
    scrollbar.setValue(0)
    header_y = window.header.y()
    wheel = QWheelEvent(
        QPointF(100, 100), QPointF(100, 100), pixel_delta, angle_delta,
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.ScrollUpdate, False,
    )
    QApplication.sendEvent(grid.viewport(), wheel)
    QApplication.processEvents()

    assert scrollbar.value() > 0
    assert window.header.y() == header_y
