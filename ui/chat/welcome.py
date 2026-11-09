"""
Welcome panel — shown in a tab that has no conversation yet.

Replaces the old first-launch popup: instead of forcing the situation
check on people, each empty tab says what it's for, offers a few
questions to tap, and (until it's been done) offers the 5-question
situation check as an optional card.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QGridLayout, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal

from core.app.platform_info import PHONE_LAYOUT


# What each tab is for, and questions to start with
TAB_WELCOME = {
    "survival": (
        "Water, fire, shelter, food and staying safe — right now.",
        ["How do I make water safe to drink?",
         "How do I start a fire without matches?",
         "What's the quickest shelter I can build before dark?",
         "What should I do first if I'm lost?"],
    ),
    "medical": (
        "First aid, wounds, illness and improvised medicine. "
        "In an emergency, say so — it switches to step-by-step mode.",
        ["How do I stop heavy bleeding?",
         "How do I clean and close a deep cut?",
         "What are the signs of infection in a wound?",
         "How do I splint a broken arm?"],
    ),
    "electronics": (
        "Circuits, batteries, solar, radio and salvaging parts. "
        "“Explain” questions are worked out from first principles.",
        ["Explain why power equals voltage times current",
         "How do I wire solar panels to charge a 12 V battery?",
         "How do I test if a battery is still good?",
         "Explain how a voltage divider works"],
    ),
    "navigation": (
        "Finding north, working out where you are, weather and signalling.",
        ["How do I find north without a compass?",
         "Explain how to find latitude from the North Star",
         "How do I signal for rescue?",
         "How do I read the weather from the sky?"],
    ),
    "farming": (
        "Growing food, preserving it, and keeping animals.",
        ["What can I plant now that grows fastest?",
         "How do I store food without a fridge?",
         "How do I make sauerkraut?",
         "How do I save seeds for next year?"],
    ),
    "build": (
        "Shelter, tools, structures and working with wood, stone and metal.",
        ["How do I build a simple log shelter?",
         "Explain how much load a wooden beam can take",
         "How do I make basic tools from scrap metal?",
         "How do I make a lever lift a heavy rock?"],
    ),
    "chemistry": (
        "Soap, lye, metals and materials — with the safety steps included.",
        ["How do I make lye from wood ash?",
         "How do I make soap from fat?",
         "Explain how to dilute a strong solution safely",
         "How do I make charcoal?"],
    ),
    "prometheus": (
        "Hi. What's on your mind? Just start typing — anything goes.",
        ["Tell me something interesting",
         "Help me think something through",
         "What did the Stoics say about hard times?",
         "I just want to talk"],
    ),
}
DEFAULT_WELCOME = (
    "Ask anything about this topic.",
    [],
)


class WelcomePanel(QWidget):
    suggestion_clicked   = Signal(str)
    assessment_requested = Signal()

    def __init__(self, tab, show_check: bool, parent=None):
        super().__init__(parent)
        self.setObjectName("welcomePanel")
        intro, suggestions = TAB_WELCOME.get(tab.id, DEFAULT_WELCOME)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 40, 24, 24)
        outer.addStretch(1)

        # Keep the content a comfortable reading width, centred
        column = QWidget()
        column.setMaximumWidth(640)
        col = QVBoxLayout(column)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(10)

        # Step 1: what this tab is for
        title = QLabel(f"{tab.icon}  {tab.name}")
        title.setObjectName("welcomeTitle")
        col.addWidget(title)

        text = QLabel(intro)
        text.setObjectName("welcomeIntro")
        text.setWordWrap(True)
        col.addWidget(text)

        # Step 2: questions to tap
        if suggestions:
            col.addSpacing(10)
            hint = QLabel("TRY ASKING")
            hint.setObjectName("welcomeHint")
            col.addWidget(hint)
            grid = QGridLayout()
            grid.setSpacing(8)
            cols = 1 if PHONE_LAYOUT else 2
            for i, q in enumerate(suggestions):
                btn = QPushButton(q)
                btn.setObjectName("suggestionBtn")
                btn.setCursor(Qt.PointingHandCursor)
                btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                btn.clicked.connect(lambda _=False, t=q: self.suggestion_clicked.emit(t))
                grid.addWidget(btn, i // cols, i % cols)
            col.addLayout(grid)

        # Step 3: optional situation check (until it's been done once)
        if show_check:
            col.addSpacing(14)
            card = QFrame()
            card.setObjectName("checkCard")
            row = QHBoxLayout(card)
            row.setContentsMargins(14, 12, 12, 12)
            note = QLabel(
                "Not sure where to start? Five quick questions about where you are "
                "and what you have give you a priority list."
            )
            note.setWordWrap(True)
            note.setObjectName("welcomeIntro")
            start = QPushButton("Situation check")
            start.setObjectName("primaryBtn")
            start.setCursor(Qt.PointingHandCursor)
            start.clicked.connect(self.assessment_requested.emit)
            row.addWidget(note, 1)
            row.addWidget(start)
            col.addWidget(card)

        holder = QHBoxLayout()
        holder.addStretch(1)
        holder.addWidget(column, 100)
        holder.addStretch(1)
        outer.addLayout(holder)
        outer.addStretch(2)
