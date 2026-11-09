"""
Input bar - text input, send button, voice button.
"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QTextEdit, QPushButton,
    QFrame, QSizePolicy
)
from PySide6.QtCore import Signal, Qt, QSize
from PySide6.QtGui import QKeyEvent, QTextCursor, QIcon, QCursor

from core.voice.stt import STTEngine
from core.app.platform_info import PHONE_LAYOUT


class ExpandingTextEdit(QTextEdit):
    """Text edit that expands with content up to a max height."""
    submit_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        from core.app.platform_info import PHONE_LAYOUT
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
    stop_requested = Signal()       # emitted when user hits stop during generation
    mic_clicked = Signal()          # stop the voice, or switch voice conversation on/off
    talk_started = Signal()         # send button held down: start listening
    talk_finished = Signal()        # …and let go: send what was said

    def __init__(self, stt: STTEngine, parent=None):
        super().__init__(parent)
        self.stt = stt
        self._generating = False
        self._talking = False           # send button is being held to talk
        self._mic_mode = "idle"

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
        # The composer: one rounded box holding the text, the mic and send,
        # centred under the conversation
        holder = QHBoxLayout()
        holder.setContentsMargins(*((8, 6, 8, 8) if PHONE_LAYOUT else (24, 8, 24, 14)))
        row = QFrame()
        row.setObjectName("composer")
        if not PHONE_LAYOUT:
            row.setMaximumWidth(820)
        holder.addStretch()
        holder.addWidget(row, 100)
        holder.addStretch()
        outer.addLayout(holder)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(10, 6, 6, 6)
        layout.setSpacing(6)

        # Text input
        self._text = ExpandingTextEdit()
        self._text.submit_requested.connect(self.submit)
        layout.addWidget(self._text)

        # Mic button — three looks (set_mic_mode):
        #   idle       🎤  click: start a voice conversation
        #   listening  🎤 on a red fill: in a voice conversation; click to end it
        #   speaking   a black square: the voice is talking; click to stop it
        self._voice_btn = QPushButton("🎤")
        self._voice_btn.setObjectName("voiceBtn")
        self._voice_btn.setFixedSize(44, 44)
        self._voice_btn.clicked.connect(self.mic_clicked.emit)
        layout.addWidget(self._voice_btn)

        # Send / Stop button. Click = send. Hold (⅓ s) = talk; let go = send it.
        self._send_btn = QPushButton("➤")
        self._send_btn.setObjectName("sendBtn")
        self._send_btn.setFixedSize(44, 44)
        self._send_btn.pressed.connect(self._send_pressed)
        self._send_btn.released.connect(self._send_released)
        layout.addWidget(self._send_btn)
        from PySide6.QtCore import QTimer
        self._hold_timer = QTimer(self)
        self._hold_timer.setSingleShot(True)
        self._hold_timer.setInterval(350)
        self._hold_timer.timeout.connect(self._start_talking)

        # Voice input starts off; speech recognition loads in the background
        # and set_voice_available() turns the button on when it's ready
        self.set_voice_available(stt.available, getattr(stt, "error", "") or "Loading speech recognition…")

    def set_mic_mode(self, mode: str):
        """'idle', 'listening' (voice conversation on) or 'speaking' (voice talking)."""
        if mode == self._mic_mode:
            return
        self._mic_mode = mode
        b = self._voice_btn
        if mode == "speaking":
            b.setText("")
            b.setIcon(_square_icon())
            b.setToolTip("Stop talking (Esc)")
        else:
            b.setIcon(QIcon())
            b.setText("🎤")
            b.setToolTip("Listening — talk, then pause. Click to end the voice conversation"
                         if mode == "listening" else
                         "Voice conversation: talk, it answers, then listens again.\n"
                         "Or hold the send button to say one thing.")
        b.setProperty("mode", mode)
        b.style().unpolish(b)
        b.style().polish(b)

    def set_voice_available(self, available: bool, reason: str = ""):
        """Turn voice input on or off (reason = tooltip when off). Stopping the voice always works."""
        self._voice_ok = available
        self._voice_btn.setEnabled(True)
        if not available and self._mic_mode != "speaking":
            self._voice_btn.setToolTip(reason or "Voice input isn't set up — run: python tools/setup_voice.py")
        self._voice_btn.setProperty("off", not available)
        self._voice_btn.style().unpolish(self._voice_btn)
        self._voice_btn.style().polish(self._voice_btn)

    def voice_ok(self) -> bool:
        return getattr(self, "_voice_ok", False)

    # ── Send button: click to send, hold to talk ──────────────────────────

    def _send_pressed(self):
        if not self._generating and self.voice_ok():
            self._hold_timer.start()

    def _start_talking(self):
        if self._send_btn.isDown() and not self._generating:
            self._talking = True
            self._send_btn.setText("●")
            self._send_btn.setToolTip("Listening — let go to send")
            self._send_btn.setProperty("talking", True)
            self._send_btn.style().unpolish(self._send_btn)
            self._send_btn.style().polish(self._send_btn)
            self.talk_started.emit()

    def _send_released(self):
        self._hold_timer.stop()
        if self._talking:
            self._talking = False
            self._send_btn.setText("➤")
            self._send_btn.setToolTip("Send (hold to talk)")
            self._send_btn.setProperty("talking", False)
            self._send_btn.style().unpolish(self._send_btn)
            self._send_btn.style().polish(self._send_btn)
            self.talk_finished.emit()
        elif self._send_btn.rect().contains(self._send_btn.mapFromGlobal(QCursor.pos())) \
                or not self.underMouse():
            self._on_send_or_stop()

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


def _square_icon():
    """A filled black square on the light 'speaking' button — the stop sign."""
    from PySide6.QtGui import QPixmap, QPainter, QColor
    pix = QPixmap(32, 32)
    pix.fill(QColor(0, 0, 0, 0))
    p = QPainter(pix)
    p.fillRect(7, 7, 18, 18, QColor("#111111"))
    p.end()
    return QIcon(pix)
