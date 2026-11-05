"""
Tab bar - scrollable row of tabs with icons.
"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QScrollArea, QPushButton,
    QFrame, QSizePolicy
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QFont

from core.tabs import TabManager


class TabButton(QPushButton):
    def __init__(self, tab_id: str, icon: str, name: str, parent=None):
        super().__init__(f"{icon} {name}", parent)
        self.tab_id = tab_id
        self.setObjectName("tabBtn")
        self.setCheckable(True)
        self.setFixedHeight(36)
        self.setMinimumWidth(90)
        # Never squeeze below the text's width — on narrow screens the row scrolls
        from PySide6.QtWidgets import QSizePolicy
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)

    def set_active(self, active: bool):
        self.setChecked(active)
        self.setObjectName("tabBtnActive" if active else "tabBtn")
        self.style().unpolish(self)
        self.style().polish(self)


class TabBar(QWidget):
    tab_selected = Signal(str)
    tab_add_requested = Signal()
    quick_access_requested = Signal()

    def __init__(self, tab_manager: TabManager, parent=None):
        super().__init__(parent)
        self.tab_manager = tab_manager
        self._buttons: dict = {}
        self.setFixedHeight(44)
        self.setObjectName("tabBar")
        self._build()

    def _build(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)

        # Quick access button (leftmost, always visible)
        quick_btn = QPushButton("Quick help")
        quick_btn.setObjectName("quickAccessBtn")
        quick_btn.setFixedHeight(32)
        quick_btn.setToolTip("16 one-tap questions for urgent situations")
        quick_btn.clicked.connect(self.quick_access_requested)
        layout.addWidget(quick_btn)

        # Scrollable tab area
        scroll = QScrollArea()
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(40)
        scroll.setObjectName("tabScroll")

        container = QWidget()
        container.setObjectName("tabContainer")
        container_layout = QHBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(4)

        for tab in self.tab_manager.tabs:
            btn = TabButton(tab.id, tab.icon, tab.name)
            btn.clicked.connect(lambda checked, tid=tab.id: self._on_tab_click(tid))
            container_layout.addWidget(btn)
            self._buttons[tab.id] = btn

        container_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll)

        # Add tab button
        add_btn = QPushButton("+")
        add_btn.setObjectName("addTabBtn")
        add_btn.setFixedSize(36, 36)
        add_btn.setToolTip("New tab")
        add_btn.clicked.connect(self.tab_add_requested)
        layout.addWidget(add_btn)

        # Set active
        self.set_active(self.tab_manager.active_tab_id)

    def _on_tab_click(self, tab_id: str):
        self.set_active(tab_id)
        self.tab_selected.emit(tab_id)

    def set_active(self, tab_id: str):
        for tid, btn in self._buttons.items():
            btn.set_active(tid == tab_id)

    def refresh(self):
        """Rebuild tab bar (after adding custom tab)."""
        # Clear existing
        for btn in self._buttons.values():
            btn.deleteLater()
        self._buttons.clear()

        # Remove old layout
        old_layout = self.layout()
        if old_layout:
            QWidget().setLayout(old_layout)

        self._build()
