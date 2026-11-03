"""Launch the desktop application."""

import sys

from PySide6.QtWidgets import QApplication

from time_tracker.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Time Tracker")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
