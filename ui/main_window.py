"""
Main window for Prometheus.
PySide6 UI - clean, readable, functional.
"""

import os
from datetime import datetime, date
from typing import Optional

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QStatusBar, QLabel, QPushButton,
    QScrollArea, QFrame, QSizePolicy, QDialog,
    QLineEdit, QComboBox, QMessageBox
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QSize
from PySide6.QtGui import QFont, QKeySequence, QShortcut

from core.config import Config
from core.memory import Memory
from core.tabs import TabManager, Tab
from core.rag import KnowledgeBase
from core.llm import LLMEngine
from core.tts import TTSEngine
from core.stt import STTEngine
from core.context_manager import ContextManager

from ui.tab_bar import TabBar
from ui.chat_view import ChatView
from ui.input_bar import InputBar
from ui.sidebar import Sidebar
from ui.workers import LLMWorker, InitWorker
from ui.assessment import AssessmentWidget
from ui.skill_tree import SkillTreeWidget
from ui.quick_access import QuickAccessWidget
from core.backup import BackupManager
from ui.doc_context import DocumentContextWidget
from core.decision_gate import DecisionGate, ResponseMode
from core.map_engine import MapEngine
from ui.map_view import MapWidget
from core.p2p import P2PEngine
from ui.messages_view import MessagesWidget
from core.tabs import suggest_redirect
from core.intent_router import IntentRouter
from core.llm_bounds import build_bounds
from core.sufficiency_gate import SourceSufficiencyGate, Sufficiency
from core.contradiction import ContradictionDetector
from core.memory_filter import MemoryRelevanceFilter
from core.tracer import tracer
from ui.dev_panel import DevPanel


class MainWindow(QMainWindow):
    def __init__(self, config: Config):
        super().__init__()
        self.config = config

        # Core systems
        self.memory = Memory()
        self.tab_manager = TabManager()
        self.knowledge = KnowledgeBase()
        self.llm = LLMEngine(config)
        self.tts = TTSEngine(config)
        self.stt = STTEngine(config)
        self.context_mgr   = ContextManager(self.llm)
        self.backup        = BackupManager()
        self.gate          = DecisionGate()
        self.router        = IntentRouter()
        self.sufficiency   = SourceSufficiencyGate()
        self.contradiction = ContradictionDetector()
        self.mem_filter    = MemoryRelevanceFilter()
        self.map_engine    = MapEngine()
        self.p2p           = P2PEngine(self.memory)
        self.p2p.start()

        # Verify memory files on startup — restore from backup if broken
        ok, broken = self.backup.verify_primary_files()
        if not ok:
            self.backup.restore_latest()

        # State
        self._generating = False
        self._llm_worker: Optional[LLMWorker] = None

        self._setup_ui()
        self._setup_shortcuts()
        self._check_ollama()
        self._start_background_init()

        # Show assessment on first run
        if not self.memory.data["user"]["name"]:
            QTimer.singleShot(500, self._show_assessment)

    def _show_assessment(self):
        """Show situation assessment mode."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Situation Assessment")
        dialog.setMinimumSize(700, 600)
        dialog.resize(800, 700)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)

        assessment = AssessmentWidget(self.memory, self.tab_manager, dialog)
        assessment.assessment_complete.connect(
            lambda answers: dialog.accept()
        )
        assessment.navigate_to_tab.connect(
            lambda tab_id: (dialog.accept(), self._load_tab(tab_id))
        )
        layout.addWidget(assessment)
        dialog.exec()
        self.sidebar.refresh()
        self._day_label.setText(self._get_day_string())

    def _show_skill_tree(self):
        """Show civilization skill tree."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Civilization Rebuild Tracker")
        dialog.setMinimumSize(700, 600)
        dialog.resize(800, 700)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)

        skill_tree = SkillTreeWidget(self.memory, dialog)
        skill_tree.navigate_to_tab.connect(
            lambda tab_id: (dialog.accept(), self._load_tab(tab_id))
        )
        layout.addWidget(skill_tree)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        close_btn.setMaximumWidth(120)
        layout.addWidget(close_btn, 0, Qt.AlignCenter)

        dialog.exec()
        self.sidebar.refresh()

    def _generate_print_reference(self):
        """Generate printable emergency reference PDF."""
        self.status_bar.showMessage("Generating printable reference...", 0)
        try:
            from generate_reference import generate_pdf
            generate_pdf()
            self.status_bar.showMessage(
                "✓ Prometheus_Emergency_Reference.pdf generated — ready to print", 5000
            )
        except Exception as e:
            self.status_bar.showMessage(f"PDF generation failed: {e}", 5000)

    def _show_map(self):
        """Show the world map in a dialog."""
        dialog = QDialog(self)
        dialog.setWindowTitle("World Map")
        dialog.setMinimumSize(900, 600)
        dialog.resize(1100, 700)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)

        map_widget = MapWidget(self.map_engine, dialog)
        map_widget.navigate_to_tab.connect(
            lambda tab_id, query: (
                dialog.accept(),
                self._load_tab(tab_id),
                self._on_send(query)
            )
        )

        # If user has a known location, centre on it
        loc = self.memory.data["user"].get("location_estimate", "")
        if loc:
            results = self.map_engine.search_locations(loc, limit=1)
            if results:
                r = results[0]
                map_widget.go_to_location(r.lat, r.lon)

        layout.addWidget(map_widget)
        dialog.exec()

    def _show_doc_context(self):
        """Show personal document context manager."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Personal Documents")
        dialog.setMinimumSize(600, 550)
        dialog.resize(650, 600)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)

        doc_widget = DocumentContextWidget(dialog)
        doc_widget.documents_updated.connect(
            lambda: self.status_bar.showMessage(
                "✓ Personal documents updated", 3000
            )
        )
        layout.addWidget(doc_widget)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        close_btn.setMaximumWidth(100)
        layout.addWidget(close_btn, 0, Qt.AlignCenter)

        dialog.exec()

    def _setup_ui(self):
        self.setWindowTitle("Prometheus")
        self.setMinimumSize(800, 600)
        self.resize(1100, 750)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Header
        header = self._build_header()
        main_layout.addWidget(header)

        # Tab bar
        self.tab_bar = TabBar(self.tab_manager)
        self.tab_bar.tab_selected.connect(self._on_tab_selected)
        self.tab_bar.tab_add_requested.connect(self._on_add_tab)
        self.tab_bar.quick_access_requested.connect(self._show_quick_access)
        main_layout.addWidget(self.tab_bar)

        # Content area (splitter: chat | sidebar)
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setHandleWidth(1)

        # Chat view
        self.chat_view = ChatView()
        self.splitter.addWidget(self.chat_view)

        # Sidebar (situation, inventory, map)
        self.sidebar = Sidebar(self.memory)
        self.sidebar.setMaximumWidth(280)
        self.sidebar.setMinimumWidth(200)
        self.splitter.addWidget(self.sidebar)

        self.splitter.setSizes([800, 280])
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)

        main_layout.addWidget(self.splitter)

        # Input bar
        self.input_bar = InputBar(self.stt)
        self.input_bar.message_submitted.connect(self._on_send)
        self.input_bar.voice_toggled.connect(self._on_voice_toggle)
        self.input_bar.stop_requested.connect(self._force_stop)
        main_layout.addWidget(self.input_bar)

        # Status bar
        self.status_bar = QStatusBar()
        self.status_bar.setMaximumHeight(24)
        self.setStatusBar(self.status_bar)

        self._day_label = QLabel(self._get_day_string())
        self.status_bar.addPermanentWidget(self._day_label)

        # Load active tab
        self._load_tab(self.tab_manager.active_tab_id)

    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("header")
        header.setFixedHeight(50)

        layout = QHBoxLayout(header)
        layout.setContentsMargins(16, 0, 16, 0)

        title = QLabel("⚡ PROMETHEUS")
        title.setObjectName("headerTitle")
        font = title.font()
        font.setPointSize(16)
        font.setBold(True)
        title.setFont(font)

        layout.addWidget(title)
        layout.addStretch()

        # Sidebar toggle
        self._sidebar_btn = QPushButton("◀ Info")
        self._sidebar_btn.setObjectName("headerBtn")
        self._sidebar_btn.setFixedSize(70, 30)
        self._sidebar_btn.clicked.connect(self._toggle_sidebar)
        layout.addWidget(self._sidebar_btn)

        # Skill tree button
        skill_btn = QPushButton("🌱 Skills")
        skill_btn.setObjectName("headerBtn")
        skill_btn.setFixedSize(70, 30)
        skill_btn.clicked.connect(self._show_skill_tree)
        layout.addWidget(skill_btn)

        # Assessment button
        assess_btn = QPushButton("📋 Assess")
        assess_btn.setObjectName("headerBtn")
        assess_btn.setFixedSize(75, 30)
        assess_btn.clicked.connect(self._show_assessment)
        layout.addWidget(assess_btn)

        # Print reference button
        print_btn = QPushButton("🖨️")
        print_btn.setObjectName("headerBtn")
        print_btn.setFixedSize(30, 30)
        print_btn.setToolTip("Generate printable emergency reference")
        print_btn.clicked.connect(self._generate_print_reference)
        layout.addWidget(print_btn)

        # Map button
        map_btn = QPushButton("🌍")
        map_btn.setObjectName("headerBtn")
        map_btn.setFixedSize(30, 30)
        map_btn.setToolTip("World Map")
        map_btn.clicked.connect(self._show_map)
        layout.addWidget(map_btn)

        # Personal documents button
        docs_btn = QPushButton("📎")
        docs_btn.setObjectName("headerBtn")
        docs_btn.setFixedSize(30, 30)
        docs_btn.setToolTip("Add personal documents as context")
        docs_btn.clicked.connect(self._show_doc_context)
        layout.addWidget(docs_btn)

        # Settings
        settings_btn = QPushButton("⚙")
        settings_btn.setObjectName("headerBtn")
        settings_btn.setFixedSize(30, 30)
        settings_btn.clicked.connect(self._show_settings)
        layout.addWidget(settings_btn)

        # Reset
        reset_btn = QPushButton("↺")
        reset_btn.setObjectName("headerBtn")
        reset_btn.setFixedSize(30, 30)
        reset_btn.setToolTip("Reset memory, tab, or full wipe")
        reset_btn.clicked.connect(self._show_reset_dialog)
        layout.addWidget(reset_btn)

        # Dev panel (Ctrl+D shortcut too)
        self._dev_btn = QPushButton("🔬")
        self._dev_btn.setObjectName("headerBtn")
        self._dev_btn.setFixedSize(30, 30)
        self._dev_btn.setToolTip("Dev panel — query observability (Ctrl+D)")
        self._dev_btn.clicked.connect(self._show_dev_panel)
        layout.addWidget(self._dev_btn)

        return header

    def _setup_shortcuts(self):
        send_shortcut = QShortcut(QKeySequence("Return"), self)
        send_shortcut.activated.connect(self.input_bar.submit)

        dev_shortcut = QShortcut(QKeySequence("Ctrl+D"), self)
        dev_shortcut.activated.connect(self._show_dev_panel)

        stop_shortcut = QShortcut(QKeySequence("Escape"), self)
        stop_shortcut.activated.connect(self._force_stop)

    def _show_dev_panel(self):
        """Show observability dev panel."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Dev Panel")
        dialog.setMinimumSize(800, 500)
        dialog.resize(900, 600)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)
        panel = DevPanel(dialog)
        panel.closed.connect(dialog.accept)
        layout.addWidget(panel)
        dialog.exec()

    def _check_ollama(self):
        if not self.llm.is_available():
            self.status_bar.showMessage(
                "⚠ Ollama not running. Start with: ollama serve", 0
            )
        elif not self.llm.model_available():
            model = self.config.llm_model
            self.status_bar.showMessage(
                f"⚠ Model not found. Run: ollama pull {model}", 0
            )
        else:
            voice_name = self.tts.current_voice_name()
            if voice_name and voice_name != "None":
                self.status_bar.showMessage(f"✓ Ready  ·  Voice: {voice_name}", 5000)
            else:
                self.status_bar.showMessage("✓ Ready", 3000)

    def _start_background_init(self):
        """Initialize heavy components in background after UI shown."""
        self._init_worker = InitWorker(
            self.knowledge,
            self.stt,
            self.config
        )
        self._init_worker.status_update.connect(
            lambda msg: self.status_bar.showMessage(msg, 0)
        )
        self._init_worker.finished.connect(
            lambda: self.status_bar.showMessage("✓ All systems ready", 3000)
        )
        self._init_worker.start()

    def _load_tab(self, tab_id: str):
        """Load a tab into the chat view."""
        tab = self.tab_manager.get_tab(tab_id)
        if not tab:
            return

        self.tab_manager.set_active(tab_id)
        self.tab_bar.set_active(tab_id)

        # Messages tab — show P2P UI instead of chat view
        if tab_id == "messages":
            self._show_messages_panel()
            return

        self._hide_messages_panel()
        self.chat_view.load_tab(tab)

        # Medical tab warning
        if tab_id == "medical":
            self.status_bar.showMessage(
                "⚕ Medical tab — AI provides reference only. "
                "Always verify critical medical decisions with multiple sources.", 8000
            )

        self.setWindowTitle(f"Prometheus — {tab.icon} {tab.name}")

    def _show_messages_panel(self):
        """Show P2P messages panel instead of chat view."""
        if not hasattr(self, '_messages_widget'):
            self._messages_widget = MessagesWidget(self.p2p)
            self.splitter.insertWidget(0, self._messages_widget)

        self.chat_view.hide()
        self._messages_widget.show()
        self.input_bar.hide()
        self.setWindowTitle("Prometheus — 📡 Messages")

        # Update P2P name if user has set their name
        name = self.memory.data["user"].get("name")
        if name:
            self.p2p.identity.set_name(name)

    def _hide_messages_panel(self):
        if hasattr(self, '_messages_widget'):
            self._messages_widget.hide()
        self.chat_view.show()
        self.input_bar.show()

    def _on_tab_selected(self, tab_id: str):
        if self._generating:
            return  # Don't switch while generating
        self._load_tab(tab_id)

    def _on_add_tab(self):
        dialog = NewTabDialog(self)
        if dialog.exec() == QDialog.Accepted:
            name, icon, description = dialog.get_values()
            if name:
                tab = self.tab_manager.add_custom_tab(name, icon, description)
                self.tab_bar.refresh()
                self._load_tab(tab.id)

    def _on_send(self, text: str):
        if not text.strip() or self._generating:
            return

        tab = self.tab_manager.get_active_tab()
        if not tab:
            return

        # Check domain isolation — suggest redirect if query belongs elsewhere
        redirect = suggest_redirect(text, tab.id)
        if redirect and redirect != tab.id:
            redirect_tab = self.tab_manager.get_tab(redirect)
            if redirect_tab:
                self.status_bar.showMessage(
                    f"💡 This looks like a {redirect_tab.icon} {redirect_tab.name} "
                    f"question — tap that tab for better results.", 6000
                )

        # Check for tab suggestion (existing fuzzy match)
        suggested = self.tab_manager.suggest_tab(text)
        if (suggested != tab.id and
                suggested != "prometheus" and
                not self._generating):
            self._maybe_suggest_tab(text, suggested)

        # Add user message
        tab.add_message("user", text)
        self.chat_view.add_message("user", text)
        self.tab_manager.save()

        # Clear input
        self.input_bar.clear_input()

        # Generate response
        self._generate_response(tab, text)

    def _maybe_suggest_tab(self, text: str, suggested_id: str):
        """Show subtle tab suggestion (non-blocking)."""
        suggested_tab = self.tab_manager.get_tab(suggested_id)
        if suggested_tab:
            self.status_bar.showMessage(
                f"💡 This might fit better in {suggested_tab.icon} {suggested_tab.name}",
                4000
            )

    def _generate_response(self, tab: Tab, user_input: str):
        self._generating = True
        self.input_bar.set_generating(True)
        self.tts.stop()

        # ── Start trace ────────────────────────────────────────────────────
        trace = tracer.start(user_input, tab.id)

        # ── Step 1: Intent routing ─────────────────────────────────────────
        routing_plan = self.router.route(user_input, tab.id)
        trace.intent          = routing_plan.intent.value
        trace.is_strict       = routing_plan.is_strict
        trace.allow_discussion = routing_plan.allow_discussion

        # ── Step 2: Tiered RAG retrieval ───────────────────────────────────
        knowledge_context, confidence_note = self.knowledge.search(
            query=user_input,
            routing_plan=routing_plan,
        )

        scores = self.knowledge.get_last_scores()
        trace.retrieval.has_sources    = scores.get("has_sources", False)
        trace.retrieval.conflict       = scores.get("conflict", False)
        trace.retrieval.top_score      = scores.get("top_score", 0)
        trace.retrieval.total_chunks   = scores.get("sources_found", 0)

        # ── Step 3: Source sufficiency gate ────────────────────────────────
        raw_chunks = getattr(self.knowledge, "_last_raw_chunks", [])
        suff_result = self.sufficiency.evaluate(
            scored_chunks=raw_chunks,
            intent=routing_plan.intent,
            routing_plan=routing_plan,
        )
        trace.sufficiency.verdict      = suff_result.verdict.value
        trace.sufficiency.chunk_count  = suff_result.chunk_count
        trace.sufficiency.avg_confidence = suff_result.avg_conf

        # ── Step 4: Contradiction detection ───────────────────────────────
        has_contradiction, contradiction_desc = self.contradiction.detect(
            raw_chunks, tab_id=tab.id
        )
        contradiction_instruction = ""
        if has_contradiction and contradiction_desc:
            contradiction_instruction = self.contradiction.format_contradiction_response(
                contradiction_desc, raw_chunks
            )

        # ── Step 5: Decision gate (with sufficiency override) ──────────────
        plan = self.gate.evaluate(
            query=user_input,
            tab_id=tab.id,
            confidence_score=scores.get("top_score", 75),
            sources_found=suff_result.chunk_count,
            sources_conflict=suff_result.verdict.value == "CONFLICTING",
            context_complete=suff_result.verdict.value == "SUFFICIENT",
        )

        # Apply sufficiency override
        override = self.sufficiency.gate_mode_override(suff_result, plan.mode.value)
        if override:
            from core.decision_gate import ResponseMode as RM
            plan.mode = RM(override)

        trace.gate_mode          = plan.mode.value
        trace.worst_case         = plan.worst_case_assumed
        trace.risk_domains       = plan.risk_domains
        trace.safe_mode_triggered = plan.mode.value == "safe_mode"

        # ── Step 6: LLM bounding ───────────────────────────────────────────
        bounds = build_bounds(
            plan=routing_plan,
            mode=plan.mode,
            has_sources=suff_result.verdict.value == "SUFFICIENT",
            sources_conflict=suff_result.verdict.value == "CONFLICTING",
            tab_id=tab.id,
        )

        if contradiction_instruction:
            bounds = contradiction_instruction + "\n\n" + bounds

        # ── Step 7: Memory relevance filter ───────────────────────────────
        filtered_context = self.mem_filter.filter(
            memory_data=self.memory.data,
            query=user_input,
            tab_id=tab.id,
        )

        map_context = ""
        loc_estimate = self.memory.data["user"].get("location_estimate", "")
        if loc_estimate and self.map_engine.is_ready():
            results = self.map_engine.search_locations(loc_estimate, limit=1)
            if results:
                r = results[0]
                map_context = self.map_engine.context_for_prompt(r.lat, r.lon)

        combined_context = filtered_context
        if map_context:
            combined_context = filtered_context + "\n\n" + map_context

        # ── Step 8: Build system prompt ────────────────────────────────────
        system_prompt = self.llm.build_system_prompt(
            tab_system=tab.system_prompt,
            user_context=combined_context,
            knowledge_context=knowledge_context,
            confidence_note=confidence_note,
            decision_addendum=plan.system_addendum,
            llm_bounds=bounds,
        )
        trace.prompt_chars = len(system_prompt)

        # ── Step 9: UX signals ─────────────────────────────────────────────
        self._show_system_boundary(
            mode=plan.mode.value,
            sufficiency=suff_result.verdict.value,
            has_sources=suff_result.verdict.value != "NONE",
        )

        # ── Step 10: CLARIFY mode — questions only, no LLM ────────────────
        if plan.mode == ResponseMode.CLARIFY and plan.clarifications:
            trace.clarify_triggered = True
            questions = "\n".join(
                f"{i+1}. {q}" for i, q in enumerate(plan.clarifications)
            )
            clarify_response = (
                "Before I can give you the right guidance, I need a few details:\n\n"
                + questions
            )
            self.chat_view.start_assistant_message()
            self.chat_view.append_token(clarify_response)
            self.chat_view.finish_assistant_message()
            tab.add_message("assistant", clarify_response)
            self.tab_manager.save()
            tracer.finish(clarify_response, self.config.model_for_tab(tab.id))
            self._generating = False
            self.input_bar.set_generating(False)
            return

        # ── Step 11: Stream response ───────────────────────────────────────
        messages = self.context_mgr.prepare_messages(tab)

        # Recency bias — ensure the most recent exchange appears last in history
        # (closest to the new query) so the model attends to it most strongly
        if len(messages) >= 4:
            # Find and move the last assistant+user pair to the end
            # messages are already in order, so this is just confirmation
            # that prepare_messages returns them correctly ordered
            pass  # context_manager already returns chronological order

        self.chat_view.start_assistant_message()

        self._llm_worker = LLMWorker(
            self.llm, messages, system_prompt,
            tab_id=tab.id,
            intent=routing_plan.intent.value,
        )
        self._llm_worker.token_received.connect(self._on_token)
        self._llm_worker.response_done.connect(
            lambda full: self._on_response_done(tab, full)
        )
        self._llm_worker.error_occurred.connect(self._on_error)
        self._llm_worker.start()

    def _show_system_boundary(self, mode: str, sufficiency: str, has_sources: bool):
        """Show subtle UX signals about system state."""
        signals = {
            "emergency":   "🚨 Emergency mode — immediate action protocol",
            "safe_mode":   "🛡 Safe mode — limited sources, conservative guidance only",
            "clarify":     "❓ Clarification needed before proceeding",
            "cautious":    "⚠ Caution mode — verify before acting",
        }
        source_note = ""
        if not has_sources:
            source_note = " | No verified sources found"
        elif sufficiency == "CONFLICTING":
            source_note = " | Sources conflict — conservative option shown"
        elif sufficiency == "WEAK":
            source_note = " | Limited sources — verify if possible"

        msg = signals.get(mode, "")
        if msg or source_note:
            self.status_bar.showMessage(
                (msg + source_note).strip(" |"), 6000
            )

    def _on_token(self, token: str):
        """Handle incoming token from LLM stream."""
        self.chat_view.append_token(token)
        self.tts.on_token(token)

    def _on_response_done(self, tab: Tab, full_response: str):
        self.tts.flush()
        images = self.knowledge.get_last_images()
        self.chat_view.finish_assistant_message(image_paths=images if images else None)
        tab.add_message("assistant", full_response)
        tracer.finish(full_response, self.config.model_for_tab(tab.id))
        if self.context_mgr.should_summarize(tab):
            QTimer.singleShot(1000, lambda: self._background_summarize(tab))
        self.tab_manager.save()
        self._generating = False
        self.input_bar.set_generating(False)
        self.status_bar.showMessage("", 0)

    def _background_summarize(self, tab: Tab):
        """Summarize old context in background without blocking UI."""
        self.context_mgr.prepare_messages(tab)
        self.tab_manager.save()

    def _on_error(self, error: str):
        self.chat_view.finish_assistant_message()
        self.chat_view.add_error(error)
        self._generating = False
        self.input_bar.set_generating(False)

    def _on_voice_toggle(self, recording: bool):
        if recording:
            self.stt.start_recording()
            self.status_bar.showMessage("🎤 Listening...", 0)
        else:
            text = self.stt.stop_recording()
            self.status_bar.showMessage("", 0)
            if text:
                self.input_bar.set_text(text)

    def _show_quick_access(self):
        """Show quick access panel as overlay dialog."""
        from PySide6.QtWidgets import QDialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Quick Access")
        dialog.setMinimumSize(500, 650)
        dialog.resize(560, 700)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)

        quick = QuickAccessWidget(dialog)
        quick.action_triggered.connect(
            lambda prompt, tab_id: (
                dialog.accept(),
                self._load_tab(tab_id),
                self._on_send(prompt)
            )
        )
        layout.addWidget(quick)
        dialog.exec()

    def _force_stop(self):
        """
        Force-stop any current generation immediately.
        Resets all state. Used when model is stuck or
        user wants to abort a response in progress.
        """
        # Kill the LLM worker thread
        if self._llm_worker and self._llm_worker.isRunning():
            self._llm_worker.terminate()
            self._llm_worker.wait(500)

        # Clear TTS queue and stop speech
        self.tts.stop()

        # Finish any open bubble cleanly
        self.chat_view.finish_assistant_message()

        # Reset generation state
        self._generating = False
        self.input_bar.set_generating(False)

        self.status_bar.showMessage("⏹ Stopped", 3000)

    def _show_reset_dialog(self):
        """Show reset options dialog."""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel

        dialog = QDialog(self)
        dialog.setWindowTitle("Reset")
        dialog.setFixedSize(380, 280)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("What would you like to reset?")
        font = title.font()
        font.setBold(True)
        font.setPointSize(13)
        title.setFont(font)
        layout.addWidget(title)

        note = QLabel(
            "These actions cannot be undone.\n"
            "A backup is saved automatically before clearing."
        )
        note.setObjectName("noteLabel")
        note.setWordWrap(True)
        layout.addWidget(note)

        # Reset current tab conversation
        tab = self.tab_manager.get_active_tab()
        tab_name = tab.name if tab else "Tab"

        clear_tab_btn = QPushButton(f"🗑  Clear {tab_name} conversation history")
        clear_tab_btn.setObjectName("navBtn")
        clear_tab_btn.clicked.connect(lambda: self._reset_tab(dialog))
        layout.addWidget(clear_tab_btn)

        # Reset all tab conversations
        clear_all_tabs_btn = QPushButton("🗑  Clear all conversation history")
        clear_all_tabs_btn.setObjectName("navBtn")
        clear_all_tabs_btn.clicked.connect(lambda: self._reset_all_tabs(dialog))
        layout.addWidget(clear_all_tabs_btn)

        # Reset user memory (name, day, inventory, situation)
        clear_memory_btn = QPushButton("🧠  Reset user memory")
        clear_memory_btn.setObjectName("navBtn")
        clear_memory_btn.clicked.connect(lambda: self._reset_memory(dialog))
        layout.addWidget(clear_memory_btn)

        # Nuclear — everything
        reset_all_btn = QPushButton("☢  Full reset — wipe everything")
        reset_all_btn.setObjectName("navBtn")
        reset_all_btn.setStyleSheet("color: #ff4444; border-color: #ff4444;")
        reset_all_btn.clicked.connect(lambda: self._reset_everything(dialog))
        layout.addWidget(reset_all_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        layout.addWidget(cancel_btn)

        dialog.exec()

    def _reset_tab(self, parent_dialog=None):
        """Clear current tab's conversation history."""
        tab = self.tab_manager.get_active_tab()
        if not tab:
            return
        self.backup.backup(label="pre_tab_reset")
        self.tab_manager.clear_tab(tab.id)
        self.chat_view.load_tab(tab)
        if parent_dialog:
            parent_dialog.accept()
        self.status_bar.showMessage(
            f"✓ {tab.name} conversation cleared", 3000
        )

    def _reset_all_tabs(self, parent_dialog=None):
        """Clear all tab conversation histories."""
        reply = QMessageBox.question(
            self, "Clear all conversations",
            "Clear history from all tabs?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        self.backup.backup(label="pre_all_tabs_reset")
        for tab in self.tab_manager.tabs:
            self.tab_manager.clear_tab(tab.id)
        tab = self.tab_manager.get_active_tab()
        if tab:
            self.chat_view.load_tab(tab)
        if parent_dialog:
            parent_dialog.accept()
        self.status_bar.showMessage("✓ All conversations cleared", 3000)

    def _reset_memory(self, parent_dialog=None):
        """Reset user memory back to defaults."""
        reply = QMessageBox.question(
            self, "Reset memory",
            "This will clear your name, day count, location, inventory and "
            "situation notes.\n\nConversation history is kept.\n\nContinue?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        self.backup.backup(label="pre_memory_reset")
        self.memory.reset()
        self.sidebar.refresh()
        self._day_label.setText(self._get_day_string())
        if parent_dialog:
            parent_dialog.accept()
        self.status_bar.showMessage("✓ Memory reset — fresh start", 3000)

    def _reset_everything(self, parent_dialog=None):
        """Full reset — memory, all conversations, situation."""
        reply = QMessageBox.question(
            self, "Full reset",
            "⚠ This wipes all memory, all conversations, and all situation data.\n\n"
            "A backup will be saved first. Continue?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        self.backup.backup(label="pre_full_reset")
        self.memory.reset()
        for tab in self.tab_manager.tabs:
            self.tab_manager.clear_tab(tab.id)
        tab = self.tab_manager.get_active_tab()
        if tab:
            self.chat_view.load_tab(tab)
        self.sidebar.refresh()
        self._day_label.setText(self._get_day_string())
        if parent_dialog:
            parent_dialog.accept()
        self.status_bar.showMessage("✓ Full reset complete", 3000)
        # Offer assessment on full reset
        QTimer.singleShot(800, self._show_assessment)
        visible = self.sidebar.isVisible()
        self.sidebar.setVisible(not visible)
        self._sidebar_btn.setText("▶ Info" if visible else "◀ Info")

    def _show_settings(self):
        from ui.settings_dialog import SettingsDialog
        dialog = SettingsDialog(self.config, self.memory, self)
        dialog.exec()
        self.memory.save()
        self.config.save()
        # Apply voice change immediately
        if self.config.tts_voice:
            self.tts.set_voice(self.config.tts_voice)
        self._day_label.setText(self._get_day_string())

    def _get_day_string(self) -> str:
        day = self.memory.data["user"]["day_count"]
        name = self.memory.data["user"]["name"]
        if name:
            return f"  {name} · Day {day}  "
        return f"  Day {day}  "

    def closeEvent(self, event):
        self.tts.shutdown()
        self.p2p.stop()
        self.tab_manager.save()
        self.memory.save()
        self.config.save()
        # Silent backup on every close
        self.backup.backup(label=f"day{self.memory.data['user']['day_count']}")
        event.accept()


class NewTabDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Tab")
        self.setFixedSize(350, 220)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        layout.addWidget(QLabel("Tab name:"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g. My Shelter, Community, Animals")
        layout.addWidget(self.name_input)

        layout.addWidget(QLabel("Icon:"))
        self.icon_combo = QComboBox()
        icons = ["🏠", "👥", "🐾", "🎵", "📖", "⚔️", "🌊", "🏔️", "🔬", "📡", "🛠️", "🌿"]
        self.icon_combo.addItems(icons)
        layout.addWidget(self.icon_combo)

        layout.addWidget(QLabel("What is this tab for?"))
        self.desc_input = QLineEdit()
        self.desc_input.setPlaceholderText("e.g. Managing our livestock and animals")
        layout.addWidget(self.desc_input)

        btns = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        ok_btn = QPushButton("Create Tab")
        ok_btn.clicked.connect(self.accept)
        ok_btn.setObjectName("primaryBtn")
        btns.addWidget(cancel_btn)
        btns.addWidget(ok_btn)
        layout.addLayout(btns)

    def get_values(self):
        return (
            self.name_input.text().strip(),
            self.icon_combo.currentText(),
            self.desc_input.text().strip()
        )
