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
from ui.workers import LLMWorker, InitWorker, TrainingWorker
from ui.assessment import AssessmentWidget
from ui.skill_tree import SkillTreeWidget
from ui.quick_access import QuickAccessWidget
from core.backup import BackupManager
from ui.doc_context import DocumentContextWidget
from core.map_engine import MapEngine
from ui.map_view import MapWidget
from core.p2p import P2PEngine
from ui.messages_view import MessagesWidget
from core.tabs import suggest_redirect
from core.tracer import tracer
from ui.dev_panel import DevPanel
from core.pipeline import QueryPipeline
from core.platform_info import PHONE_LAYOUT
from ui.layout_helpers import size_dialog
from core.training import TrainingGraph, DerivationEngine, TrainingSession, VERDICT_LABELS


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
        self.map_engine    = MapEngine()
        # Decision layers (router, gates, bounds) — shared with Android
        self.pipeline      = QueryPipeline(self.memory, self.knowledge, self.llm, self.map_engine)
        self.p2p           = P2PEngine(self.memory)
        self.p2p.start()

        # Training Path (v22) — first-principles derivation for deductive tabs
        self.training_graph   = TrainingGraph()
        self.training_engine  = DerivationEngine(self.training_graph, self.knowledge, self.llm)
        self.training_session = TrainingSession(self.training_graph)

        # Verify memory files on startup — restore from backup if broken
        ok, broken = self.backup.verify_primary_files()
        if not ok:
            self.backup.restore_latest()

        # State
        self._generating = False
        self._llm_worker: Optional[LLMWorker] = None
        self._training_worker: Optional[TrainingWorker] = None
        self._generation_id = 0   # bumped on every query and on force-stop

        self._setup_ui()
        self._setup_shortcuts()
        self._check_ollama()
        self._start_background_init()

        # First launch: no popup. Each empty tab shows a welcome panel
        # (Survival offers the situation check). The cursor starts in the
        # message box so you can just type.
        QTimer.singleShot(0, self.input_bar.focus_input)

    def _show_assessment(self):
        """Show situation assessment mode."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Situation Assessment")
        size_dialog(dialog, 700, 600, 800, 700)

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
        # Show what the check filled in, and drop the "situation check" card
        if self._has_situation_data() and not PHONE_LAYOUT and not self.sidebar.isVisible():
            self._toggle_sidebar()
        if not self._generating:
            self._load_tab(self.tab_manager.active_tab_id)

    def _show_skill_tree(self):
        """Show civilization skill tree."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Civilization Rebuild Tracker")
        size_dialog(dialog, 700, 600, 800, 700)

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
        size_dialog(dialog, 900, 600, 1100, 700)

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
        size_dialog(dialog, 600, 550, 650, 600)

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
        if not PHONE_LAYOUT:
            self.setMinimumSize(800, 600)
            self.resize(1100, 750)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Header — on a phone the buttons scroll sideways instead of overflowing
        header = self._build_header()
        if PHONE_LAYOUT:
            header_scroll = QScrollArea()
            header_scroll.setWidget(header)
            header_scroll.setWidgetResizable(True)
            header_scroll.setFixedHeight(header.height() + 6)
            header_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            header_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            header_scroll.setFrameShape(QFrame.NoFrame)
            header_scroll.setObjectName("tabScroll")
            main_layout.addWidget(header_scroll)
        else:
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

        # Chat view (welcome panel questions send straight away)
        self.chat_view = ChatView()
        self.chat_view.check_pending = lambda: not self.memory.data["user"].get("assessment_done")
        self.chat_view.suggestion_clicked.connect(self._on_send)
        self.chat_view.assessment_requested.connect(self._show_assessment)
        self.splitter.addWidget(self.chat_view)

        # Sidebar (situation, inventory, map)
        self.sidebar = Sidebar(self.memory)
        self.sidebar.setMaximumWidth(280)
        self.sidebar.setMinimumWidth(200)
        self.splitter.addWidget(self.sidebar)

        self.splitter.setSizes([800, 280])
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)

        # Phone: the situation panel takes the whole width when opened,
        # so start with it closed
        if PHONE_LAYOUT:
            self.sidebar.setMaximumWidth(16777215)
            self.sidebar.hide()
        elif not self._has_situation_data():
            # Desktop: a panel of empty "—" rows is just noise on a fresh start
            self.sidebar.hide()
        self._sidebar_btn.setChecked(self.sidebar.isVisibleTo(self))

        main_layout.addWidget(self.splitter, 1)   # chat takes all spare height

        # Input bar
        self.input_bar = InputBar(self.stt)
        self.input_bar.message_submitted.connect(self._on_send)
        self.input_bar.voice_toggled.connect(self._on_voice_toggle)
        self.input_bar.stop_requested.connect(self._force_stop)
        self.input_bar.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        main_layout.addWidget(self.input_bar)

        # Status bar
        self.status_bar = QStatusBar()
        self.status_bar.setMaximumHeight(24)
        self.setStatusBar(self.status_bar)


        # Load active tab
        self._load_tab(self.tab_manager.active_tab_id)

    def _build_header(self) -> QWidget:
        """
        Header: name and day on the left; the few things people use often
        on the right; everything else in the More menu.
        """
        from PySide6.QtWidgets import QMenu

        header = QFrame()
        header.setObjectName("header")
        header.setFixedHeight(52)

        layout = QHBoxLayout(header)
        layout.setContentsMargins(16, 0, 12, 0)
        layout.setSpacing(4)

        # Left: name and day
        title = QLabel("P" if PHONE_LAYOUT else "PROMETHEUS")
        title.setObjectName("headerTitle")
        font = title.font()
        font.setPointSize(13)
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)

        self._day_label = QLabel(self._get_day_string())
        self._day_label.setObjectName("headerDay")
        layout.addWidget(self._day_label)
        layout.addStretch()

        def header_button(text, tip, slot, checkable=False):
            btn = QPushButton(text)
            btn.setObjectName("headerBtn")
            btn.setToolTip(tip)
            btn.setCheckable(checkable)
            btn.setCursor(Qt.PointingHandCursor)
            if slot:
                btn.clicked.connect(slot)
            layout.addWidget(btn)
            return btn

        # Right: everyday actions (on a phone these move into More)
        if not PHONE_LAYOUT:
            header_button("Situation check", "Five quick questions → a priority list",
                          self._show_assessment)
            header_button("Skills", "Rebuild progress — 55 skills in 8 stages",
                          self._show_skill_tree)
            header_button("Map", "Offline world map", self._show_map)
        self._sidebar_btn = header_button("Info", "Show or hide your situation panel",
                                          self._toggle_sidebar, checkable=True)
        header_button("Settings", "Name, model, voice", self._show_settings)

        # More: occasional and advanced actions
        more = header_button("More ▾", "More actions", None)
        menu = QMenu(more)
        if PHONE_LAYOUT:
            menu.addAction("Situation check", self._show_assessment)
            menu.addAction("Skills", self._show_skill_tree)
            menu.addAction("Map", self._show_map)
            menu.addSeparator()
        menu.addAction("Personal documents…", self._show_doc_context)
        menu.addAction("Print emergency reference (PDF)", self._generate_print_reference)
        menu.addSeparator()
        menu.addAction("Reset…", self._show_reset_dialog)
        menu.addSeparator()
        menu.addAction("Developer panel   Ctrl+D", self._show_dev_panel)
        more.setMenu(menu)

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
        size_dialog(dialog, 800, 500, 900, 600)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)
        panel = DevPanel(dialog, training_graph=self.training_graph)
        panel.closed.connect(dialog.accept)
        layout.addWidget(panel)
        dialog.exec()

    def _check_ollama(self):
        """Start a background Ollama check (never blocks the window)."""
        from ui.workers import OllamaCheckWorker
        if getattr(self, "_ollama_worker", None) and self._ollama_worker.isRunning():
            return
        self._ollama_worker = OllamaCheckWorker(self.llm)
        self._ollama_worker.checked.connect(self._on_ollama_checked)
        self._ollama_worker.start()

    def _on_ollama_checked(self, result: dict):
        """
        Show what's wrong in plain words, and keep re-checking every
        10 seconds until Ollama and the models are ready.
        """
        if not hasattr(self, "_ollama_timer"):
            self._ollama_timer = QTimer(self)
            self._ollama_timer.setInterval(10_000)
            self._ollama_timer.timeout.connect(self._check_ollama)

        url = self.llm.base_url
        if not result["reachable"]:
            if PHONE_LAYOUT:
                msg = (f"⚠ Can't reach Ollama at {url}. Set your computer's "
                       "address in Settings → Model.")
            else:
                msg = (f"⚠ Can't reach Ollama at {url} ({result['error']}). "
                       "Open the Ollama app or run: ollama serve — checking again every 10 s")
            self.status_bar.showMessage(msg, 0)
            self._ollama_timer.start()
            return

        if result["missing"]:
            pulls = "   ".join(f"ollama pull {m}" for m in result["missing"])
            self.status_bar.showMessage(
                f"⚠ Ollama is running but the model isn't installed. Run: {pulls} "
                "— or pick an installed one in Settings → Model", 0
            )
            self._ollama_timer.start()
            return

        self._ollama_timer.stop()
        voice_name = self.tts.current_voice_name()
        ready = f"✓ Ready · {self.config.fast_model}"
        if voice_name and voice_name != "None":
            ready += f" · Voice: {voice_name}"
        self.status_bar.showMessage(ready, 6000)

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
        # When loading finishes, re-check Ollama so its warning isn't
        # replaced by "ready" while answers still can't be generated
        self._init_worker.finished.connect(self._check_ollama)
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
        """
        Entry point for every query.
        Routes the intent, then forks:
          Training Path  — deductive tabs, explain/assess intents (derive it)
          Knowledge Path — everything else (look it up, 11 steps)
        """
        self._generating = True
        self._generation_id += 1
        self.input_bar.set_generating(True)
        self.tts.stop()

        try:
            # ── Start trace ────────────────────────────────────────────────
            trace = tracer.start(user_input, tab.id)

            # ── Intent routing ─────────────────────────────────────────────
            routing_plan = self.pipeline.route(user_input, tab.id, trace)

            # ── Fork ───────────────────────────────────────────────────────
            if routing_plan.use_training_path:
                self._run_training_path(tab, user_input, routing_plan, trace)
            else:
                self._run_knowledge_path(tab, user_input, routing_plan, trace)

        except Exception as e:
            # Never leave the input locked if something above throws
            self._end_generation()
            self.chat_view.add_error(f"Something went wrong preparing the answer: {e}")

    # ── Training Path ──────────────────────────────────────────────────────

    def _run_training_path(self, tab: Tab, user_input: str, routing_plan, trace):
        """Derive from first principles on a worker thread (never block Qt)."""
        trace.path = "training"
        self.status_bar.showMessage("🧮 Working it out from first principles…", 0)
        gen_id = self._generation_id

        self._training_worker = TrainingWorker(self.training_engine, user_input, tab.id)
        self._training_worker.derivation_done.connect(
            lambda result: self._on_derivation_done(gen_id, tab, result)
        )
        self._training_worker.fallback_requested.connect(
            lambda result: self._on_training_fallback(gen_id, tab, user_input, routing_plan, trace, result)
        )
        self._training_worker.derivation_error.connect(
            lambda err: self._on_training_fallback(
                gen_id, tab, user_input, routing_plan, trace,
                {"status": "ERROR", "reason": f"Couldn't work it out ({err})."})
        )
        self._training_worker.start()

    def _on_derivation_done(self, gen_id: int, tab: Tab, result: dict):
        if gen_id != self._generation_id:
            return   # stopped or superseded
        trace = tracer.get_current()
        if trace:
            trace.training_status  = result.get("status", "")
            trace.training_concept = result.get("concept_id", "")
            trace.gate_mode        = "direct"

        text = result.get("text", "")
        self.status_bar.showMessage("", 0)
        self.chat_view.start_assistant_message()
        self._on_token(text)          # records speak-start and feeds the voice
        self.tts.flush()

        timing = self._finish_trace(text, tab)
        self.chat_view.finish_assistant_message(**timing)
        tab.add_message("assistant", text)
        self.tab_manager.save()

        # Ask for a verdict — only confirmed successes build trust
        if result.get("status") == "DERIVED":
            self.training_session.remember(tab.id, result)
            self.chat_view.add_verdict_bar(
                VERDICT_LABELS,
                lambda verdict, tid=tab.id: self._on_verdict(tid, verdict),
            )
        self._end_generation()

    def _on_verdict(self, tab_id: str, verdict: str):
        msg = self.training_session.apply_verdict(tab_id, verdict)
        if msg:
            self.status_bar.showMessage(msg, 6000)

    def _on_training_fallback(self, gen_id: int, tab: Tab, user_input: str,
                              routing_plan, trace, result: dict):
        """Derivation not possible — answer from the library instead."""
        if gen_id != self._generation_id:
            return
        trace.path = "knowledge"
        trace.training_status = f"fallback: {result.get('status', '')}"
        self.status_bar.showMessage("", 0)
        note = self.pipeline.training_fallback_note(result)
        if note:
            # Shown in the chat so it isn't lost when the status bar updates
            self.chat_view.add_note(note)
        try:
            self._run_knowledge_path(tab, user_input, routing_plan, trace)
        except Exception as e:
            self._end_generation()
            self.chat_view.add_error(f"Something went wrong preparing the answer: {e}")

    # ── Knowledge Path ─────────────────────────────────────────────────────

    def _run_knowledge_path(self, tab: Tab, user_input: str, routing_plan, trace):
        """
        The Knowledge Path. Steps 2–10 run in core/pipeline.py (shared with
        Android); this method only handles the UI and step 11 (streaming).
        """
        prepared = self.pipeline.prepare_knowledge(tab, user_input, routing_plan, trace)

        # Step 9: tell the user about mode and sources
        if prepared.status_text:
            self.status_bar.showMessage(prepared.status_text, 6000)

        # Step 10: CLARIFY — questions only, no LLM
        if prepared.clarify_text:
            self.chat_view.start_assistant_message()
            self._on_token(prepared.clarify_text)
            self.tts.flush()
            timing = self._finish_trace(prepared.clarify_text, tab)
            self.chat_view.finish_assistant_message(**timing)
            tab.add_message("assistant", prepared.clarify_text)
            self.tab_manager.save()
            self._end_generation()
            return

        # Step 11: stream the response (tokens go to the chat and the voice)
        messages = self.context_mgr.prepare_messages(tab)
        self.chat_view.start_assistant_message()

        self._llm_worker = LLMWorker(
            self.llm, messages, prepared.system_prompt,
            tab_id=tab.id,
            intent=prepared.intent,
        )
        self._llm_worker.token_received.connect(self._on_token)
        self._llm_worker.response_done.connect(
            lambda full: self._on_response_done(tab, full)
        )
        self._llm_worker.error_occurred.connect(self._on_error)
        self._llm_worker.start()

    def _on_token(self, token: str):
        """Handle incoming token from LLM stream."""
        tracer.record_first_token()   # speak-start — only the first call counts
        self.chat_view.append_token(token)
        self.tts.on_token(token)

    def _finish_trace(self, response: str, tab: Tab) -> dict:
        """Close the trace and return its timing for the chat stamp."""
        trace = tracer.get_current()
        tracer.finish(response, self.config.model_for_tab(tab.id))
        if not trace:
            return {}
        return {"first_token_ms": trace.first_token_ms, "response_ms": trace.response_ms}

    def _end_generation(self):
        self._generating = False
        self.input_bar.set_generating(False)

    def _on_response_done(self, tab: Tab, full_response: str):
        self.tts.flush()
        images = self.knowledge.get_last_images()
        timing = self._finish_trace(full_response, tab)
        self.chat_view.finish_assistant_message(
            image_paths=images if images else None, **timing
        )
        tab.add_message("assistant", full_response)
        if self.context_mgr.should_summarize(tab):
            QTimer.singleShot(1000, lambda: self._background_summarize(tab))
        self.tab_manager.save()
        self._end_generation()
        self.status_bar.showMessage("", 0)

    def _background_summarize(self, tab: Tab):
        """Summarize old context in background without blocking UI."""
        self.context_mgr.prepare_messages(tab)
        self.tab_manager.save()

    def _on_error(self, error: str):
        tracer.discard()
        self.chat_view.finish_assistant_message()
        self.chat_view.add_error(error)
        self._end_generation()

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
        size_dialog(dialog, 500, 650, 560, 700)

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
        # Ignore any late signals from the stopped query
        self._generation_id += 1

        # Kill the LLM and training worker threads
        if self._llm_worker and self._llm_worker.isRunning():
            self._llm_worker.terminate()
            self._llm_worker.wait(500)
        if self._training_worker and self._training_worker.isRunning():
            self._training_worker.terminate()
            self._training_worker.wait(500)
        tracer.discard()

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
        reset_all_btn.setObjectName("dangerBtn")
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
            "⚠ This wipes all memory, all conversations, all situation data,\n"
            "and everything the Training Path has learned.\n\n"
            "A backup will be saved first. Continue?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        self.backup.backup(label="pre_full_reset")
        self.memory.reset()
        self.training_graph.reset()
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
        # The welcome panel offers the situation check again

    def _has_situation_data(self) -> bool:
        """True once there's anything worth showing in the situation panel."""
        d = self.memory.data
        u, inv, alerts = d["user"], d["inventory"], d["alerts"]
        return bool(
            u.get("name") or u.get("location_estimate") or
            any(v for v in inv.values()) or any(v for v in alerts.values()) or
            d["progress"].get("completed")
        )

    def _toggle_sidebar(self):
        visible = self.sidebar.isVisible()
        self.sidebar.setVisible(not visible)
        self._sidebar_btn.setChecked(not visible)
        if PHONE_LAYOUT:
            # Phone: Info swaps the chat for the situation panel
            self.chat_view.setVisible(visible)
            self.input_bar.setVisible(visible)
            self._sidebar_btn.setText("Chat" if not visible else "Info")

    def _show_settings(self):
        from ui.settings_dialog import SettingsDialog
        dialog = SettingsDialog(self.config, self.memory, self)
        dialog.exec()
        self.memory.save()
        self.config.save()
        # Apply changes now — no restart needed
        self.llm.base_url = self.config.ollama_url.rstrip("/")
        self._check_ollama()
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
