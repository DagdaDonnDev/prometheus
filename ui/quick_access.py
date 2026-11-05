"""
Quick Access Tab
================
Single screen with the most critical actions.
One tap to the most important information.
No typing required.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QFrame, QScrollArea,
    QSizePolicy
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont


# ── Quick action definitions ───────────────────────────────────────────────

QUICK_ACTIONS = [
    # Row 1 — Immediate survival
    {
        "icon": "💧",
        "label": "Water",
        "prompt": "I need water right now. What are my immediate options for finding and purifying water?",
        "tab": "survival",
        "color": "#1a3a5c",
        "border": "#2a6aac",
    },
    {
        "icon": "🔥",
        "label": "Fire",
        "prompt": "I need to start a fire now. What is the fastest reliable method with natural materials?",
        "tab": "survival",
        "color": "#3a1a00",
        "border": "#c45000",
    },
    {
        "icon": "🏕️",
        "label": "Shelter",
        "prompt": "I need emergency shelter now. What can I build quickly with what is around me?",
        "tab": "survival",
        "color": "#1a2a1a",
        "border": "#3a6a3a",
    },
    {
        "icon": "🌿",
        "label": "Food",
        "prompt": "What is safe to eat in my surroundings right now? How do I identify edible plants?",
        "tab": "farming",
        "color": "#1a2a1a",
        "border": "#4a8a2a",
    },

    # Row 2 — Medical
    {
        "icon": "🩸",
        "label": "Bleeding",
        "prompt": "Someone is bleeding seriously. What do I do right now to stop it?",
        "tab": "medical",
        "color": "#3a0000",
        "border": "#aa0000",
    },
    {
        "icon": "🤒",
        "label": "Fever",
        "prompt": "Someone has a high fever with no medicine available. What do I do?",
        "tab": "medical",
        "color": "#2a1a00",
        "border": "#8a5000",
    },
    {
        "icon": "🦴",
        "label": "Fracture",
        "prompt": "I think someone has a broken bone. How do I assess and splint it without medical equipment?",
        "tab": "medical",
        "color": "#2a2a00",
        "border": "#7a7a00",
    },
    {
        "icon": "🤢",
        "label": "Infection",
        "prompt": "A wound is showing signs of infection. What do I do without antibiotics?",
        "tab": "medical",
        "color": "#1a2a1a",
        "border": "#2a7a2a",
    },

    # Row 3 — Navigation and situation
    {
        "icon": "🧭",
        "label": "Find North",
        "prompt": "How do I find north right now without a compass?",
        "tab": "navigation",
        "color": "#001a2a",
        "border": "#006a8a",
    },
    {
        "icon": "📍",
        "label": "Where Am I",
        "prompt": "I don't know where I am. Walk me through how to determine my rough location from what I can observe.",
        "tab": "navigation",
        "color": "#001a2a",
        "border": "#005a7a",
    },
    {
        "icon": "📡",
        "label": "Signal",
        "prompt": "How do I signal for help or other survivors? What are the most visible methods?",
        "tab": "navigation",
        "color": "#1a001a",
        "border": "#6a006a",
    },
    {
        "icon": "⛅",
        "label": "Weather",
        "prompt": "How do I read the weather without instruments? What signs tell me what is coming?",
        "tab": "navigation",
        "color": "#001a2a",
        "border": "#004a6a",
    },

    # Row 4 — Build and resources
    {
        "icon": "⚡",
        "label": "Power",
        "prompt": "How do I generate basic electricity from available materials without a grid?",
        "tab": "electronics",
        "color": "#2a2a00",
        "border": "#aaaa00",
    },
    {
        "icon": "🔧",
        "label": "Tools",
        "prompt": "How do I make basic tools from raw materials when I have nothing to start with?",
        "tab": "build",
        "color": "#1a1a1a",
        "border": "#5a5a5a",
    },
    {
        "icon": "🧪",
        "label": "Soap",
        "prompt": "How do I make soap from ash and fat? Give me the complete process.",
        "tab": "chemistry",
        "color": "#001a2a",
        "border": "#005a8a",
    },
    {
        "icon": "🍺",
        "label": "Ferment",
        "prompt": "How do I ferment food or make alcohol safely from what I have available?",
        "tab": "farming",
        "color": "#1a0a00",
        "border": "#6a3000",
    },
]


class QuickButton(QFrame):
    """Single quick action button."""
    triggered = Signal(str, str)  # prompt, tab_id

    def __init__(self, action: dict, parent=None):
        super().__init__(parent)
        self.prompt = action["prompt"]
        self.tab_id = action["tab"]

        self.setObjectName("quickBtn")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(80)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # Neutral card; the action's colour is only a bar on the left edge
        self.setStyleSheet(
            f"QFrame#quickBtn {{ border-left: 4px solid {action['border']}; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignCenter)

        icon = QLabel(action["icon"])
        icon.setAlignment(Qt.AlignCenter)
        font = icon.font()
        font.setPointSize(22)
        icon.setFont(font)
        layout.addWidget(icon)

        label = QLabel(action["label"])
        label.setAlignment(Qt.AlignCenter)
        label.setObjectName("quickLabel")
        layout.addWidget(label)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.triggered.emit(self.prompt, self.tab_id)


class QuickAccessWidget(QWidget):
    """
    Quick access tab content.
    Grid of critical action buttons.
    """
    action_triggered = Signal(str, str)  # prompt, tab_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QFrame()
        header.setObjectName("tabInfo")
        header.setFixedHeight(36)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 0, 16, 0)
        title = QLabel("⚡  Quick Access — tap to ask")
        title.setObjectName("tabInfo")
        hl.addWidget(title)
        layout.addWidget(header)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("chatScroll")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(12, 12, 12, 12)
        content_layout.setSpacing(10)

        # Section labels and grid
        sections = [
            ("Survival",          QUICK_ACTIONS[0:4]),
            ("Medical",           QUICK_ACTIONS[4:8]),
            ("Navigation",        QUICK_ACTIONS[8:12]),
            ("Build & Resources", QUICK_ACTIONS[12:16]),
        ]

        for section_name, actions in sections:
            # Section label
            lbl = QLabel(section_name.upper())
            lbl.setObjectName("sectionHeader")
            content_layout.addWidget(lbl)

            # 2x2 grid of buttons
            grid = QGridLayout()
            grid.setSpacing(8)
            for i, action in enumerate(actions):
                btn = QuickButton(action)
                btn.triggered.connect(self.action_triggered)
                row, col = divmod(i, 2)
                grid.addWidget(btn, row, col)
            content_layout.addLayout(grid)

        content_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)
