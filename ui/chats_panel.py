"""
Chats bar (left) — this tab's chats: start a new one, search, switch.

Each chat is separate: a new chat starts with no messages from the others,
so earlier conversations don't steer it. Right-click a chat to rename or
delete it.

Desktop: a column on the left, shown or hidden with the header's Chats button.
Phone:   the Chats button swaps the conversation for this list.
"""

from datetime import datetime, timedelta

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QPushButton, QLineEdit, QListWidget, QListWidgetItem,
    QLabel, QWidget, QMenu,
)
from PySide6.QtCore import Qt, Signal

from core.platform_info import PHONE_LAYOUT


def _when(iso: str) -> str:
    """'Today 14:03', 'Yesterday', 'Mon', '3 Nov' — short and readable."""
    try:
        t = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return ""
    now = datetime.now()
    if t.date() == now.date():
        return f"Today {t:%H:%M}"
    if t.date() == (now - timedelta(days=1)).date():
        return "Yesterday"
    if (now - t).days < 7:
        return f"{t:%a}"
    return f"{t.day} {t:%b}"


class _ChatRow(QWidget):
    def __init__(self, title: str, when: str):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 6, 8, 6)
        lay.setSpacing(1)
        t = QLabel(title)
        t.setObjectName("chatRowTitle")
        w = QLabel(when)
        w.setObjectName("chatRowWhen")
        lay.addWidget(t)
        lay.addWidget(w)


class ChatsPanel(QFrame):
    new_chat_requested = Signal()
    open_requested     = Signal(str)          # chat id
    delete_requested   = Signal(str)
    rename_requested   = Signal(str, str)     # chat id, current title

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("chatsPanel")
        if not PHONE_LAYOUT:
            self.setMinimumWidth(200)
            self.setMaximumWidth(300)
        self._tab = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        new_btn = QPushButton("+  New chat")
        new_btn.setObjectName("primaryBtn")
        new_btn.setCursor(Qt.PointingHandCursor)
        new_btn.clicked.connect(self.new_chat_requested.emit)
        lay.addWidget(new_btn)

        self._search = QLineEdit()
        self._search.setObjectName("chatSearch")
        self._search.setPlaceholderText("Search chats")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(lambda _: self.refresh(self._tab))
        lay.addWidget(self._search)

        self._list = QListWidget()
        self._list.setObjectName("chatList")
        self._list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._menu)
        self._list.itemClicked.connect(
            lambda item: self.open_requested.emit(item.data(Qt.UserRole)))
        lay.addWidget(self._list, 1)

        self._empty = QLabel("")
        self._empty.setObjectName("infoLabel")
        self._empty.setWordWrap(True)
        lay.addWidget(self._empty)

    def refresh(self, tab):
        """Rebuild the list for this tab (newest first, current one selected)."""
        self._tab = tab
        self._list.clear()
        if tab is None:
            return
        query = self._search.text().strip()
        chats = tab.all_chats(query)
        for c in chats:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, c["id"])
            row = _ChatRow(c.get("title") or "New chat", _when(c.get("updated", "")))
            item.setSizeHint(row.sizeHint())
            self._list.addItem(item)
            self._list.setItemWidget(item, row)
            if c.get("current"):
                item.setSelected(True)
        if not chats:
            self._empty.setText("No chats match." if query else
                                "No chats yet — your conversations will be listed here.")
            self._empty.show()
        else:
            self._empty.hide()

    def focus_search(self):
        self._search.setFocus()

    def _menu(self, pos):
        item = self._list.itemAt(pos)
        if not item:
            return
        chat_id = item.data(Qt.UserRole)
        title = ""
        w = self._list.itemWidget(item)
        if w:
            title = w.findChild(QLabel, "chatRowTitle").text()
        menu = QMenu(self)
        menu.addAction("Rename", lambda: self.rename_requested.emit(chat_id, title))
        menu.addSeparator()
        menu.addAction("Delete", lambda: self.delete_requested.emit(chat_id))
        menu.exec(self._list.viewport().mapToGlobal(pos))
