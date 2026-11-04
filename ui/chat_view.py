"""
Chat view - displays conversation messages.
Supports streaming token append.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QLabel,
    QFrame, QHBoxLayout, QSizePolicy, QPushButton
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QTextCursor

from core.tabs import Tab


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
            # Add icon for assistant
            icon = QLabel("⚡")
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
    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_bubble: MessageBubble = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Tab info bar
        self._tab_info = QLabel("")
        self._tab_info.setObjectName("tabInfo")
        self._tab_info.setAlignment(Qt.AlignCenter)
        self._tab_info.setFixedHeight(30)
        layout.addWidget(self._tab_info)

        # Summary bar (shown when tab has a summary)
        self._summary_bar = QPushButton("📋 View conversation summary")
        self._summary_bar.setObjectName("summaryBar")
        self._summary_bar.setFixedHeight(28)
        self._summary_bar.hide()
        self._summary_bar.clicked.connect(self._show_summary)
        layout.addWidget(self._summary_bar)

        # Scroll area for messages
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

        # Update tab info bar
        self._tab_info.setText(f"{tab.icon}  {tab.name}")

        # Update summary bar
        if tab.summary:
            self._summary_bar.show()
        else:
            self._summary_bar.hide()

        # Clear existing messages
        self._clear_messages()

        # Load history
        for msg in tab.history:
            bubble = MessageBubble(msg["role"], msg["content"])
            self._messages_layout.insertWidget(
                self._messages_layout.count() - 1,
                bubble
            )

        # Scroll to bottom
        QTimer.singleShot(50, self._scroll_to_bottom)

    def _clear_messages(self):
        """Remove all message bubbles."""
        layout = self._messages_layout
        while layout.count() > 1:  # Keep the stretch
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def add_message(self, role: str, content: str):
        """Add a complete message."""
        bubble = MessageBubble(role, content)
        self._messages_layout.insertWidget(
            self._messages_layout.count() - 1,
            bubble
        )
        QTimer.singleShot(50, self._scroll_to_bottom)

    def start_assistant_message(self):
        """Begin streaming assistant response."""
        self._current_bubble = MessageBubble("assistant", "")
        self._messages_layout.insertWidget(
            self._messages_layout.count() - 1,
            self._current_bubble
        )
        QTimer.singleShot(50, self._scroll_to_bottom)

    def append_token(self, token: str):
        """Append a streaming token to current assistant message."""
        if self._current_bubble:
            self._current_bubble.append_text(token)
            # Auto-scroll while streaming
            self._scroll_to_bottom()

    def finish_assistant_message(self):
        """Mark current streaming message as complete."""
        self._current_bubble = None
        if self._current_tab and self._current_tab.summary:
            self._summary_bar.show()

    def add_error(self, error: str):
        """Display an error message."""
        bubble = MessageBubble("assistant", f"⚠ {error}")
        self._messages_layout.insertWidget(
            self._messages_layout.count() - 1,
            bubble
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
