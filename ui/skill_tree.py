"""
Skill Tree and Progress Tracker
================================
Visual civilization rebuild tracker.
Shows what you've achieved and what's unlocked next.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QFrame, QSizePolicy,
    QCheckBox, QToolTip
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QCursor

from core.memory import Memory


# ── Skill tree data ────────────────────────────────────────────────────────

SKILL_TREE = [
    {
        "stage": "Stage 0",
        "name": "Immediate Survival",
        "color": "#8B0000",
        "days": "Day 1-3",
        "skills": [
            {"id": "s0_water",    "name": "Find and purify water",         "requires": [],              "tab": "survival"},
            {"id": "s0_shelter",  "name": "Build emergency shelter",       "requires": [],              "tab": "survival"},
            {"id": "s0_fire",     "name": "Start fire without matches",    "requires": [],              "tab": "survival"},
            {"id": "s0_food",     "name": "Identify safe food sources",    "requires": [],              "tab": "farming"},
            {"id": "s0_medical",  "name": "Basic wound care",             "requires": [],              "tab": "medical"},
            {"id": "s0_navigate", "name": "Determine cardinal directions", "requires": [],              "tab": "navigation"},
        ]
    },
    {
        "stage": "Stage 1",
        "name": "Stone Age",
        "color": "#8B4513",
        "days": "Week 1-2",
        "skills": [
            {"id": "s1_tools",    "name": "Make stone tools (flint knapping)",  "requires": ["s0_fire"],    "tab": "build"},
            {"id": "s1_cordage",  "name": "Make rope and cordage",              "requires": [],             "tab": "build"},
            {"id": "s1_trap",     "name": "Set snares and deadfall traps",      "requires": ["s1_cordage"], "tab": "farming"},
            {"id": "s1_bow",      "name": "Make bow and arrows",                "requires": ["s1_cordage"], "tab": "build"},
            {"id": "s1_preserve", "name": "Smoke and dry food",                 "requires": ["s0_fire"],    "tab": "farming"},
            {"id": "s1_medicine", "name": "Basic herbal medicine",              "requires": [],             "tab": "medical"},
            {"id": "s1_hide",     "name": "Process animal hide",                "requires": ["s1_tools"],   "tab": "build"},
        ]
    },
    {
        "stage": "Stage 2",
        "name": "Neolithic",
        "color": "#B8860B",
        "days": "Weeks 2-8",
        "skills": [
            {"id": "s2_pottery",  "name": "Make and fire clay pottery",        "requires": ["s0_fire"],              "tab": "build"},
            {"id": "s2_crops",    "name": "Plant first crops",                 "requires": ["s0_water"],             "tab": "farming"},
            {"id": "s2_animals",  "name": "Begin animal domestication",        "requires": ["s2_crops"],             "tab": "farming"},
            {"id": "s2_shelter2", "name": "Build permanent shelter",           "requires": ["s1_tools", "s1_cordage"],"tab": "build"},
            {"id": "s2_ferment",  "name": "Fermentation (food + drink)",       "requires": ["s2_pottery"],           "tab": "farming"},
            {"id": "s2_soap",     "name": "Make soap from ash and fat",        "requires": ["s0_fire"],              "tab": "chemistry"},
            {"id": "s2_loom",     "name": "Spin and weave textiles",           "requires": ["s1_cordage"],           "tab": "build"},
            {"id": "s2_candle",   "name": "Make candles or oil lamps",         "requires": ["s2_animals"],           "tab": "build"},
        ]
    },
    {
        "stage": "Stage 3",
        "name": "Bronze Age",
        "color": "#CD7F32",
        "days": "Months 2-6",
        "skills": [
            {"id": "s3_charcoal", "name": "Charcoal production (earth kiln)", "requires": ["s0_fire"],              "tab": "chemistry"},
            {"id": "s3_copper",   "name": "Smelt copper from ore",            "requires": ["s3_charcoal"],          "tab": "chemistry"},
            {"id": "s3_bronze",   "name": "Make bronze (copper + tin)",       "requires": ["s3_copper"],            "tab": "chemistry"},
            {"id": "s3_bellows",  "name": "Build forge bellows",              "requires": ["s1_hide"],              "tab": "build"},
            {"id": "s3_casting",  "name": "Cast metal in clay moulds",        "requires": ["s3_copper", "s2_pottery"],"tab": "chemistry"},
            {"id": "s3_wheel",    "name": "Make wheel and axle",              "requires": ["s2_shelter2"],          "tab": "build"},
            {"id": "s3_irrigate", "name": "Build irrigation channels",        "requires": ["s3_wheel"],             "tab": "farming"},
            {"id": "s3_beehive",  "name": "Keep bees (honey + wax)",          "requires": ["s2_crops"],             "tab": "farming"},
        ]
    },
    {
        "stage": "Stage 4",
        "name": "Iron Age",
        "color": "#708090",
        "days": "Months 4-12",
        "skills": [
            {"id": "s4_iron",     "name": "Smelt iron (bloomery furnace)",    "requires": ["s3_bellows", "s3_charcoal"], "tab": "chemistry"},
            {"id": "s4_steel",    "name": "Make steel (iron + carbon)",       "requires": ["s4_iron"],                  "tab": "chemistry"},
            {"id": "s4_tools2",   "name": "Forge iron tools and weapons",     "requires": ["s4_iron"],                  "tab": "build"},
            {"id": "s4_mill",     "name": "Build water or wind mill",         "requires": ["s3_wheel", "s2_shelter2"],  "tab": "build"},
            {"id": "s4_plow",     "name": "Iron plough — large scale farming","requires": ["s4_tools2"],                "tab": "farming"},
            {"id": "s4_writing",  "name": "Writing system for records",       "requires": [],                           "tab": "prometheus"},
            {"id": "s4_glass",    "name": "Make glass (sand + ash + heat)",   "requires": ["s3_charcoal"],              "tab": "chemistry"},
            {"id": "s4_roads",    "name": "Build roads and bridges",          "requires": ["s4_tools2"],                "tab": "build"},
        ]
    },
    {
        "stage": "Stage 5",
        "name": "Medieval",
        "color": "#4682B4",
        "days": "Year 1-2",
        "skills": [
            {"id": "s5_lenses",   "name": "Grind lenses (glasses, optics)", "requires": ["s4_glass"],              "tab": "electronics"},
            {"id": "s5_paper",    "name": "Make paper from plant fibre",    "requires": ["s4_writing"],            "tab": "build"},
            {"id": "s5_printing", "name": "Movable type printing press",    "requires": ["s5_paper", "s4_tools2"], "tab": "build"},
            {"id": "s5_distill",  "name": "Distillation (alcohol, medicine)","requires": ["s2_ferment", "s2_pottery"],"tab": "chemistry"},
            {"id": "s5_gunpowder","name": "Gunpowder (mining, defense)",    "requires": ["s3_charcoal"],           "tab": "chemistry"},
            {"id": "s5_compass",  "name": "Make magnetic compass",          "requires": [],                        "tab": "navigation"},
            {"id": "s5_clock",    "name": "Build pendulum clock",           "requires": ["s4_tools2"],             "tab": "electronics"},
            {"id": "s5_antibio",  "name": "Penicillin from bread mould",    "requires": ["s5_distill"],            "tab": "medical"},
        ]
    },
    {
        "stage": "Stage 6",
        "name": "Industrial",
        "color": "#2E8B57",
        "days": "Years 2-5",
        "skills": [
            {"id": "s6_steam",    "name": "Build steam engine",             "requires": ["s4_steel", "s5_clock"],  "tab": "electronics"},
            {"id": "s6_lathe",    "name": "Precision machining (lathe)",    "requires": ["s6_steam"],              "tab": "build"},
            {"id": "s6_cement",   "name": "Make cement and concrete",       "requires": ["s4_iron"],               "tab": "build"},
            {"id": "s6_fertilize","name": "Fertiliser production",          "requires": ["s6_steam"],              "tab": "farming"},
            {"id": "s6_photo",    "name": "Photography (silver salts)",     "requires": ["s5_lenses"],             "tab": "chemistry"},
            {"id": "s6_telegraph","name": "Build telegraph system",         "requires": ["s6_steam"],              "tab": "electronics"},
        ]
    },
    {
        "stage": "Stage 7",
        "name": "Electrical Age",
        "color": "#F0A500",
        "days": "Years 5-10",
        "skills": [
            {"id": "s7_generator","name": "Build electrical generator",     "requires": ["s4_steel"],             "tab": "electronics"},
            {"id": "s7_battery",  "name": "Build lead-acid battery",        "requires": ["s7_generator"],         "tab": "electronics"},
            {"id": "s7_motor",    "name": "Build electric motor",           "requires": ["s7_generator"],         "tab": "electronics"},
            {"id": "s7_radio",    "name": "Build spark gap radio",          "requires": ["s7_generator"],         "tab": "electronics"},
            {"id": "s7_solar",    "name": "Wire salvaged solar panels",     "requires": ["s7_battery"],           "tab": "electronics"},
            {"id": "s7_lighting", "name": "Electric lighting system",       "requires": ["s7_generator"],         "tab": "electronics"},
        ]
    },
]


class SkillCard(QFrame):
    toggled = Signal(str, bool)  # skill_id, completed

    def __init__(self, skill: dict, completed: bool, unlocked: bool, tab_id: str, parent=None):
        super().__init__(parent)
        self.skill_id = skill["id"]
        self.completed = completed
        self.unlocked = unlocked
        self.tab_id = skill.get("tab", "survival")

        self.setObjectName("skillCard")
        self.setFixedHeight(40)
        self.setCursor(Qt.PointingHandCursor if unlocked else Qt.ForbiddenCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        self._check = QCheckBox()
        self._check.setChecked(completed)
        self._check.setEnabled(unlocked)
        self._check.toggled.connect(lambda c: self.toggled.emit(self.skill_id, c))
        layout.addWidget(self._check)

        name = QLabel(skill["name"])
        name.setObjectName("skillName" if unlocked else "skillNameLocked")
        name.setWordWrap(False)
        layout.addWidget(name)
        layout.addStretch()

        if not unlocked:
            lock = QLabel("🔒")
            lock.setFixedWidth(20)
            layout.addWidget(lock)

        if skill.get("tab"):
            tab_label = QLabel(skill["tab"])
            tab_label.setObjectName("skillTab")
            tab_label.setFixedWidth(70)
            tab_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            layout.addWidget(tab_label)

        self._update_style()

    def _update_style(self):
        if self.completed:
            self.setObjectName("skillCardDone")
        elif self.unlocked:
            self.setObjectName("skillCard")
        else:
            self.setObjectName("skillCardLocked")
        self.style().unpolish(self)
        self.style().polish(self)


class SkillTreeWidget(QWidget):
    navigate_to_tab = Signal(str)

    def __init__(self, memory: Memory, parent=None):
        super().__init__(parent)
        self.memory = memory
        self._completed = set(
            memory.data.get("progress", {}).get("completed", [])
        )
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Header
        header = QFrame()
        header.setObjectName("header")
        header.setFixedHeight(50)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 0, 16, 0)

        title = QLabel("🌱 Civilization Rebuild Tracker")
        title.setObjectName("headerTitle")
        font = title.font()
        font.setPointSize(14)
        font.setBold(True)
        title.setFont(font)

        self._stats_label = QLabel("")
        self._stats_label.setObjectName("assessmentProgress")

        hl.addWidget(title)
        hl.addStretch()
        hl.addWidget(self._stats_label)
        layout.addWidget(header)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("chatScroll")

        content = QWidget()
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(12, 12, 12, 12)
        self._content_layout.setSpacing(12)

        self._build_tree()

        self._content_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)

        self._update_stats()

    def _build_tree(self):
        for stage_data in SKILL_TREE:
            self._content_layout.addWidget(
                self._make_stage(stage_data)
            )

    def _make_stage(self, stage_data: dict) -> QFrame:
        frame = QFrame()
        frame.setObjectName("stageCard")
        # The stage's colour is a bar on the card's edge, never the text
        frame.setStyleSheet(f"#stageCard {{ border-left: 4px solid {stage_data['color']}; }}")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(6)

        # Stage header
        header_row = QHBoxLayout()

        stage_label = QLabel(f"{stage_data['stage']}: {stage_data['name']}")
        stage_label.setObjectName("stageTitle")
        font = stage_label.font()
        font.setPointSize(11)
        font.setBold(True)
        stage_label.setFont(font)

        days_label = QLabel(stage_data["days"])
        days_label.setObjectName("infoLabel")

        # Count completed in this stage
        stage_skills = stage_data["skills"]
        done = sum(1 for s in stage_skills if s["id"] in self._completed)
        count_label = QLabel(f"{done} of {len(stage_skills)} done")
        count_label.setObjectName("stageCount")

        header_row.addWidget(stage_label)
        header_row.addStretch()
        header_row.addWidget(days_label)
        header_row.addSpacing(8)
        header_row.addWidget(count_label)
        layout.addLayout(header_row)

        # Skills
        for skill in stage_skills:
            completed = skill["id"] in self._completed
            unlocked = self._is_unlocked(skill)
            card = SkillCard(skill, completed, unlocked, skill.get("tab", ""))
            card.toggled.connect(self._on_skill_toggled)
            layout.addWidget(card)

        return frame

    def _is_unlocked(self, skill: dict) -> bool:
        """Check if all requirements are completed."""
        return all(req in self._completed for req in skill.get("requires", []))

    def _on_skill_toggled(self, skill_id: str, completed: bool):
        if completed:
            self._completed.add(skill_id)
        else:
            self._completed.discard(skill_id)

        # Save to memory
        self.memory.data["progress"]["completed"] = list(self._completed)
        self.memory.save()

        # Rebuild tree to update locked states
        while self._content_layout.count() > 1:
            item = self._content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for stage_data in SKILL_TREE:
            self._content_layout.insertWidget(
                self._content_layout.count() - 1,
                self._make_stage(stage_data)
            )

        self._update_stats()

    def _update_stats(self):
        total = sum(len(s["skills"]) for s in SKILL_TREE)
        done = len(self._completed)
        pct = int(done / total * 100) if total > 0 else 0
        self._stats_label.setText(f"{done}/{total} skills ({pct}%)")
