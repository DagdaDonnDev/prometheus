"""
PROMETHEUS - Offline AI Survival Companion
Entry point
"""

import sys
import os

# Ensure we're running from project root
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QFontDatabase, QFont

from ui.main_window import MainWindow
from core.config import Config


def main():
    # High DPI support
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("Prometheus")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("Prometheus")

    # Load config
    config = Config()

    # Apply global stylesheet
    app.setStyleSheet(load_stylesheet())

    # Create and show main window
    window = MainWindow(config)
    window.show()

    sys.exit(app.exec())


def load_stylesheet():
    style_path = os.path.join("ui", "style.qss")
    if os.path.exists(style_path):
        with open(style_path, "r") as f:
            return f.read()
    return ""


if __name__ == "__main__":
    main()
