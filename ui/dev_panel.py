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
from core.platform_info import PHONE_LAYOUT


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


def speak_start_colour(ms: int) -> str:
    """Bar colour for speak-start time: green <500ms, amber <800ms, red above."""
    if not ms:
        return "#555555"
    if ms < 500:
        return "#44cc44"
    if ms < 800:
        return "#ffcc00"
    return "#ff4444"


def colour_bar(colour: str, width: int = 4, height: int = 36) -> QFrame:
    """Small solid bar — colour is shown here, never on text."""
    bar = QFrame()
    bar.setFixedSize(width, height)
    bar.setStyleSheet(f"background: {colour}; border: none; border-radius: 2px;")
    return bar


class TraceRow(QFrame):
    """
    Single trace displayed as a compact row.
    Left border colour = response mode. Small bars = source sufficiency
    and speak-start speed. All text stays neutral.
    """

    def __init__(self, trace: QueryTrace, parent=None):
        super().__init__(parent)
        self.setObjectName("traceRow")
        self.setFixedHeight(56)

        mode = trace.gate_mode or "?"
        mode_color = MODE_COLORS.get(mode, "#888")
        self.setStyleSheet(f"#traceRow {{ border-left: 4px solid {mode_color}; }}")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        # Mode and intent
        mode_lbl = QLabel(f"{mode.upper()[:9]}\n{trace.intent[:12]}")
        mode_lbl.setFixedWidth(84)
        layout.addWidget(mode_lbl)

        # Path — knowledge (RAG) or training (derivation)
        path_lbl = QLabel("🧮 derive" if trace.path == "training" else "📚 lookup")
        path_lbl.setObjectName("traceMeta")
        path_lbl.setFixedWidth(70)
        path_lbl.setToolTip(trace.training_status or "Knowledge Path")
        layout.addWidget(path_lbl)

        # Query preview
        preview = trace.query_preview[:50] + ("…" if len(trace.query_preview) > 50 else "")
        query_lbl = QLabel(preview)
        query_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(query_lbl)

        # Sources — bar shows sufficiency
        suff = trace.sufficiency.verdict if trace.sufficiency else "?"
        chunks = trace.retrieval.total_chunks if trace.retrieval else 0
        top_score = trace.retrieval.top_score if trace.retrieval else 0
        layout.addWidget(colour_bar(SUFFICIENCY_COLORS.get(suff, "#888")))
        src_lbl = QLabel(f"{suff[:4]} {chunks}src\n{top_score:.0f}%")
        src_lbl.setObjectName("traceMeta")
        src_lbl.setFixedWidth(70)
        layout.addWidget(src_lbl)

        # Timing — speak-start is the headline, full completion secondary
        layout.addWidget(colour_bar(speak_start_colour(trace.first_token_ms)))
        speak_lbl = QLabel(f"🔊 {trace.first_token_ms}ms")
        f = speak_lbl.font()
        f.setBold(True)
        speak_lbl.setFont(f)
        speak_lbl.setFixedWidth(78)
        speak_lbl.setToolTip("Speak-start: when the first words reached the voice")
        layout.addWidget(speak_lbl)

        done_lbl = QLabel(f"✓ {trace.response_ms}ms")
        done_lbl.setObjectName("traceMeta")
        done_lbl.setFixedWidth(72)
        done_lbl.setToolTip("Full completion")
        layout.addWidget(done_lbl)

        # Tab
        tab_lbl = QLabel(trace.tab_id[:12])
        tab_lbl.setObjectName("traceMeta")
        tab_lbl.setFixedWidth(78)
        tab_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(tab_lbl)


class DevPanel(QWidget):
    """
    Full observability panel.
    Three tabs: Live Traces, Pattern Analysis, Eval Harness.
    """

    closed = Signal()

    def __init__(self, parent=None, training_graph=None):
        super().__init__(parent)
        self._graph = training_graph
        self.setObjectName("devPanel")
        if not PHONE_LAYOUT:
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
        clear_btn.setFixedSize(72, 28)
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

        # ── Training graph ─────────────────────────────────────────────────
        train_widget = QWidget()
        train_layout = QVBoxLayout(train_widget)
        train_layout.setContentsMargins(12, 12, 12, 12)
        train_layout.setSpacing(8)

        train_info = QLabel(
            "Concepts the Training Path can derive. Tier 1 are locked laws.\n"
            "A concept is usable as a building block once it reaches 50%."
        )
        train_info.setObjectName("noteLabel")
        train_info.setWordWrap(True)
        train_layout.addWidget(train_info)

        self._train_table = QTableWidget(0, 5)
        self._train_table.setHorizontalHeaderLabels(
            ["Concept", "Tab", "Tier", "Confidence", "Status"]
        )
        header = self._train_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        self._train_table.verticalHeader().setVisible(False)
        self._train_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._train_table.setEditTriggers(QTableWidget.NoEditTriggers)
        train_layout.addWidget(self._train_table)

        train_btns = QHBoxLayout()
        release_btn = QPushButton("Release selected from hold")
        release_btn.setObjectName("navBtn")
        release_btn.clicked.connect(self._release_selected)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setObjectName("navBtn")
        refresh_btn.clicked.connect(self._refresh_training)
        train_btns.addWidget(release_btn)
        train_btns.addWidget(refresh_btn)
        train_btns.addStretch()
        train_layout.addLayout(train_btns)

        tabs.addTab(train_widget, "🧮 Training")
        tabs.currentChanged.connect(
            lambda i: self._refresh_training() if tabs.tabText(i).endswith("Training") else None
        )

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
                ("🔊 Avg speak-start",   "avg_first_token_ms",  "ms",  False),
                ("Slow speak-start >800ms", "slow_speak_start_rate", "%", True),
                ("✓ Avg full response",  "avg_response_ms",     "ms",  False),
                ("Training Path rate",   "training_path_rate",  "%",   False),
                ("Safe mode rate",       "safe_mode_rate",      "%",   True),
                ("Clarify rate",         "clarify_rate",        "%",   False),
                ("No sources rate",      "no_sources_rate",     "%",   True),
                ("Weak sources rate",    "weak_sources_rate",   "%",   True),
                ("Conflict rate",        "conflict_rate",       "%",   True),
                ("Tier 3 usage rate",    "tier3_usage_rate",    "%",   False),
                ("Avg top confidence",   "avg_top_confidence",  "pct", False),
                ("Emergency count",      "emergency_count",     "",    False),
                ("Redirect rate",        "redirect_rate",       "%",   False),
            ]

            for label, key, unit, warn_high in metrics:
                val = patterns.get(key, 0)
                if unit == "%":
                    display = f"{val*100:.1f}%"
                elif unit == "pct":          # already 0–100, not a fraction
                    display = f"{val:.1f}%"
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
                elif key == "avg_first_token_ms" and val > 800:
                    flag = " ⚠ slow — conversations will feel laggy"

                lines.append(f"  {label:<25} {display}{flag}")

            self._patterns_text.setPlainText("\n".join(lines))

    def _refresh_training(self):
        """Fill the training table from the live graph."""
        if not self._graph:
            return
        nodes = sorted(
            self._graph.nodes.values(),
            key=lambda n: (n["tabs"][0], n["tier"], n["name"])
        )
        self._train_table.setRowCount(len(nodes))
        self._train_ids = []
        for row, n in enumerate(nodes):
            if n["quarantined"]:
                status = "on hold — " + n["quarantine_reason"]
            elif n["trust_level"] == "derived":
                status = "trusted result (lemma)"
            elif n["tier"] == 1:
                status = "law (locked)"
            elif self._graph.is_trained(n["id"]):
                status = "trained"
            else:
                missing = self._graph.missing_parents(n["id"])
                status = (
                    "needs: " + ", ".join(self._graph.get(m)["name"] for m in missing)
                    if missing else "untrained"
                )
            cells = [
                n["name"], ", ".join(n["tabs"]), str(n["tier"]),
                f"{n['confidence'] * 100:.0f}%  ({n['success_count']}/{n['verdict_count']} ✓)",
                status,
            ]
            for col, text in enumerate(cells):
                self._train_table.setItem(row, col, QTableWidgetItem(text))
            self._train_ids.append(n["id"])

    def _release_selected(self):
        if not self._graph:
            return
        rows = {i.row() for i in self._train_table.selectedIndexes()}
        for r in rows:
            cid = self._train_ids[r]
            if self._graph.get(cid)["quarantined"]:
                self._graph.release(cid)
        self._refresh_training()

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

        # Training Path unit tests (graph, engine, session) — no Ollama needed
        import io
        import unittest
        on_result("\nTRAINING PATH TESTS")
        stream = io.StringIO()
        try:
            suite = unittest.defaultTestLoader.discover("tests", pattern="test_training.py")
            result = unittest.TextTestRunner(stream=stream, verbosity=1).run(suite)
            on_result(stream.getvalue().strip())
            on_result(
                f"RESULTS: {result.testsRun - len(result.failures) - len(result.errors)} passed, "
                f"{len(result.failures) + len(result.errors)} failed"
            )
        except Exception as e:
            on_result(f"Could not run training tests: {e}")
