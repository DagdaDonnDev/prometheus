"""
Input bar - text input, send button, voice button.
"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QTextEdit, QPushButton,
    QFrame, QSizePolicy
)
from PySide6.QtCore import Signal, Qt, QSize
from PySide6.QtGui import QKeyEvent

from core.stt import STTEngine


class ExpandingTextEdit(QTextEdit):
    """Text edit that expands with content up to a max height."""
    submit_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText("Ask anything... (Enter to send, Shift+Enter for new line)")
        self.setMinimumHeight(44)
        self.setMaximumHeight(150)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.document().contentsChanged.connect(self._adjust_height)

    def _adjust_height(self):
        doc_height = int(self.document().size().height()) + 16
        new_height = max(44, min(150, doc_height))
        self.setFixedHeight(new_height)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if event.modifiers() & Qt.ShiftModifier:
                super().keyPressEvent(event)
            else:
                self.submit_requested.emit()
        else:
            super().keyPressEvent(event)


class InputBar(QFrame):
    message_submitted = Signal(str)
    voice_toggled = Signal(bool)

    def __init__(self, stt: STTEngine, parent=None):
        super().__init__(parent)
        self.stt = stt
        self._recording = False
        self._generating = False

        self.setObjectName("inputBar")
        self.setFrameShape(QFrame.NoFrame)

        layout = QHBoxLayout(self)
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

        # Send button
        self._send_btn = QPushButton("➤")
        self._send_btn.setObjectName("sendBtn")
        self._send_btn.setFixedSize(44, 44)
        self._send_btn.clicked.connect(self.submit)
        layout.addWidget(self._send_btn)

        # Hide voice if STT not available
        if not stt.available:
            self._voice_btn.setEnabled(False)
            self._voice_btn.setToolTip("Install faster-whisper for voice input")

    def submit(self):
        if self._generating:
            return
        text = self._text.toPlainText().strip()
        if text:
            self.message_submitted.emit(text)

    def clear_input(self):
        self._text.clear()

    def set_text(self, text: str):
        self._text.setPlainText(text)
        self._text.moveCursor(self._text.textCursor().End)

    def set_generating(self, generating: bool):
        self._generating = generating
        self._text.setReadOnly(generating)
        self._send_btn.setEnabled(not generating)
        self._send_btn.setText("⏹" if generating else "➤")

    def _on_voice_click(self, checked: bool):
        self._recording = checked
        self.voice_toggled.emit(checked)

        if checked:
            self._voice_btn.setText("⏹")
            self._voice_btn.setToolTip("Stop recording")
        else:
            self._voice_btn.setText("🎤")
            self._voice_btn.setToolTip("Hold to speak")
