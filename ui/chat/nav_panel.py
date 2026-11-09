"""
Left navigation — sections on top, that section's chats underneath.

Replaces the old row of tabs across the top (names were cut off once there
were more than a few). Same signals and methods as the old TabBar, so the
window drives it the same way:
    tab_selected(id) · tab_add_requested · quick_access_requested
    set_active(id) · set_label(id, text) · refresh()

Desktop: a column on the left (the header's ☰ shows or hides it).
Phone:   ☰ swaps the conversation for this menu.
"""

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QWidget, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal

from core.app.platform_info import PHONE_LAYOUT


class _NavItem(QPushButton):
    """One section: icon and name. The open one gets a bar on its left."""

    def __init__(self, tab_id: str, icon: str, name: str):
        super().__init__(f"{icon}   {name}")
        self.tab_id, self.icon = tab_id, icon
        self.setObjectName("navItem")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(36)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)


class NavPanel(QFrame):
    tab_selected = Signal(str)
    tab_add_requested = Signal()
    quick_access_requested = Signal()

    def __init__(self, tab_manager, chats_panel, parent=None):
        super().__init__(parent)
        self.tab_manager = tab_manager
        self.setObjectName("navPanel")
        if not PHONE_LAYOUT:
            self.setMinimumWidth(230)
            self.setMaximumWidth(300)
        self._items = {}

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 12, 10, 10)
        lay.setSpacing(4)

        # Step 1: urgent help first — one tap away from anywhere
        quick = QPushButton("Quick help")
        quick.setObjectName("navQuick")
        quick.setCursor(Qt.PointingHandCursor)
        quick.setFixedHeight(38)
        quick.setToolTip("16 one-tap questions for urgent situations")
        quick.clicked.connect(self.quick_access_requested)
        lay.addWidget(quick)
        lay.addSpacing(8)

        # Step 2: the sections
        head = QHBoxLayout()
        label = QLabel("Sections")
        label.setObjectName("navHeading")
        head.addWidget(label)
        head.addStretch()
        add = QPushButton("+")
        add.setObjectName("navAdd")
        add.setFixedSize(24, 24)
        add.setCursor(Qt.PointingHandCursor)
        add.setToolTip("New section")
        add.clicked.connect(self.tab_add_requested)
        head.addWidget(add)
        lay.addLayout(head)

        self._list = QWidget()
        self._list_lay = QVBoxLayout(self._list)
        self._list_lay.setContentsMargins(0, 0, 0, 0)
        self._list_lay.setSpacing(2)
        lay.addWidget(self._list)
        self._fill()

        # Step 3: this section's chats (new, search, switch)
        lay.addSpacing(10)
        self.chats_panel = chats_panel
        chats_panel.setParent(self)
        lay.addWidget(chats_panel, 100)
        lay.addStretch(1)       # sections stay together at the top when there's no chat list

        self.set_active(self.tab_manager.active_tab_id)

    def _fill(self):
        for tab in self.tab_manager.tabs:
            item = _NavItem(tab.id, tab.icon, tab.name)
            item.clicked.connect(lambda _=False, tid=tab.id: self._clicked(tid))
            self._list_lay.addWidget(item)
            self._items[tab.id] = item

    def _clicked(self, tab_id: str):
        self.set_active(tab_id)
        self.tab_selected.emit(tab_id)

    # ── Same API as the old TabBar ─────────────────────────────────────────

    def set_active(self, tab_id: str):
        for tid, item in self._items.items():
            item.setChecked(tid == tab_id)

    def set_label(self, tab_id: str, name: str):
        item = self._items.get(tab_id)
        if item:
            item.setText(f"{item.icon}   {name}")

    def refresh(self):
        """Rebuild the list (after adding a section)."""
        for item in self._items.values():
            item.setParent(None)
            item.deleteLater()
        self._items.clear()
        self._fill()
        self.set_active(self.tab_manager.active_tab_id)

    # The old TabBar exposed its buttons; tests and the window still look them up
    @property
    def _buttons(self):
        return self._items
