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
    What an answer is drawing on, shown under it — always open.

    Step 1: a "From:" line naming each source (book and page)
    Step 2: the page image of the top source, shown straight away
    Step 3: up to two more pages as small thumbnails
    Click any image to see it full size.
    """

    MAIN_WIDTH  = 260 if PHONE_LAYOUT else 320
    THUMB_WIDTH = 110

    def __init__(self, image_paths: List[str] = None, sources: List[str] = None, parent=None):
        super().__init__(parent)
        self.setObjectName("imagePanel")
        image_paths = [p for p in (image_paths or []) if Path(p).exists()][:3]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 0, 8, 6)
        layout.setSpacing(6)

        # Step 1
        if sources:
            src = QLabel("From: " + " · ".join(sources))
            src.setObjectName("timingStamp")
            src.setWordWrap(True)
            layout.addWidget(src)

        if not image_paths:
            return

        # Step 2
        main = self._image_label(image_paths[0], self.MAIN_WIDTH)
        if main:
            layout.addWidget(main, 0, Qt.AlignLeft)

        # Step 3
        if len(image_paths) > 1:
            row = QHBoxLayout()
            row.setSpacing(6)
            for path in image_paths[1:]:
                thumb = self._image_label(path, self.THUMB_WIDTH)
                if thumb:
                    row.addWidget(thumb)
            row.addStretch()
            layout.addLayout(row)

    def _image_label(self, img_path: str, width: int):
        pixmap = QPixmap(img_path)
        if pixmap.isNull():
            return None
        pixmap = pixmap.scaledToWidth(width, Qt.SmoothTransformation)
        lbl = QLabel()
        lbl.setObjectName("sourceImage")
        lbl.setPixmap(pixmap)
        lbl.setFixedSize(pixmap.width(), pixmap.height())
        lbl.setCursor(Qt.PointingHandCursor)
        lbl.setToolTip("Click to see the full page")
        lbl.mousePressEvent = lambda e, p=img_path: self._open_fullsize(p)
        return lbl

    def _open_fullsize(self, img_path: str):
        """Full page in a dark dialog, scaled to fit the screen."""
        from PySide6.QtWidgets import QScrollArea
        dialog = QDialog(self)
        dialog.setWindowTitle("Source page")
        pixmap = QPixmap(img_path)
        if pixmap.isNull():
            return
        screen = self.screen().availableGeometry() if self.screen() else None
        max_w = min(900, (screen.width() - 80) if screen else 900)
        if pixmap.width() > max_w:
            pixmap = pixmap.scaledToWidth(max_w, Qt.SmoothTransformation)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(8, 8, 8, 8)
        scroll = QScrollArea()
        img_lbl = QLabel()
        img_lbl.setPixmap(pixmap)
        scroll.setWidget(img_lbl)
        layout.addWidget(scroll)
        max_h = (screen.height() - 120) if screen else 900
        dialog.resize(pixmap.width() + 40, min(pixmap.height() + 40, max_h))
        dialog.exec()


class MessageBubble(QFrame):
    """
    One message. Right-click it, or use its ⋯ button, for:
      Copy · Edit (your messages) · Retry (the last reply) · Delete
    The ⋯ button shows on hover on a computer and always on a phone.
    """
    action = Signal(str, object)          # ("copy"|"edit"|"retry"|"delete", message dict)

    def __init__(self, role: str, content: str = "", parent=None):
        super().__init__(parent)
        self.role = role
        self.msg = None                   # the tab-history entry this bubble shows
        self.can_retry = lambda: False    # set by ChatView: only the last reply
        self.setObjectName(f"bubble_{role}")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)

        self._label = QLabel(content)
        self._label.setWordWrap(True)
        self._label.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
        )
        self._label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self._label.setContextMenuPolicy(Qt.NoContextMenu)   # right-click → our menu
        font = self._label.font()
        font.setPointSize(11 if PHONE_LAYOUT else 12)
        self._label.setFont(font)

        self._menu_btn = QPushButton("⋯")
        self._menu_btn.setObjectName("bubbleMenuBtn")
        self._menu_btn.setFixedSize(26, 26)
        self._menu_btn.setCursor(Qt.PointingHandCursor)
        self._menu_btn.setToolTip("Copy, edit, retry or delete")
        self._menu_btn.clicked.connect(
            lambda: self._show_menu(self._menu_btn.mapToGlobal(self._menu_btn.rect().bottomLeft())))
        if not PHONE_LAYOUT:
            self._menu_btn.setVisible(False)          # appears on hover

        # Yours: a soft bubble on the right. Replies: plain text across the
        # column, like a page — easier to read than a box
        if role == "user":
            layout.setContentsMargins(14, 10, 14, 10)
            self._label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
            layout.addWidget(self._menu_btn, 0, Qt.AlignTop)
            layout.addWidget(self._label)
        else:
            layout.setContentsMargins(2, 4, 2, 4)
            layout.addWidget(self._label)
            layout.addWidget(self._menu_btn, 0, Qt.AlignTop)

    # ── Actions ────────────────────────────────────────────────────────────

    def enterEvent(self, event):
        if not PHONE_LAYOUT:
            self._menu_btn.setVisible(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not PHONE_LAYOUT:
            self._menu_btn.setVisible(False)
        super().leaveEvent(event)

    def contextMenuEvent(self, event):
        self._show_menu(event.globalPos())

    def menu_actions(self) -> list:
        """Names of what the menu offers right now (also used by tests)."""
        names = ["copy"]
        if self.msg is not None:
            if self.role == "user":
                names.append("edit")
            elif self.can_retry():
                names.append("retry")
            names.append("delete")
        return names

    def _show_menu(self, where):
        from PySide6.QtWidgets import QMenu
        labels = {"copy": "Copy", "edit": "Edit", "retry": "Retry", "delete": "Delete"}
        menu = QMenu(self)
        for name in self.menu_actions():
            if name == "delete":
                menu.addSeparator()
            menu.addAction(labels[name],
                           lambda n=name: self.action.emit(n, self.msg or {"content": self.get_text()}))
        menu.exec(where)

    def fit_width(self, max_width: int):
        """
        Your bubble: as wide as the text (up to max_width), so short messages
        aren't squeezed onto two lines or cut off.
        """
        fm = self._label.fontMetrics()
        longest = max((fm.horizontalAdvance(line) for line in (self._label.text() or " ").split("\n")),
                      default=0)
        inner = max_width - 28 - (self._menu_btn.width() if PHONE_LAYOUT else 0)
        self._label.setMinimumWidth(min(longest + 6, inner))
        self.setMaximumWidth(max_width)

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
    message_action       = Signal(str, object)   # copy / edit / retry / delete, message dict

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

        # Messages sit in a centred reading column (easier on the eyes than
        # lines running the full width of a big window)
        self._messages_widget = QWidget()
        self._messages_widget.setObjectName("messagesWidget")
        centre = QHBoxLayout(self._messages_widget)
        centre.setContentsMargins(0, 0, 0, 0)
        column = QWidget()
        column.setObjectName("messagesColumn")
        if not PHONE_LAYOUT:
            column.setMaximumWidth(820)
        centre.addStretch()
        centre.addWidget(column, 100)
        centre.addStretch()
        self._messages_layout = QVBoxLayout(column)
        self._messages_layout.setContentsMargins(*((12, 12, 12, 12) if PHONE_LAYOUT else (24, 20, 24, 20)))
        self._messages_layout.setSpacing(14)
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
            bubble = self._new_bubble(msg["role"], msg["content"])
            bubble.msg = msg
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
            self._welcome.hide()
            self._welcome.deleteLater()
            self._welcome = None

    def _clear_messages(self):
        self._welcome = None
        self.hide_researching()
        layout = self._messages_layout
        while layout.count() > 1:
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.hide()                 # off screen now, not after the next event loop
                w.setParent(None)
                w.deleteLater()

    def _new_bubble(self, role: str, content: str) -> MessageBubble:
        """Every bubble reports its menu actions through message_action."""
        bubble = MessageBubble(role, content)
        bubble.action.connect(self.message_action)
        bubble.can_retry = lambda b=bubble: (
            b.msg is not None and self._current_tab is not None and
            bool(self._current_tab.history) and self._current_tab.history[-1] is b.msg and
            b.role == "assistant"
        )
        self._last_bubble = bubble
        return bubble

    def attach_last(self, msg: dict):
        """Tie the newest bubble to the history entry just saved for it."""
        b = getattr(self, "_last_bubble", None)
        if b is not None and b.msg is None:
            b.msg = msg

    def add_message(self, role: str, content: str):
        self._hide_welcome()
        bubble = self._new_bubble(role, content)
        if role == "user":
            # yours hugs the right edge and is only as wide as it needs to be
            bubble.fit_width(320 if PHONE_LAYOUT else 580)
            self._messages_layout.insertWidget(self._messages_layout.count() - 1, bubble,
                                               0, Qt.AlignRight)
        else:
            self._messages_layout.insertWidget(self._messages_layout.count() - 1, bubble)
        QTimer.singleShot(50, self._scroll_to_bottom)

    def start_assistant_message(self):
        self._hide_welcome()
        self._current_bubble = self._new_bubble("assistant", "")
        self._messages_layout.insertWidget(
            self._messages_layout.count() - 1, self._current_bubble
        )
        QTimer.singleShot(50, self._scroll_to_bottom)

    def append_token(self, token: str):
        if self._current_bubble:
            self._current_bubble.append_text(token)
            self._scroll_to_bottom()

    def finish_assistant_message(self, image_paths: List[str] = None,
                                 first_token_ms: int = 0, response_ms: int = 0,
                                 breakdown: str = "", sources: List[str] = None):
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
            stamp.setContentsMargins(2, 0, 0, 0)
            stamp.setToolTip(
                "🔊 when you started hearing the reply · ✓ when it finished"
                + (f"\n{breakdown}" if breakdown else "")
            )
            self._messages_layout.insertWidget(
                self._messages_layout.count() - 1, stamp
            )
        if self._current_tab and self._current_tab.summary:
            self._summary_bar.show()

        # What the answer drew on: source names and page images
        if image_paths or sources:
            panel = ImagePanel(image_paths, sources)
            self._messages_layout.insertWidget(
                self._messages_layout.count() - 1, panel
            )
            QTimer.singleShot(50, self._scroll_to_bottom)

    def show_researching(self, text: str):
        """
        Small working line in the chat ("🔍 Researching voltage divider…"),
        replaced by the answer. Dots animate so it's clearly busy.
        """
        self._hide_welcome()
        if getattr(self, "_research_label", None) is None:
            self._research_label = QLabel()
            self._research_label.setObjectName("researchLine")
            self._research_label.setContentsMargins(2, 4, 8, 4)
            self._messages_layout.insertWidget(self._messages_layout.count() - 1, self._research_label)
            self._research_dots = 0
            self._research_timer = QTimer(self)
            self._research_timer.timeout.connect(self._tick_researching)
            self._research_timer.start(400)
        self._research_text = text
        self._tick_researching()
        QTimer.singleShot(50, self._scroll_to_bottom)

    def _tick_researching(self):
        self._research_dots = (self._research_dots + 1) % 4
        self._research_label.setText(f"🔍  {self._research_text}" + "." * self._research_dots)

    def hide_researching(self):
        if getattr(self, "_research_label", None) is not None:
            self._research_timer.stop()
            self._research_label.deleteLater()
            self._research_label = None

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
        outer.setContentsMargins(2, 2, 8, 2)
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
