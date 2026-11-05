"""
Situation Assessment Mode
=========================
The first thing a disoriented survivor sees.
Five questions. Immediate priority list.
No prior knowledge required to use.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QScrollArea, QSizePolicy,
    QButtonGroup, QGridLayout
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont

from core.memory import Memory
from core.tabs import TabManager


# ── Question definitions ───────────────────────────────────────────────────

QUESTIONS = [
    {
        "id": "surroundings",
        "text": "What do you see around you?",
        "subtitle": "Look in every direction before answering",
        "options": [
            ("🌲 Forest / Woodland",    "forest"),
            ("🏜️ Desert / Dry scrub",   "desert"),
            ("🌊 Coast / Beach",        "coastal"),
            ("🏙️ Urban / Buildings",    "urban"),
            ("🌾 Grassland / Plains",   "grassland"),
            ("❄️ Snow / Ice",           "arctic"),
            ("🌿 Jungle / Rainforest",  "tropical"),
            ("⛰️ Mountain / Highland",  "mountain"),
        ]
    },
    {
        "id": "temperature",
        "text": "What is the temperature roughly?",
        "subtitle": "Your best estimate right now",
        "options": [
            ("🥶 Freezing — breath visible, below 0°C",  "freezing"),
            ("🧊 Cold — below 10°C",                     "cold"),
            ("😐 Mild — comfortable in light clothing",  "mild"),
            ("☀️ Hot — above 30°C, sweating",            "hot"),
            ("🔥 Burning — extreme heat, above 40°C",    "extreme_heat"),
        ]
    },
    {
        "id": "injury",
        "text": "Are you injured?",
        "subtitle": "Check your entire body carefully",
        "options": [
            ("✅ No injuries",                               "none"),
            ("🩹 Minor — cuts, bruises, can walk fine",     "minor"),
            ("⚠️ Moderate — pain, limited movement",        "moderate"),
            ("🚨 Serious — bleeding, broken bone, shock",   "serious"),
            ("😵 Head injury / Confused / Disoriented",     "head"),
        ]
    },
    {
        "id": "companions",
        "text": "Are you alone?",
        "subtitle": "Include anyone you can see or hear",
        "options": [
            ("👤 Completely alone",                         "alone"),
            ("👥 With 1-3 others",                         "small_group"),
            ("👨‍👩‍👧‍👦 Group of 4-10",                        "group"),
            ("🏘️ Larger group / community",                "community"),
        ]
    },
    {
        "id": "supplies",
        "text": "What do you have with you?",
        "subtitle": "Check your pockets, bag, vehicle — everything",
        "options": [
            ("🈳 Nothing at all",                           "nothing"),
            ("📱 Just this device",                         "device_only"),
            ("🎒 Basic bag / some supplies",                "basic_supplies"),
            ("🛠️ Tools and equipment",                      "tools"),
            ("🚗 Vehicle with supplies",                    "vehicle"),
            ("🏠 Near a structure / building",              "shelter_available"),
        ]
    },
]


# ── Priority generation ────────────────────────────────────────────────────

def generate_priorities(answers: dict) -> list:
    """
    Generate immediate priority list from assessment answers.
    Returns list of (priority_num, icon, title, detail, tab_id) tuples.
    """
    priorities = []
    p = 1

    surroundings = answers.get("surroundings", "")
    temperature  = answers.get("temperature", "")
    injury       = answers.get("injury", "none")
    companions   = answers.get("companions", "alone")
    supplies     = answers.get("supplies", "nothing")

    # ── IMMEDIATE THREATS ──────────────────────────────────────────────────

    # Serious injury is always first
    if injury == "serious":
        priorities.append((p, "🚨", "STOP BLEEDING / TREAT INJURY",
            "You have a serious injury. This is your only priority right now. "
            "Apply direct pressure to any bleeding wound. Do not move if you "
            "suspect a spinal injury. Open the Medical tab for step-by-step guidance.",
            "medical"))
        p += 1

    if injury == "head":
        priorities.append((p, "🧠", "HEAD INJURY — REST AND MONITOR",
            "Do not exert yourself. Sit or lie down. Do not sleep for 2 hours "
            "if you lost consciousness. Watch for: worsening headache, vomiting, "
            "confusion, unequal pupils. Open Medical tab for concussion protocol.",
            "medical"))
        p += 1

    # Extreme temperatures are immediately life threatening
    if temperature == "freezing":
        priorities.append((p, "🥶", "PREVENT HYPOTHERMIA — URGENT",
            "Below freezing, you have 1-3 hours before hypothermia becomes fatal "
            "without shelter. Find or build wind/snow protection immediately. "
            "Insulate yourself from the ground — ground steals heat faster than air. "
            "Do NOT remove wet clothing in wind — get out of wind first.",
            "survival"))
        p += 1

    if temperature == "extreme_heat":
        priorities.append((p, "🔥", "PREVENT HEAT STROKE — URGENT",
            "Extreme heat kills within hours. Find shade immediately — any shade. "
            "Stop all physical activity. Wet skin and fan if possible. "
            "Heat stroke signs: confusion, no sweating, red hot skin = emergency.",
            "survival"))
        p += 1

    # ── WATER ─────────────────────────────────────────────────────────────

    water_urgency = "🔵"
    water_detail = "You can survive 3 days without water but weakness begins in hours. "

    if surroundings == "desert" or temperature in ("hot", "extreme_heat"):
        water_urgency = "🔴"
        water_detail = (
            "In heat/desert conditions water is critical within 1-2 hours. "
            "Look for: dry riverbeds (dig outer bend), animal trails at dawn/dusk, "
            "green vegetation patches, rock crevices after rain. "
        )
    elif surroundings == "arctic" or temperature == "freezing":
        water_detail = (
            "Never eat snow — it lowers core temperature dangerously. "
            "Melt snow first. Ice is better than snow (more water per volume). "
        )

    water_detail += "Open the Survival tab and ask about water sources."
    priorities.append((p, water_urgency, "FIND WATER",
        water_detail, "survival"))
    p += 1

    # ── SHELTER ───────────────────────────────────────────────────────────

    if supplies not in ("shelter_available", "vehicle") and temperature in ("freezing", "cold"):
        priorities.append((p, "🏕️", "BUILD SHELTER",
            "Cold kills faster than hunger. You need wind protection and ground insulation "
            "before nightfall. A debris hut takes 1-2 hours to build and can keep you "
            "alive in freezing temperatures. Open Survival tab for shelter instructions.",
            "survival"))
        p += 1
    elif supplies == "nothing" or supplies == "device_only":
        priorities.append((p, "🏕️", "FIND SHELTER BEFORE DARK",
            "Assess structures nearby — any roof and walls are better than open air. "
            "If none available, a natural windbreak (rock face, dense trees) buys time. "
            "Build more substantial shelter when water is secured.",
            "survival"))
        p += 1

    # ── FIRE ──────────────────────────────────────────────────────────────

    if temperature in ("freezing", "cold") or surroundings in ("forest", "mountain", "arctic"):
        priorities.append((p, "🔥", "MAKE FIRE",
            "Fire provides warmth, water purification, signaling, and psychological comfort. "
            "Gather tinder (dry grass, bark shreds, dead leaves) before you need it. "
            "Even in wet conditions dry material exists — look under bark, inside dead wood. "
            "Open Survival tab and ask about fire starting methods.",
            "survival"))
        p += 1

    # ── INJURY MONITORING ─────────────────────────────────────────────────

    if injury == "minor":
        priorities.append((p, "🩹", "CLEAN AND COVER WOUNDS",
            "Minor wounds become serious infections without treatment. "
            "Clean with boiled water, cover to keep clean. "
            "Watch for redness spreading beyond wound edges, increasing warmth, pus. "
            "Open Medical tab for wound care instructions.",
            "medical"))
        p += 1

    if injury == "moderate":
        priorities.append((p, "⚠️", "ASSESS AND TREAT INJURY",
            "Your injury may worsen with activity. Assess what is limiting you. "
            "Fractures need splinting before you move. Wounds need cleaning. "
            "Open Medical tab for assessment and treatment.",
            "medical"))
        p += 1

    # ── COMPANIONS ────────────────────────────────────────────────────────

    if companions == "alone":
        priorities.append((p, "📡", "SIGNAL FOR OTHERS",
            "Finding other people dramatically increases survival probability. "
            "Universal distress signal: 3 of anything — fires, whistle blasts, "
            "loud sounds. Signal fire smoke visible for kilometres. "
            "Move to high ground if possible — better visibility and signaling range.",
            "navigation"))
        p += 1

    # ── FOOD ──────────────────────────────────────────────────────────────

    priorities.append((p, "🌿", "IDENTIFY FOOD SOURCES",
        "You can survive 3 weeks without food but weakness begins in days. "
        "Do not eat anything you cannot positively identify. "
        f"In {surroundings or 'your environment'}: open the Farm tab and ask "
        "what is safe to eat in your surroundings.",
        "farming"))
    p += 1

    # ── ORIENTATION ───────────────────────────────────────────────────────

    priorities.append((p, "🧭", "DETERMINE YOUR LOCATION",
        "Even a rough location helps decisions. Look for: sun position (rises East, "
        "sets West), water flow direction (toward coast), terrain features visible "
        "at distance. Open Navigation tab and describe what you can see.",
        "navigation"))
    p += 1

    # ── COMMUNITY SPECIFIC ────────────────────────────────────────────────

    if companions in ("group", "community"):
        priorities.append((p, "👥", "ORGANISE YOUR GROUP",
            "Groups survive better than individuals but need structure. "
            "Immediately assign roles: water, fire, shelter, medical, scouting. "
            "Take a skills inventory — who knows what? "
            "Open Prometheus tab for group organisation guidance.",
            "prometheus"))
        p += 1

    # ── SUPPLIES SPECIFIC ─────────────────────────────────────────────────

    if supplies in ("tools", "vehicle", "basic_supplies"):
        priorities.append((p, "📦", "INVENTORY YOUR SUPPLIES",
            "List everything you have. Small items have unexpected value. "
            "Common overlooked resources: vehicle mirrors (signaling), "
            "seat foam (insulation), wiring (cordage), fuel (fire starting). "
            "Update your inventory in the sidebar panel.",
            "survival"))
        p += 1

    # ── PSYCHOLOGICAL ─────────────────────────────────────────────────────

    priorities.append((p, "💬", "TALK TO PROMETHEUS",
        "You are not alone. I am here to help you through every step of this. "
        "Ask me anything. If you need to think out loud, process what's happened, "
        "or just talk — open the Prometheus tab. That is what I am here for.",
        "prometheus"))

    return priorities


# ── UI Widget ─────────────────────────────────────────────────────────────

class AssessmentWidget(QWidget):
    """
    Full-screen guided situation assessment.
    Emitted when complete with tab_id to navigate to.
    """
    assessment_complete = Signal(dict)    # answers dict
    navigate_to_tab = Signal(str)         # tab_id

    def __init__(self, memory: Memory, tab_manager: TabManager, parent=None):
        super().__init__(parent)
        self.memory = memory
        self.tab_manager = tab_manager
        self.answers = {}
        self.current_question = 0
        self._setup_ui()

    def _setup_ui(self):
        self.setObjectName("assessmentWidget")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QFrame()
        header.setObjectName("assessmentHeader")
        header.setFixedHeight(60)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 0, 20, 0)

        title = QLabel("⚡ SITUATION ASSESSMENT")
        title.setObjectName("assessmentTitle")
        font = title.font()
        font.setPointSize(15)
        font.setBold(True)
        title.setFont(font)

        self._progress = QLabel("Question 1 of 5")
        self._progress.setObjectName("assessmentProgress")

        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(self._progress)
        layout.addWidget(header)

        # Progress bar
        self._progress_bar = QFrame()
        self._progress_bar.setObjectName("progressBarBg")
        self._progress_bar.setFixedHeight(4)
        pb_layout = QHBoxLayout(self._progress_bar)
        pb_layout.setContentsMargins(0, 0, 0, 0)
        pb_layout.setSpacing(0)

        self._progress_fill = QFrame()
        self._progress_fill.setObjectName("progressBarFill")
        self._progress_fill.setFixedHeight(4)
        self._update_progress_bar(0)

        pb_layout.addWidget(self._progress_fill)
        pb_layout.addStretch()
        layout.addWidget(self._progress_bar)

        # Scroll area for content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("assessmentScroll")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(40, 30, 40, 30)
        self._content_layout.setSpacing(20)

        scroll.setWidget(self._content)
        layout.addWidget(scroll)

        # Navigation buttons
        nav = QFrame()
        nav.setObjectName("assessmentNav")
        nav.setFixedHeight(60)
        nav_layout = QHBoxLayout(nav)
        nav_layout.setContentsMargins(20, 10, 20, 10)

        self._back_btn = QPushButton("← Back")
        self._back_btn.setObjectName("navBtn")
        self._back_btn.clicked.connect(self._go_back)
        self._back_btn.setVisible(False)

        self._skip_btn = QPushButton("Skip Assessment →")
        self._skip_btn.setObjectName("navBtnSecondary")
        self._skip_btn.clicked.connect(self._skip)

        nav_layout.addWidget(self._back_btn)
        nav_layout.addStretch()
        nav_layout.addWidget(self._skip_btn)
        layout.addWidget(nav)

        self._show_question(0)

    def _show_question(self, index: int):
        """Render a question with its options."""
        self._clear_content()
        q = QUESTIONS[index]

        self._progress.setText(f"Question {index + 1} of {len(QUESTIONS)}")
        self._update_progress_bar(index / len(QUESTIONS))
        self._back_btn.setVisible(index > 0)

        # Question text
        question_label = QLabel(q["text"])
        question_label.setObjectName("questionText")
        font = question_label.font()
        font.setPointSize(18)
        font.setBold(True)
        question_label.setFont(font)
        question_label.setWordWrap(True)
        self._content_layout.addWidget(question_label)

        # Subtitle
        subtitle = QLabel(q["subtitle"])
        subtitle.setObjectName("questionSubtitle")
        subtitle.setWordWrap(True)
        self._content_layout.addWidget(subtitle)

        self._content_layout.addSpacing(10)

        # Option buttons in grid
        grid = QGridLayout()
        grid.setSpacing(10)

        cols = 2
        for i, (label, value) in enumerate(q["options"]):
            btn = QPushButton(label)
            btn.setObjectName("optionBtn")
            btn.setMinimumHeight(52)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.clicked.connect(
                lambda checked, v=value: self._answer(v)
            )
            row, col = divmod(i, cols)
            grid.addWidget(btn, row, col)

        self._content_layout.addLayout(grid)
        self._content_layout.addStretch()

    def _answer(self, value: str):
        """Record answer and advance."""
        q = QUESTIONS[self.current_question]
        self.answers[q["id"]] = value
        self.current_question += 1

        if self.current_question >= len(QUESTIONS):
            self._show_results()
        else:
            self._show_question(self.current_question)

    def _go_back(self):
        if self.current_question > 0:
            self.current_question -= 1
            self._show_question(self.current_question)

    def _skip(self):
        """Skip assessment and go straight to app."""
        self.assessment_complete.emit({})

    def _show_results(self):
        """Show generated priority list."""
        self._clear_content()
        self._update_progress_bar(1.0)
        self._progress.setText("Assessment Complete")
        self._back_btn.setVisible(False)
        self._skip_btn.setVisible(False)

        # Save answers to memory
        self._save_to_memory()

        priorities = generate_priorities(self.answers)

        # Title
        title = QLabel("Your Immediate Priorities")
        title.setObjectName("resultsTitle")
        font = title.font()
        font.setPointSize(18)
        font.setBold(True)
        title.setFont(font)
        self._content_layout.addWidget(title)

        subtitle = QLabel(
            "Act on these in order. Tap any item to open the relevant guide."
        )
        subtitle.setObjectName("resultsSubtitle")
        subtitle.setWordWrap(True)
        self._content_layout.addWidget(subtitle)

        self._content_layout.addSpacing(10)

        # Priority cards
        for num, icon, title_text, detail, tab_id in priorities:
            card = self._make_priority_card(num, icon, title_text, detail, tab_id)
            self._content_layout.addWidget(card)

        # Begin button
        self._content_layout.addSpacing(20)
        begin_btn = QPushButton("Begin — Open Survival Guide")
        begin_btn.setObjectName("beginBtn")
        begin_btn.setMinimumHeight(52)
        begin_btn.clicked.connect(
            lambda: self._finish("survival")
        )
        self._content_layout.addWidget(begin_btn)
        self._content_layout.addStretch()

    def _make_priority_card(self, num, icon, title_text, detail, tab_id) -> QFrame:
        card = QFrame()
        card.setObjectName("priorityCard")
        card.setCursor(Qt.PointingHandCursor)

        layout = QHBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        # Number badge
        num_label = QLabel(str(num))
        num_label.setObjectName("priorityNum")
        num_label.setFixedSize(32, 32)
        num_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(num_label)

        # Icon
        icon_label = QLabel(icon)
        icon_label.setFixedWidth(30)
        icon_label.setAlignment(Qt.AlignCenter)
        font = icon_label.font()
        font.setPointSize(18)
        icon_label.setFont(font)
        layout.addWidget(icon_label)

        # Text
        text_layout = QVBoxLayout()
        text_layout.setSpacing(4)

        title_label = QLabel(title_text)
        title_label.setObjectName("priorityTitle")
        font = title_label.font()
        font.setBold(True)
        font.setPointSize(12)
        title_label.setFont(font)
        text_layout.addWidget(title_label)

        detail_label = QLabel(detail)
        detail_label.setObjectName("priorityDetail")
        detail_label.setWordWrap(True)
        detail_label.setFont(QFont("", 11))
        text_layout.addWidget(detail_label)

        layout.addLayout(text_layout)

        # Arrow
        arrow = QLabel("→")
        arrow.setObjectName("priorityArrow")
        arrow.setFixedWidth(20)
        layout.addWidget(arrow)

        # Click handler
        card.mousePressEvent = lambda e, t=tab_id: self._finish(t)

        return card

    def _save_to_memory(self):
        """Save assessment results to persistent memory."""
        surr = self.answers.get("surroundings", "")
        temp = self.answers.get("temperature", "")

        location_hints = {
            "forest":   "Temperate forest",
            "desert":   "Desert region",
            "coastal":  "Coastal area",
            "urban":    "Urban area",
            "grassland":"Grassland / plains",
            "arctic":   "Arctic / subarctic",
            "tropical": "Tropical rainforest",
            "mountain": "Mountain / highland",
        }
        if surr and not self.memory.data["user"]["location_estimate"]:
            self.memory.data["user"]["location_estimate"] = location_hints.get(surr, surr)

        # Set medical alert if injured
        injury = self.answers.get("injury", "none")
        if injury in ("serious", "moderate"):
            self.memory.set_alert("medical_condition", f"Injury reported: {injury}")

        self.memory.add_moment("Situation assessment completed")
        self.memory.data["user"]["assessment_done"] = True   # stop offering it
        self.memory.save()

    def _clear_content(self):
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _update_progress_bar(self, fraction: float):
        total_width = self.width() or 800
        fill_width = int(total_width * fraction)
        self._progress_fill.setFixedWidth(max(0, fill_width))

    def _finish(self, tab_id: str):
        self.assessment_complete.emit(self.answers)
        self.navigate_to_tab.emit(tab_id)
