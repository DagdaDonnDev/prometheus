"""
PROMETHEUS - Offline AI Survival Companion
Entry point
"""

import sys
import os

# Ensure we're running from project root
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Offline app: if the search model is already downloaded, never ask Hugging Face
from core.ai.embedder import use_offline_cache_if_present
use_offline_cache_if_present()

# Step 1: check the packages the window needs before importing it, so a
# missing install gives one clear instruction instead of a traceback
_missing = []
for _module, _package in (("PySide6", "PySide6"), ("requests", "requests")):
    try:
        __import__(_module)
    except ImportError:
        _missing.append(_package)
if _missing:
    print(
        "Prometheus can't start — missing Python packages: " + ", ".join(_missing) + "\n\n"
        "Install everything with the same Python you used to run this:\n\n"
        f'    "{sys.executable}" -m pip install -r requirements.txt\n'
    )
    sys.exit(1)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QFontDatabase, QFont

from ui.main_window import MainWindow
from core.app.config import Config


def main():
    # High DPI support
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("Prometheus")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("Prometheus")

    # App icon (assets/icon.png): window, taskbar, Alt+Tab. On Windows the
    # taskbar shows Python's icon unless the app has its own ID.
    if os.path.exists(APP_ICON):
        app.setWindowIcon(QIcon(APP_ICON))
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Prometheus.App")
        except Exception:
            pass

    # Load config
    config = Config.load()      # what was chosen in Settings last time

    # Apply global stylesheet
    app.setStyleSheet(load_stylesheet())

    # Create and show main window
    window = MainWindow(config)
    window.show()

    sys.exit(app.exec())


APP_ICON = os.path.join("assets", "icon.png")


def load_stylesheet():
    style_path = os.path.join("ui", "style.qss")
    if os.path.exists(style_path):
        with open(style_path, "r") as f:
            return f.read()
    return ""


if __name__ == "__main__":
    main()
