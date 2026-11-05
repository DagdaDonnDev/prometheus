"""
Layout helpers shared by every window, so desktop and phone stay one app.
"""

from PySide6.QtCore import Qt

from core.platform_info import PHONE_LAYOUT


def size_dialog(dialog, min_w: int, min_h: int, w: int, h: int):
    """
    Desktop: give the dialog its usual minimum and starting size.
    Phone:   no minimum (it would be wider than the screen) — open it full screen.
    """
    if PHONE_LAYOUT:
        dialog.setWindowState(dialog.windowState() | Qt.WindowMaximized)
    else:
        dialog.setMinimumSize(min_w, min_h)
        dialog.resize(w, h)
