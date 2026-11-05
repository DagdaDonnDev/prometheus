"""
Sidebar - shows user situation, inventory, alerts.
Collapsible. Updates from memory.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QFrame,
    QPushButton, QScrollArea, QHBoxLayout,
    QLineEdit, QSpinBox
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont

from core.memory import Memory


class SectionHeader(QLabel):
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setObjectName("sectionHeader")
        font = self.font()
        font.setBold(True)
        font.setPointSize(11)
        self.setFont(font)


class InfoRow(QFrame):
    def __init__(self, label: str, value: str = "—", parent=None):
        super().__init__(parent)
        self.setObjectName("infoRow")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        self._label = QLabel(label)
        self._label.setObjectName("infoLabel")
        self._label.setFixedWidth(80)

        self._value = QLabel(value)
        self._value.setObjectName("infoValue")
        self._value.setWordWrap(True)

        layout.addWidget(self._label)
        layout.addWidget(self._value)
        layout.addStretch()

    def set_value(self, value: str):
        self._value.setText(value or "—")


class Sidebar(QWidget):
    def __init__(self, memory: Memory, parent=None):
        super().__init__(parent)
        self.memory = memory
        self.setObjectName("sidebar")
        self._setup_ui()

        # Refresh every 30 seconds
        self._timer = QTimer()
        self._timer.timeout.connect(self.refresh)
        self._timer.start(30000)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("sidebarScroll")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(8, 8, 8, 8)
        content_layout.setSpacing(8)

        # ── Identity ──────────────────────────────
        content_layout.addWidget(SectionHeader("👤 Identity"))

        self._name_row = InfoRow("Name")
        self._day_row = InfoRow("Day")
        self._location_row = InfoRow("Location")
        content_layout.addWidget(self._name_row)
        content_layout.addWidget(self._day_row)
        content_layout.addWidget(self._location_row)

        # Day counter buttons
        day_btns = QHBoxLayout()
        day_btn_minus = QPushButton("-")
        day_btn_minus.setFixedSize(28, 28)
        day_btn_minus.setObjectName("smallBtn")
        day_btn_minus.clicked.connect(self._day_minus)

        self._day_label = QLabel("Day 1")
        self._day_label.setAlignment(Qt.AlignCenter)

        day_btn_plus = QPushButton("+")
        day_btn_plus.setFixedSize(28, 28)
        day_btn_plus.setObjectName("smallBtn")
        day_btn_plus.clicked.connect(self._day_plus)

        day_btns.addWidget(day_btn_minus)
        day_btns.addWidget(self._day_label)
        day_btns.addWidget(day_btn_plus)
        day_btns.setContentsMargins(8, 0, 8, 0)
        content_layout.addLayout(day_btns)

        # ── Alerts ────────────────────────────────
        self._alerts_header = SectionHeader("🚨 Alerts")
        content_layout.addWidget(self._alerts_header)

        self._alert_medical = InfoRow("Medical")
        self._alert_danger = InfoRow("Danger")
        self._alert_shortage = InfoRow("Shortage")
        content_layout.addWidget(self._alert_medical)
        content_layout.addWidget(self._alert_danger)
        content_layout.addWidget(self._alert_shortage)

        # ── Resources ─────────────────────────────
        content_layout.addWidget(SectionHeader("📦 Resources"))

        self._food_row = InfoRow("Food")
        self._water_row = InfoRow("Water")
        self._shelter_row = InfoRow("Shelter")
        self._power_row = InfoRow("Power")
        content_layout.addWidget(self._food_row)
        content_layout.addWidget(self._water_row)
        content_layout.addWidget(self._shelter_row)
        content_layout.addWidget(self._power_row)

        # ── Progress ──────────────────────────────
        content_layout.addWidget(SectionHeader("✅ Progress"))

        self._progress_label = QLabel("Nothing logged yet")
        self._progress_label.setObjectName("progressLabel")
        self._progress_label.setWordWrap(True)
        content_layout.addWidget(self._progress_label)

        content_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)

        self.refresh()

    def refresh(self):
        """Update all sidebar values from memory."""
        u = self.memory.data["user"]
        inv = self.memory.data["inventory"]
        alerts = self.memory.data["alerts"]
        progress = self.memory.data["progress"]

        # Identity
        self._name_row.set_value(u.get("name"))
        day = u.get("day_count", 1)
        self._day_row.set_value(str(day))
        self._day_label.setText(f"Day {day}")
        self._location_row.set_value(u.get("location_estimate"))

        # Alerts
        self._alert_medical.set_value(alerts.get("medical_condition"))
        self._alert_danger.set_value(alerts.get("immediate_danger"))
        self._alert_shortage.set_value(alerts.get("critical_shortage"))

        # Resources
        food = inv.get("food_days")
        self._food_row.set_value(f"~{food} days" if food is not None else None)

        water = inv.get("water_days")
        self._water_row.set_value(f"~{water} days" if water is not None else None)

        self._shelter_row.set_value(inv.get("shelter_status"))
        self._power_row.set_value(inv.get("power_source"))

        # Progress
        completed = progress.get("completed", [])
        in_progress = progress.get("in_progress", [])

        progress_text = ""
        if completed:
            progress_text += "Done: " + ", ".join(completed[-3:])
        if in_progress:
            if progress_text:
                progress_text += "\n"
            progress_text += "In progress: " + ", ".join(in_progress)

        self._progress_label.setText(progress_text or "Nothing logged yet")

    def _day_plus(self):
        self.memory.increment_day()
        self.refresh()

    def _day_minus(self):
        day = self.memory.data["user"]["day_count"]
        if day > 1:
            self.memory.data["user"]["day_count"] -= 1
            self.memory.save()
            self.refresh()
