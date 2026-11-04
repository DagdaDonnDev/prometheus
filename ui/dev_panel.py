"""
Dev Panel
=========
Observability UI showing live trace data for every query.
Toggle with Ctrl+D or via header button.
Shows: intent, retrieval tiers, sufficiency, gate mode, timing.
Also shows pattern analysis and evaluation harness runner.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QScrollArea, QTextEdit,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QTabWidget, QSplitter, QSizePolicy
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont, QColor

from core.tracer import tracer, QueryTrace


# Colours for different modes
MODE_COLORS = {
    "emergency": "#ff4444",
    "safe_mode":  "#ff8800",
    "clarify":    "#ffcc00",
    "cautious":   "#88aaff",
    "direct":     "#44cc44",
    "":           "#888888",
}

SUFFICIENCY_COLORS = {
    "SUFFICIENT":  "#44cc44",
    "WEAK":        "#ffcc00",
    "CONFLICTING": "#ff8800",
    "NONE":        "#ff4444",
}


class TraceRow(QFrame):
    """Single trace displayed as a compact row."""

    def __init__(self, trace: QueryTrace, parent=None):
        super().__init__(parent)
        self.setObjectName("infoRow")
        self.setFixedHeight(56)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        # Mode badge
        mode = trace.gate_mode or "?"
        mode_color = MODE_COLORS.get(mode, "#888")
        mode_lbl = QLabel(mode.upper()[:8])
        mode_lbl.setFixedWidth(70)
        mode_lbl.setAlignment(Qt.AlignCenter)
        mode_lbl.setStyleSheet(
            f"background: {mode_color}22; color: {mode_color}; "
            f"border: 1px solid {mode_color}; border-radius: 4px; "
            f"font-size: 10px; font-weight: bold; padding: 2px;"
        )
        layout.addWidget(mode_lbl)

        # Intent
        intent_lbl = QLabel(trace.intent[:12])
        intent_lbl.setObjectName("infoLabel")
        intent_lbl.setFixedWidth(80)
        layout.addWidget(intent_lbl)

        # Query preview
        query_lbl = QLabel(trace.query_preview[:50] + ("…" if len(trace.query_preview) > 50 else ""))
        query_lbl.setObjectName("skillName")
        query_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(query_lbl)

        # Sources
        suff = trace.sufficiency.verdict if trace.sufficiency else "?"
        suff_color = SUFFICIENCY_COLORS.get(suff, "#888")
        chunks = trace.retrieval.total_chunks if trace.retrieval else 0
        top_score = trace.retrieval.top_score if trace.retrieval else 0
        src_lbl = QLabel(f"{suff[:4]} {chunks}src {top_score:.0f}%")
        src_lbl.setFixedWidth(100)
        src_lbl.setStyleSheet(f"color: {suff_color}; font-size: 10px;")
        layout.addWidget(src_lbl)

        # Timing
        ms_lbl = QLabel(f"{trace.response_ms}ms")
        ms_lbl.setObjectName("infoLabel")
        ms_lbl.setFixedWidth(50)
        ms_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(ms_lbl)

        # Tab
        tab_lbl = QLabel(trace.tab_id[:8])
        tab_lbl.setObjectName("skillTab")
        tab_lbl.setFixedWidth(60)
        tab_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(tab_lbl)


class DevPanel(QWidget):
    """
    Full observability panel.
    Three tabs: Live Traces, Pattern Analysis, Eval Harness.
    """

    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("devPanel")
        self.setMinimumSize(700, 500)
        self._setup_ui()

        # Auto-refresh every 2 seconds — only when visible
        self._timer = QTimer()
        self._timer.timeout.connect(self._refresh)
        self._timer.start(2000)

    def showEvent(self, event):
        self._timer.start(2000)
        super().showEvent(event)

    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Header
        header = QFrame()
        header.setObjectName("header")
        header.setFixedHeight(44)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 0, 16, 0)

        title = QLabel("🔬 Dev Panel — Query Observability")
        title.setObjectName("headerTitle")
        font = title.font()
        font.setPointSize(12)
        font.setBold(True)
        title.setFont(font)

        self._status = QLabel("")
        self._status.setObjectName("assessmentProgress")

        clear_btn = QPushButton("Clear")
        clear_btn.setObjectName("navBtn")
        clear_btn.setFixedSize(60, 28)
        clear_btn.clicked.connect(self._clear)

        close_btn = QPushButton("✕")
        close_btn.setObjectName("navBtn")
        close_btn.setFixedSize(28, 28)
        close_btn.clicked.connect(self.closed.emit)

        hl.addWidget(title)
        hl.addStretch()
        hl.addWidget(self._status)
        hl.addWidget(clear_btn)
        hl.addWidget(close_btn)
        layout.addWidget(header)

        # Tabs
        tabs = QTabWidget()
        tabs.setObjectName("tabBar")

        # ── Live traces ────────────────────────────────────────────────────
        traces_widget = QWidget()
        traces_layout = QVBoxLayout(traces_widget)
        traces_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("chatScroll")

        self._traces_content = QWidget()
        self._traces_layout = QVBoxLayout(self._traces_content)
        self._traces_layout.setContentsMargins(8, 8, 8, 8)
        self._traces_layout.setSpacing(4)
        self._traces_layout.addStretch()

        scroll.setWidget(self._traces_content)
        traces_layout.addWidget(scroll)
        self._traces_scroll = scroll

        tabs.addTab(traces_widget, "📊 Live Traces")

        # ── Pattern analysis ───────────────────────────────────────────────
        patterns_widget = QWidget()
        patterns_layout = QVBoxLayout(patterns_widget)
        patterns_layout.setContentsMargins(12, 12, 12, 12)

        self._patterns_text = QTextEdit()
        self._patterns_text.setObjectName("docList")
        self._patterns_text.setReadOnly(True)
        self._patterns_text.setFont(QFont("Courier", 10))
        patterns_layout.addWidget(self._patterns_text)

        tabs.addTab(patterns_widget, "📈 Patterns")

        # ── Eval harness ───────────────────────────────────────────────────
        eval_widget = QWidget()
        eval_layout = QVBoxLayout(eval_widget)
        eval_layout.setContentsMargins(12, 12, 12, 12)
        eval_layout.setSpacing(8)

        eval_info = QLabel(
            "Run the deterministic evaluation harness against the current system.\n"
            "Tests intent routing, mode selection, and source handling."
        )
        eval_info.setObjectName("noteLabel")
        eval_info.setWordWrap(True)
        eval_layout.addWidget(eval_info)

        run_btn = QPushButton("▶ Run Evaluation Suite")
        run_btn.setObjectName("primaryBtn")
        run_btn.clicked.connect(self._run_eval)
        eval_layout.addWidget(run_btn)

        self._eval_output = QTextEdit()
        self._eval_output.setObjectName("docList")
        self._eval_output.setReadOnly(True)
        self._eval_output.setFont(QFont("Courier", 9))
        eval_layout.addWidget(self._eval_output)

        tabs.addTab(eval_widget, "🧪 Eval")

        layout.addWidget(tabs)
        self._tabs = tabs

    def _refresh(self):
        """Update traces display."""
        traces = tracer.recent_traces(30)
        patterns = tracer.analyse_patterns()

        # Update status
        total = patterns.get("total_queries", 0)
        safe_rate = patterns.get("safe_mode_rate", 0) * 100
        self._status.setText(
            f"{total} queries | safe_mode: {safe_rate:.0f}%"
        )

        # Rebuild trace list if changed
        current_count = self._traces_layout.count() - 1  # -1 for stretch
        if len(traces) != current_count:
            while self._traces_layout.count() > 1:
                item = self._traces_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

            for trace in reversed(traces):  # newest first
                row = TraceRow(trace)
                self._traces_layout.insertWidget(0, row)

        # Update patterns
        if patterns and self._tabs.currentIndex() == 1:
            lines = ["PATTERN ANALYSIS — last {} queries\n".format(
                patterns.get("total_queries", 0)
            )]
            lines.append("=" * 50)

            metrics = [
                ("Safe mode rate",       "safe_mode_rate",      "%",   True),
                ("Clarify rate",         "clarify_rate",        "%",   False),
                ("No sources rate",      "no_sources_rate",     "%",   True),
                ("Weak sources rate",    "weak_sources_rate",   "%",   True),
                ("Conflict rate",        "conflict_rate",       "%",   True),
                ("Tier 3 usage rate",    "tier3_usage_rate",    "%",   False),
                ("Avg response time",    "avg_response_ms",     "ms",  False),
                ("Avg top confidence",   "avg_top_confidence",  "%",   False),
                ("Emergency count",      "emergency_count",     "",    False),
                ("Redirect rate",        "redirect_rate",       "%",   False),
            ]

            for label, key, unit, warn_high in metrics:
                val = patterns.get(key, 0)
                if unit == "%":
                    display = f"{val*100:.1f}%"
                elif unit == "ms":
                    display = f"{val:.0f}ms"
                else:
                    display = str(int(val))

                # Flag concerning values
                flag = ""
                if warn_high and unit == "%" and val > 0.3:
                    flag = " ⚠"
                elif key == "avg_top_confidence" and val < 60:
                    flag = " ⚠"

                lines.append(f"  {label:<25} {display}{flag}")

            self._patterns_text.setPlainText("\n".join(lines))

    def _clear(self):
        tracer.clear()
        while self._traces_layout.count() > 1:
            item = self._traces_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _run_eval(self):
        """Run the evaluation harness."""
        from core.eval_harness import EvalHarness
        self._eval_output.setPlainText("Running evaluation suite...\n")

        def on_result(line: str):
            current = self._eval_output.toPlainText()
            self._eval_output.setPlainText(current + line + "\n")

        harness = EvalHarness(callback=on_result)
        harness.run_all()
