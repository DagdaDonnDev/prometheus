"""
Input bar - text input, send button, voice button.
"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QTextEdit, QPushButton,
    QFrame, QSizePolicy
)
from PySide6.QtCore import Signal, Qt, QSize
from PySide6.QtGui import QKeyEvent, QTextCursor

from core.stt import STTEngine


class ExpandingTextEdit(QTextEdit):
    """Text edit that expands with content up to a max height."""
    submit_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        from core.platform_info import PHONE_LAYOUT
        self.setPlaceholderText(
            "Ask anything…" if PHONE_LAYOUT
            else "Ask anything... (Enter to send, Shift+Enter for new line)"
        )
        self.setMinimumHeight(44)
        self.setMaximumHeight(150)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.document().contentsChanged.connect(self._adjust_height)
        self.setFixedHeight(44)   # start one line tall; grows as you type

        # Up / Down bring back what you sent before (newest first), like a terminal
        self.recall: list = []
        self._recall_pos = None

    def _adjust_height(self):
        doc_height = int(self.document().size().height()) + 16
        new_height = max(44, min(150, doc_height))
        self.setFixedHeight(new_height)

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        if key in (Qt.Key_Return, Qt.Key_Enter):
            if event.modifiers() & Qt.ShiftModifier:
                super().keyPressEvent(event)
            else:
                self._recall_pos = None
                self.submit_requested.emit()
            return

        cursor = self.textCursor()
        on_first_line = cursor.blockNumber() == 0
        on_last_line = cursor.blockNumber() == self.document().blockCount() - 1

        # Step 1: Up on an empty box (or while flicking through) → an older message
        if key == Qt.Key_Up and self.recall and on_first_line and \
                (not self.toPlainText().strip() or self._recall_pos is not None):
            pos = len(self.recall) if self._recall_pos is None else self._recall_pos
            if pos > 0:
                self._recall_pos = pos - 1
                self._show_recalled()
            return

        # Step 2: Down while flicking through → a newer one, then back to empty
        if key == Qt.Key_Down and self._recall_pos is not None and on_last_line:
            if self._recall_pos < len(self.recall) - 1:
                self._recall_pos += 1
                self._show_recalled()
            else:
                self._recall_pos = None
                self.clear()
            return

        super().keyPressEvent(event)

    def _show_recalled(self):
        self.setPlainText(self.recall[self._recall_pos])
        self.moveCursor(QTextCursor.MoveOperation.End)


class InputBar(QFrame):
    message_submitted = Signal(str)
    voice_toggled = Signal(bool)
    stop_requested = Signal()       # emitted when user hits stop during generation

    def __init__(self, stt: STTEngine, parent=None):
        super().__init__(parent)
        self.stt = stt
        self._recording = False
        self._generating = False

        self.setObjectName("inputBar")
        self.setFrameShape(QFrame.NoFrame)

        # Banner shown while you're editing an earlier message
        from PySide6.QtWidgets import QVBoxLayout, QLabel
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self._edit_banner = QLabel("Editing your message — Enter sends it from here, Esc cancels")
        self._edit_banner.setObjectName("editBanner")
        self._edit_banner.hide()
        outer.addWidget(self._edit_banner)
        row = QWidget()
        outer.addWidget(row)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        # Text input
        self._text = ExpandingTextEdit()
        self._text.submit_requested.connect(self.submit)
        layout.addWidget(self._text)

        # Voice button
        self._voice_btn = QPushButton("🎤")
        self._voice_btn.setObjectName("voiceBtn")
        self._voice_btn.setFixedSize(44, 44)
        self._voice_btn.setCheckable(True)
        self._voice_btn.setToolTip("Hold to speak")
        self._voice_btn.clicked.connect(self._on_voice_click)
        layout.addWidget(self._voice_btn)

        # Send / Stop button
        self._send_btn = QPushButton("➤")
        self._send_btn.setObjectName("sendBtn")
        self._send_btn.setFixedSize(44, 44)
        self._send_btn.clicked.connect(self._on_send_or_stop)
        layout.addWidget(self._send_btn)

        # Voice input starts off; speech recognition loads in the background
        # and set_voice_available() turns the button on when it's ready
        self.set_voice_available(stt.available, getattr(stt, "error", "") or "Loading speech recognition…")

    def set_voice_available(self, available: bool, reason: str = ""):
        """Turn the mic button on or off (reason = tooltip when off)."""
        self._voice_btn.setEnabled(available)
        self._voice_btn.setToolTip("Hold to speak" if available else
                                   (reason or "Voice input isn't set up — run: python setup_voice.py"))

    def _on_send_or_stop(self):
        if self._generating:
            self.stop_requested.emit()
        else:
            self.submit()

    def submit(self):
        if self._generating:
            return
        text = self._text.toPlainText().strip()
        if text:
            self.message_submitted.emit(text)

    def set_recall(self, messages: list):
        """Your earlier messages in this tab, oldest first (Up shows the newest)."""
        self._text.recall = [m for m in messages if m.strip()][-50:]
        self._text._recall_pos = None

    def remember_sent(self, text: str):
        if text.strip() and (not self._text.recall or self._text.recall[-1] != text):
            self._text.recall.append(text)
        self._text._recall_pos = None

    def set_editing(self, editing: bool):
        self._edit_banner.setVisible(editing)

    def focus_input(self):
        self._text.setFocus()

    def clear_input(self):
        self._text.clear()

    def set_text(self, text: str):
        self._text.setPlainText(text)
        self._text.moveCursor(QTextCursor.MoveOperation.End)

    def set_generating(self, generating: bool):
        self._generating = generating
        self._text.setReadOnly(generating)
        self._send_btn.setEnabled(True)   # always enabled — stops generation when active
        self._send_btn.setText("⏹" if generating else "➤")
        self._send_btn.setToolTip("Stop generation" if generating else "Send")

    def _on_voice_click(self, checked: bool):
        self._recording = checked
        self.voice_toggled.emit(checked)

        if checked:
            self._voice_btn.setText("⏹")
            self._voice_btn.setToolTip("Stop recording")
        else:
            self._voice_btn.setText("🎤")
            self._voice_btn.setToolTip("Hold to speak")
