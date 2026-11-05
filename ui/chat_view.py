"""
Chat view - displays conversation messages.
Supports streaming token append and image display.
"""

from pathlib import Path
from typing import List

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QLabel,
    QFrame, QHBoxLayout, QSizePolicy, QPushButton,
    QDialog
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QPixmap

from core.tabs import Tab
from PySide6.QtCore import Signal
from core.platform_info import PHONE_LAYOUT


class ImagePanel(QFrame):
    """
    Collapsible panel showing page images retrieved alongside an answer.
    Used for plant, medical, and diagram results.
    """

    def __init__(self, image_paths: List[str], parent=None):
        super().__init__(parent)
        self.setObjectName("imagePanel")
        self._visible = False
        self._image_paths = image_paths

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setSpacing(6)

        # Toggle button
        self._toggle = QPushButton(f"📷 Show source illustrations ({len(image_paths)} page{'s' if len(image_paths) > 1 else ''})")
        self._toggle.setObjectName("summaryBar")
        self._toggle.setFixedHeight(26)
        self._toggle.clicked.connect(self._toggle_images)
        layout.addWidget(self._toggle)

        # Image container (hidden by default)
        self._container = QWidget()
        self._container.hide()
        self._container_layout = QHBoxLayout(self._container)
        self._container_layout.setContentsMargins(0, 0, 0, 0)
        self._container_layout.setSpacing(8)
        self._container_layout.setAlignment(Qt.AlignLeft)

        self._images_loaded = False
        layout.addWidget(self._container)

    def _toggle_images(self):
        self._visible = not self._visible
        if self._visible:
            if not self._images_loaded:
                self._load_images()
            self._container.show()
            self._toggle.setText(f"📷 Hide source illustrations")
        else:
            self._container.hide()
            self._toggle.setText(
                f"📷 Show source illustrations ({len(self._image_paths)} page{'s' if len(self._image_paths) > 1 else ''})"
            )

    def _load_images(self):
        """Load and display images (deferred until first shown)."""
        for img_path in self._image_paths[:3]:  # max 3 images
            if not Path(img_path).exists():
                continue

            pixmap = QPixmap(img_path)
            if pixmap.isNull():
                continue

            # Scale to fit — max 240px wide in panel
            pixmap = pixmap.scaledToWidth(240, Qt.SmoothTransformation)

            lbl = QLabel()
            lbl.setPixmap(pixmap)
            lbl.setFixedSize(240, pixmap.height())
            lbl.setCursor(Qt.PointingHandCursor)
            lbl.setToolTip("Click to view full size")

            # Click to open full size
            path_copy = img_path
            lbl.mousePressEvent = lambda e, p=path_copy: self._open_fullsize(p)

            self._container_layout.addWidget(lbl)

        self._images_loaded = True

    def _open_fullsize(self, img_path: str):
        """Open image at full resolution in a dialog."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Source illustration")

        pixmap = QPixmap(img_path)
        if pixmap.isNull():
            return

        # Scale to screen — max 900px wide
        if pixmap.width() > 900:
            pixmap = pixmap.scaledToWidth(900, Qt.SmoothTransformation)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(8, 8, 8, 8)

        img_lbl = QLabel()
        img_lbl.setPixmap(pixmap)
        img_lbl.setFixedSize(pixmap.width(), pixmap.height())
        layout.addWidget(img_lbl)

        dialog.setFixedSize(pixmap.width() + 16, pixmap.height() + 16)
        dialog.exec()


class MessageBubble(QFrame):
    def __init__(self, role: str, content: str = "", parent=None):
        super().__init__(parent)
        self.role = role
        self.setObjectName(f"bubble_{role}")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)

        self._label = QLabel(content)
        self._label.setWordWrap(True)
        self._label.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
        )
        self._label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        font = self._label.font()
        font.setPointSize(13)
        self._label.setFont(font)

        if role == "user":
            layout.addStretch()
            layout.addWidget(self._label)
        else:
            if not PHONE_LAYOUT:   # phone: no icon column, every pixel goes to text
                icon = QLabel("⚡")
                icon.setObjectName("bubbleIcon")
                icon.setFixedWidth(24)
                icon.setAlignment(Qt.AlignTop)
                layout.addWidget(icon)
            layout.addWidget(self._label)
            layout.addStretch()

    def append_text(self, text: str):
        current = self._label.text()
        self._label.setText(current + text)

    def set_text(self, text: str):
        self._label.setText(text)

    def get_text(self) -> str:
        return self._label.text()


class ChatView(QWidget):
    suggestion_clicked   = Signal(str)   # a "try asking" question was tapped
    assessment_requested = Signal()      # the situation-check card was tapped

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_bubble: MessageBubble = None
        self._welcome = None
        # Set by the window: returns True while the situation check hasn't been done
        self.check_pending = lambda: False
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._tab_info = QLabel("")
        self._tab_info.setObjectName("tabInfo")
        self._tab_info.setAlignment(Qt.AlignCenter)
        self._tab_info.setFixedHeight(30)
        self._tab_info.hide()   # the tab bar already shows which tab is open
        layout.addWidget(self._tab_info)

        self._summary_bar = QPushButton("📋 View conversation summary")
        self._summary_bar.setObjectName("summaryBar")
        self._summary_bar.setFixedHeight(28)
        self._summary_bar.hide()
        self._summary_bar.clicked.connect(self._show_summary)
        layout.addWidget(self._summary_bar)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setObjectName("chatScroll")
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._messages_widget = QWidget()
        self._messages_widget.setObjectName("messagesWidget")
        self._messages_layout = QVBoxLayout(self._messages_widget)
        self._messages_layout.setContentsMargins(8, 8, 8, 8)
        self._messages_layout.setSpacing(8)
        self._messages_layout.addStretch()

        self._scroll.setWidget(self._messages_widget)
        layout.addWidget(self._scroll)

        self._current_tab: Tab = None

    def load_tab(self, tab: Tab):
        """Load all messages from a tab."""
        self._current_tab = tab
        self._tab_info.setText(f"{tab.icon}  {tab.name}")

        if tab.summary:
            self._summary_bar.show()
        else:
            self._summary_bar.hide()

        self._clear_messages()

        for msg in tab.history:
            bubble = MessageBubble(msg["role"], msg["content"])
            self._messages_layout.insertWidget(
                self._messages_layout.count() - 1, bubble
            )

        # Empty tab → welcome panel. The situation check is only offered in
        # Survival, so someone who just wants to chat isn't pushed into it.
        if not tab.history:
            from ui.welcome import WelcomePanel
            self._welcome = WelcomePanel(
                tab, show_check=(tab.id == "survival" and self.check_pending())
            )
            self._welcome.suggestion_clicked.connect(self.suggestion_clicked)
            self._welcome.assessment_requested.connect(self.assessment_requested)
            self._messages_layout.insertWidget(0, self._welcome)

        QTimer.singleShot(50, self._scroll_to_bottom)

    def _hide_welcome(self):
        """The first message replaces the welcome panel."""
        if self._welcome is not None:
            self._welcome.deleteLater()
            self._welcome = None

    def _clear_messages(self):
        self._welcome = None
        layout = self._messages_layout
        while layout.count() > 1:
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def add_message(self, role: str, content: str):
        self._hide_welcome()
        bubble = MessageBubble(role, content)
        self._messages_layout.insertWidget(
            self._messages_layout.count() - 1, bubble
        )
        QTimer.singleShot(50, self._scroll_to_bottom)

    def start_assistant_message(self):
        self._hide_welcome()
        self._current_bubble = MessageBubble("assistant", "")
        self._messages_layout.insertWidget(
            self._messages_layout.count() - 1, self._current_bubble
        )
        QTimer.singleShot(50, self._scroll_to_bottom)

    def append_token(self, token: str):
        if self._current_bubble:
            self._current_bubble.append_text(token)
            self._scroll_to_bottom()

    def finish_assistant_message(self, image_paths: List[str] = None,
                                 first_token_ms: int = 0, response_ms: int = 0):
        """
        Mark current streaming message as complete.
        If image_paths provided, attach an image panel below the bubble.
        If timing is given, add a small stamp: speak-start first, full time second.
        """
        self._current_bubble = None

        if first_token_ms:
            stamp_text = f"↳ 🔊 {first_token_ms}ms"
            if response_ms and response_ms != first_token_ms:
                stamp_text += f"   ✓ {response_ms}ms"
            stamp = QLabel(stamp_text)
            stamp.setObjectName("timingStamp")
            stamp.setContentsMargins(40, 0, 0, 0)
            stamp.setToolTip("🔊 when you started hearing the reply · ✓ when it finished")
            self._messages_layout.insertWidget(
                self._messages_layout.count() - 1, stamp
            )
        if self._current_tab and self._current_tab.summary:
            self._summary_bar.show()

        # Add image panel if we have images
        if image_paths:
            panel = ImagePanel(image_paths)
            self._messages_layout.insertWidget(
                self._messages_layout.count() - 1, panel
            )
            QTimer.singleShot(50, self._scroll_to_bottom)

    def add_verdict_bar(self, options: dict, on_choice):
        """
        Row of buttons under a derivation asking whether it was right.
        options: {verdict_key: button label}. on_choice(verdict_key) is called
        once, then the row replaces itself with a short note.
        """
        from PySide6.QtWidgets import QGridLayout

        bar = QFrame()
        bar.setObjectName("verdictBar")
        outer = QVBoxLayout(bar)
        outer.setContentsMargins(8 if PHONE_LAYOUT else 40, 2, 8, 2)
        outer.setSpacing(4)

        # Desktop: one row. Phone: question on top, buttons in a 2×2 grid
        # (a single row is wider than a phone screen).
        grid = QGridLayout()
        grid.setSpacing(6)
        prompt = QLabel("Was this right?")
        prompt.setObjectName("infoLabel")
        if PHONE_LAYOUT:
            outer.addWidget(prompt)
        else:
            grid.addWidget(prompt, 0, 0)
        outer.addLayout(grid)

        buttons = []

        def choose(key):
            for w in buttons + [prompt]:
                w.deleteLater()
            done = QLabel(f"Marked: {options[key]}")
            done.setObjectName("infoLabel")
            outer.addWidget(done)
            on_choice(key)

        for i, (key, label) in enumerate(options.items()):
            btn = QPushButton(label)
            btn.setObjectName("navBtn")
            btn.setFixedHeight(26)
            btn.clicked.connect(lambda _=False, k=key: choose(k))
            buttons.append(btn)
            if PHONE_LAYOUT:
                grid.addWidget(btn, i // 2, i % 2)
            else:
                grid.addWidget(btn, 0, i + 1)
        if not PHONE_LAYOUT:
            grid.setColumnStretch(len(options) + 1, 1)

        self._messages_layout.insertWidget(self._messages_layout.count() - 1, bar)
        QTimer.singleShot(50, self._scroll_to_bottom)

    def add_note(self, text: str):
        """Small neutral note between messages (e.g. why a derivation fell back)."""
        note = QLabel(text)
        note.setObjectName("timingStamp")
        note.setWordWrap(True)
        note.setContentsMargins(40, 2, 8, 2)
        self._messages_layout.insertWidget(self._messages_layout.count() - 1, note)
        QTimer.singleShot(50, self._scroll_to_bottom)

    def add_error(self, error: str):
        bubble = MessageBubble("assistant", f"⚠ {error}")
        self._messages_layout.insertWidget(
            self._messages_layout.count() - 1, bubble
        )
        self._scroll_to_bottom()

    def _scroll_to_bottom(self):
        scrollbar = self._scroll.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _show_summary(self):
        if self._current_tab and self._current_tab.summary:
            from PySide6.QtWidgets import QMessageBox
            msg = QMessageBox(self)
            msg.setWindowTitle(f"{self._current_tab.name} — Conversation Summary")
            msg.setText(self._current_tab.summary)
            msg.exec()
