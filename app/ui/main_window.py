"""
Main window for Prometheus.
PySide6 UI - clean, readable, functional.
"""

import os
import sys
from datetime import datetime, date
from typing import Optional

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QStatusBar, QLabel, QPushButton,
    QScrollArea, QFrame, QSizePolicy, QDialog,
    QLineEdit, QComboBox, QMessageBox
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QSize, QObject
from PySide6.QtGui import QFont, QKeySequence, QShortcut

from core.app.config import Config
from core.you.memory import Memory
from core.you.tabs import TabManager, Tab
from core.library.rag import KnowledgeBase
from core.ai.llm import LLMEngine
from core.voice.tts import TTSEngine
from core.voice.stt import STTEngine
from core.ai.context_manager import ContextManager

from ui.chat.chat_view import ChatView
from ui.chat.input_bar import InputBar
from ui.panels.sidebar import Sidebar
from ui.workers import LLMWorker, InitWorker, TrainingWorker
from ui.dialogs.assessment import AssessmentWidget
from ui.dialogs.skill_tree import SkillTreeWidget
from ui.panels.quick_access import QuickAccessWidget
from core.you.backup import BackupManager
from ui.dialogs.doc_context import DocumentContextWidget
from core.app.map_engine import MapEngine
from ui.dialogs.map_view import MapWidget
from core.app.p2p import P2PEngine
from ui.panels.messages_view import MessagesWidget
from core.you.tabs import suggest_redirect
from core.answers.tracer import tracer
from ui.dialogs.dev_panel import DevPanel
from core.answers.pipeline import QueryPipeline
from core.app.platform_info import PHONE_LAYOUT
from ui.layout_helpers import size_dialog
from core.training import TrainingGraph, DerivationEngine, TrainingSession


class MainWindow(QMainWindow):
    def __init__(self, config: Config):
        super().__init__()
        self.config = config

        # Core systems
        self.memory = Memory()
        self.tab_manager = TabManager()
        # Obsidian: take any edits made to Me.md while the app was closed
        from core.library import obsidian
        obsidian.set_vault(config.obsidian_vault, config.obsidian_use_notes)
        try:
            obsidian.read_back_only(self.memory)
        except Exception:
            pass
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
        from core.app.features import P2P_ENABLED
        if P2P_ENABLED:          # off until ready — nothing listens on the network
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
        self._apply_assistant_name()
        self._on_review_changed()           # "Review (n)" if anything is waiting
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

        # Content area (splitter: menu | chat | sidebar)
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setHandleWidth(1)

        # Left menu: sections on top, this section's chats underneath
        # (replaces the old row of tabs; same API, so self.tab_bar still works)
        from ui.chat.chats_panel import ChatsPanel
        from ui.chat.nav_panel import NavPanel
        self.chats_panel = ChatsPanel()
        self.chats_panel.new_chat_requested.connect(self._new_chat)
        self.chats_panel.open_requested.connect(self._open_chat)
        self.chats_panel.delete_requested.connect(self._delete_chat)
        self.chats_panel.rename_requested.connect(self._rename_chat)
        self.nav = NavPanel(self.tab_manager, self.chats_panel)
        self.tab_bar = self.nav
        self.nav.tab_selected.connect(self._on_tab_selected)
        self.nav.tab_add_requested.connect(self._on_add_tab)
        self.nav.quick_access_requested.connect(self._show_quick_access)
        self.splitter.addWidget(self.nav)

        # Chat view (welcome panel questions send straight away)
        self.chat_view = ChatView()
        self.chat_view.check_pending = lambda: not self.memory.data["user"].get("assessment_done")
        self.chat_view.suggestion_clicked.connect(self._on_send)
        self.chat_view.message_action.connect(self._on_message_action)
        self.chat_view.assessment_requested.connect(self._show_assessment)
        # The conversation and its message box sit together, right of the menu
        self._chat_pane = QWidget()
        self._chat_pane.setObjectName("chatPane")
        self._chat_pane_lay = QVBoxLayout(self._chat_pane)
        self._chat_pane_lay.setContentsMargins(0, 0, 0, 0)
        self._chat_pane_lay.setSpacing(0)
        self._chat_pane_lay.addWidget(self.chat_view, 1)
        self.splitter.addWidget(self._chat_pane)

        # Sidebar (situation, inventory, map)
        self.sidebar = Sidebar(self.memory)
        self.sidebar.setMaximumWidth(280)
        self.sidebar.setMinimumWidth(200)
        self.splitter.addWidget(self.sidebar)

        self.splitter.setSizes([260, 800, 280])
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)
        if PHONE_LAYOUT:
            self.nav.hide()                    # phone: ☰ swaps it in
        self._chats_btn.setChecked(not self.nav.isHidden())

        # Phone: the situation panel takes the whole width when opened,
        # so start with it closed
        if PHONE_LAYOUT:
            self.sidebar.setMaximumWidth(16777215)
            self.sidebar.hide()
        elif not self._has_situation_data():
            # Desktop: a panel of empty "—" rows is just noise on a fresh start
            self.sidebar.hide()
        self._sidebar_btn.setChecked(not self.sidebar.isHidden())

        main_layout.addWidget(self.splitter, 1)   # chat takes all spare height

        # Input bar
        self.input_bar = InputBar(self.stt)
        self.input_bar.message_submitted.connect(self._on_send)
        self.input_bar.mic_clicked.connect(self._on_mic_clicked)
        self.input_bar.talk_started.connect(self._start_push_to_talk)
        self.input_bar.talk_finished.connect(lambda: self.stt.finish_listening())
        self.input_bar.stop_requested.connect(self._force_stop)
        # Voice: words heard on a background thread come back here
        self._voice_mode = False          # back-and-forth voice conversation
        self._heard = _HeardBridge()
        self._heard.heard.connect(self._on_heard)
        self._summary_bridge = _SummaryBridge()
        self._summary_bridge.done.connect(self._summary_ready)
        self._power_bridge = _PowerBridge()
        self._power_bridge.decided.connect(self._apply_power)
        self._noticed_bridge = _NoticedBridge()
        self._noticed_bridge.found.connect(self._on_noticed)
        self._speech_timer = QTimer(self)
        self._speech_timer.setInterval(120)
        self._speech_timer.timeout.connect(self._voice_tick)
        self._speech_timer.start()
        self.input_bar.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self._chat_pane_lay.addWidget(self.input_bar)

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

        # Left: the menu button (sections and chats), icon, name and day
        self._chats_btn = QPushButton("☰")
        self._chats_btn.setObjectName("menuBtn")
        self._chats_btn.setCheckable(True)
        self._chats_btn.setFixedSize(36, 36)
        self._chats_btn.setCursor(Qt.PointingHandCursor)
        self._chats_btn.setToolTip("Sections and chats")
        self._chats_btn.clicked.connect(self._toggle_chats)
        layout.addWidget(self._chats_btn)
        layout.addSpacing(10)
        icon_path = os.path.join("assets", "icon.png")
        if os.path.exists(icon_path):
            from PySide6.QtGui import QPixmap
            logo = QLabel()
            logo.setObjectName("headerLogo")
            pix = QPixmap(icon_path)
            dpr = self.devicePixelRatioF() or 1.0
            pix = pix.scaled(int(26 * dpr), int(26 * dpr), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            pix.setDevicePixelRatio(dpr)
            logo.setPixmap(pix)
            layout.addWidget(logo)
            layout.addSpacing(8)
        name = (self.config.assistant_name or "Prometheus").strip()
        title = QLabel(name)
        self._title_label = title
        title.setObjectName("headerTitle")
        layout.addWidget(title)

        self._day_label = QLabel(self._get_day_string())
        self._day_label.setObjectName("headerDay")
        layout.addWidget(self._day_label)
        if PHONE_LAYOUT:
            self._day_label.hide()            # room for the buttons; the Info panel shows the day
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
            from core.ai import ollama_local
            here = set(ollama_local.local_models())
            if here and all(m in here for m in result["missing"]):
                # The models ARE in app\models — the Ollama that answered isn't
                # the one reading them (the owner saw this after the move)
                msg = (f"⚠ Your models are in app\\models, but the Ollama at {url} isn't reading "
                       "them. Close Prometheus and open it again; if this stays, hold Shift while "
                       "opening Prometheus.exe for a debug log — checking again every 10 s")
            else:
                pulls = "   ".join(f"python -m core.ai.ollama_local --pull {m}" for m in result["missing"])
                msg = (f"⚠ Ollama is running but the model isn't installed. Run: {pulls} "
                       "— or pick an installed one in Settings → Model")
            self.status_bar.showMessage(msg, 0)
            self._ollama_timer.start()
            return

        self._ollama_timer.stop()
        self._warm_up_model()
        voice_name = self.tts.current_voice_name()
        ready = f"✓ Ready · {self.config.speaker_model}"
        if self.config.two_models:
            ready += f" (librarian: {self.config.librarian_model.split('/')[-1]})"
        if getattr(self.config, "low_power_active", False):
            ready += " · low power"
        if voice_name and voice_name != "None":
            ready += f" · Voice: {voice_name}"
        self.status_bar.showMessage(ready, 6000)

    def _apply_assistant_name(self):
        """Header title and the companion tab use the chosen name."""
        self._apply_power_limits()
        name = (self.config.assistant_name or "Prometheus").strip()
        self._title_label.setText(name)
        tab = self.tab_manager.get_tab("prometheus")
        if tab and tab.name != name:
            tab.name = name
            self.tab_bar.refresh()
            if self.tab_manager.active_tab_id == "prometheus" and not self._generating:
                self._load_tab("prometheus")
        self._warmed = None          # the companion prompt changed — warm up again

    def _warm_up_model(self):
        """
        Once Ollama is ready: load the model and have it read the companion
        prompt, so the first message doesn't wait for either. Runs once per
        model choice, on a background thread.
        """
        import threading
        key = (self.llm.base_url, self.config.speaker_model, self.config.librarian_model)
        if getattr(self, "_warmed", None) == key:
            return
        self._warmed = key
        plan = self.pipeline.route("hi", "prometheus")
        prompt = self.pipeline._prepare_companion("hi", plan).system_prompt

        def warm():
            # Both models loaded and kept: the speaker reads its chat prompt,
            # the librarian just loads (its prompts change every time)
            self.llm.warm_up(prompt)
            if self.config.two_models and self.config.librarian_model != self.config.speaker_model:
                self.llm.warm_up(model=self.config.librarian_model)
            # Now the models are loaded, see what this computer can do
            # (Ollama says whether they went onto the graphics card)
            from core.app import hardware
            try:
                hw = hardware.detect()
                mode, why = hardware.recommend(hw, hardware.ollama_on_gpu(self.llm.base_url))
                self._power_bridge.decided.emit(mode, why, hw.summary())
            except Exception:
                pass
        threading.Thread(target=warm, daemon=True).start()

    def _apply_power(self, auto_choice: str, why: str, summary: str, tell: bool = True):
        """
        Full or low-power mode.

        Step 1: Settings → Model → Performance wins if it's Full or Low power;
                on Automatic, the hardware's choice is used
        Step 2: apply the limits (fewer, shorter library passages)
        Step 3: on Automatic, say so in the chat when the choice changes
                (not every start — only when it differs from last time)
        """
        cfg = self.config
        cfg.hardware_summary, cfg.power_reason = summary, why
        # Step 1
        chosen = cfg.power_mode if cfg.power_mode in ("full", "low") else auto_choice
        cfg.low_power_active = chosen == "low"
        # Step 2
        self._apply_power_limits()
        # Step 3
        if cfg.power_mode == "auto" and auto_choice != cfg.power_last:
            first_time = not cfg.power_last
            cfg.power_last = auto_choice
            cfg.save()
            if tell and (auto_choice == "low" or not first_time):
                note = (f"Low-power mode is on — {why}. Answers are kept leaner so they stay "
                        "quick. Settings → Model → Performance to change it."
                        if auto_choice == "low" else
                        f"Full mode is on — {why}. Settings → Model → Performance to change it.")
                self.chat_view.add_note(note)
                self.status_bar.showMessage(note, 12000)

    def _apply_power_limits(self):
        """Library passages per answer: 2 shorter ones in low power, else as set."""
        low = getattr(self.config, "low_power_active", False)
        wanted = max(1, int(self.config.rag_results or 3))
        self.knowledge.prompt_passages = min(wanted, 2) if low else wanted
        self.knowledge.passage_words = 90 if low else 130

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
        self._init_worker.finished.connect(
            lambda: self.input_bar.set_voice_available(
                self.stt.available,
                self.stt.error if self.config.stt_enabled else "Voice input is off in Settings → Voice"))
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

        # Wikipedia tab — search and read, not a chat
        if tab_id == "wikipedia":
            self._show_wiki_panel()
            return

        # Review tab — confirm what it picked up about you, not a chat
        if tab_id == "review":
            self._show_review_panel()
            return

        self._hide_messages_panel()
        self._hide_wiki_panel()
        self._hide_review_panel()
        self.chat_view.load_tab(tab)
        self._stop_editing()
        self.chats_panel.show()               # chat sections list their chats in the menu
        self.chats_panel.refresh(tab)
        self.input_bar.set_recall([m["content"] for m in tab.history if m.get("role") == "user"])

        # Medical tab warning
        if tab_id == "medical":
            self.status_bar.showMessage(
                "⚕ Medical tab — AI provides reference only. "
                "Always verify critical medical decisions with multiple sources.", 8000
            )

        self.setWindowTitle(f"Prometheus — {tab.icon} {tab.name}")

    # ── Message actions (⋯ menu / right-click) ─────────────────────────────

    def _on_message_action(self, action: str, msg: dict):
        """
        copy   → clipboard
        edit   → your message back in the box; sending replaces it and what followed
        retry  → drop the last reply and ask again
        delete → remove that one message
        """
        from PySide6.QtWidgets import QApplication
        tab = self.tab_manager.get_active_tab()
        if action == "copy":
            QApplication.clipboard().setText((msg or {}).get("content", ""))
            self.status_bar.showMessage("Copied", 2000)
            return
        if not tab or msg is None:
            return
        if self._generating:
            self.status_bar.showMessage("Wait for the reply to finish (or press Esc to stop it)", 4000)
            return
        idx = next((i for i, m in enumerate(tab.history) if m is msg), None)
        if idx is None:
            return

        if action == "edit":
            self._editing_msg = msg
            self.input_bar.set_text(msg["content"])
            self.input_bar.set_editing(True)
            self.input_bar.focus_input()

        elif action == "delete":
            del tab.history[idx]
            if getattr(self, "_editing_msg", None) is msg:
                self._stop_editing()
            self.tab_manager.save()
            self.chat_view.load_tab(tab)
            self.input_bar.set_recall([m["content"] for m in tab.history if m.get("role") == "user"])

        elif action == "retry":
            # Only the last reply, and only if a question came before it
            if idx != len(tab.history) - 1 or idx == 0 or tab.history[idx - 1].get("role") != "user":
                return
            question = tab.history[idx - 1]["content"]
            del tab.history[idx]
            self.tab_manager.save()
            self.chat_view.load_tab(tab)
            self._generate_response(tab, question)

    # ── Chats ──────────────────────────────────────────────────────────────

    def _toggle_chats(self):
        """
        ☰ — desktop: show or hide the left menu.
        Phone: the menu takes the whole screen; ☰ again (or picking a section
        or a chat) goes back to what was open.
        """
        opening = self.nav.isHidden()
        if PHONE_LAYOUT:
            if opening:
                for w in (self._chat_pane, self.sidebar,
                          getattr(self, "_wiki_widget", None), getattr(self, "_review_widget", None)):
                    if w is not None:
                        w.hide()
                self._sidebar_btn.setChecked(False)
                self.nav.show()
            else:
                self.nav.hide()
                self._load_tab(self.tab_manager.active_tab_id)
        else:
            self.nav.setVisible(opening)
        self._chats_btn.setChecked(opening)
        if opening:
            self.chats_panel.refresh(self.tab_manager.get_active_tab())

    def _after_chat_change(self, tab):
        self.tab_manager.save()
        self.chat_view.load_tab(tab)
        self._stop_editing()
        self.input_bar.set_recall([m["content"] for m in tab.history if m.get("role") == "user"])
        self.chats_panel.refresh(tab)
        if PHONE_LAYOUT and self.nav.isVisible():
            self._toggle_chats()             # phone: back to the conversation
        self.input_bar.focus_input()

    def _busy(self) -> bool:
        if self._generating:
            self.status_bar.showMessage("Wait for the reply to finish (or press Esc to stop it)", 4000)
        return self._generating

    def _new_chat(self):
        tab = self.tab_manager.get_active_tab()
        if not tab or self._busy():
            return
        tab.new_chat()
        self._after_chat_change(tab)

    def _open_chat(self, chat_id: str):
        tab = self.tab_manager.get_active_tab()
        if not tab or self._busy():
            return
        if tab.open_chat(chat_id):
            self._after_chat_change(tab)

    def _delete_chat(self, chat_id: str):
        tab = self.tab_manager.get_active_tab()
        if not tab or self._busy():
            return
        title = next((c["title"] for c in tab.all_chats() if c["id"] == chat_id), "this chat")
        if QMessageBox.question(self, "Delete chat",
                                f"Delete \u201c{title}\u201d? This can't be undone.",
                                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        tab.delete_chat(chat_id)
        self._after_chat_change(tab)

    def _rename_chat(self, chat_id: str, current: str):
        from PySide6.QtWidgets import QInputDialog
        tab = self.tab_manager.get_active_tab()
        if not tab:
            return
        title, ok = QInputDialog.getText(self, "Rename chat", "Name:", text=current)
        if ok:
            tab.rename_chat(chat_id, title)
            self.tab_manager.save()
            self.chats_panel.refresh(tab)

    def _stop_editing(self):
        self._editing_msg = None
        self.input_bar.set_editing(False)

    def _show_wiki_panel(self):
        from ui.panels.wiki_search import WikiSearchWidget
        self._hide_messages_panel()
        self._hide_review_panel()
        if not hasattr(self, "_wiki_widget"):
            self._wiki_widget = WikiSearchWidget(self.knowledge)
            self._wiki_widget.ask_about.connect(self._ask_about_article)
            self._wiki_widget.ask_in.connect(self._ask_about_passage)
            self.splitter.insertWidget(1, self._wiki_widget)
        self._chat_pane.hide()
        self.input_bar.hide()
        self.chats_panel.hide()            # Wikipedia isn't a chat
        self._wiki_widget.show()
        self._wiki_widget.focus_search()
        self.setWindowTitle(f"{self.config.assistant_name or 'Prometheus'} — Search")

    def _show_review_panel(self):
        from ui.panels.review_panel import ReviewPanel
        self._hide_messages_panel()
        self._hide_wiki_panel()
        if not hasattr(self, "_review_widget"):
            self._review_widget = ReviewPanel(self.memory)
            self._review_widget.changed.connect(self._on_review_changed)
            self.splitter.insertWidget(1, self._review_widget)
        self._chat_pane.hide()
        self.input_bar.hide()
        self.chats_panel.hide()
        self._review_widget.refresh()
        self._review_widget.show()
        self.setWindowTitle(f"{self.config.assistant_name or 'Prometheus'} — Review")

    def _hide_review_panel(self):
        if hasattr(self, "_review_widget"):
            self._review_widget.hide()

    def _on_review_changed(self, waiting: int = -1):
        """Tab label shows how many are waiting; accepted facts reach the side panel."""
        from core.you import claims
        if waiting < 0:
            waiting = claims.pending_count()
        self.tab_bar.set_label("review", f"Review ({waiting})" if waiting else "Review")
        self.sidebar.refresh()

    def _hide_wiki_panel(self):
        if hasattr(self, "_wiki_widget"):
            self._wiki_widget.hide()

    def _ask_about_article(self, title: str):
        """'Ask about this' in the Search tab → the chat tab, asking about it."""
        if not title or self._generating:
            return
        self._load_tab("prometheus")
        self._on_send(f"Tell me about {title}")

    def _ask_about_passage(self, domain: str, subject: str):
        """'Ask about this' on a book result → the section that reads that folder."""
        if not subject or self._generating:
            return
        # Step 1: a section that reads that folder; Step 2: one that reads a folder
        # of the same family ("plants" → "plants_temperate"); else the chat
        def reads(t, exact):
            ds = [] if t.id == "wikipedia" else (getattr(t, "domains", None) or [])
            return domain in ds if exact else any(d.startswith(domain) or domain.startswith(d.split("_")[0])
                                                  for d in ds)
        tab = next((t for t in self.tab_manager.tabs if reads(t, True)), None) or \
            next((t for t in self.tab_manager.tabs if reads(t, False)), None)
        self._load_tab(tab.id if tab else "prometheus")
        self._on_send(subject if len(subject.split()) > 3 else f"Tell me about {subject}")

    def _show_messages_panel(self):
        """Show P2P messages panel instead of chat view."""
        if not hasattr(self, '_messages_widget'):
            self._messages_widget = MessagesWidget(self.p2p)
            self.splitter.insertWidget(1, self._messages_widget)

        self._chat_pane.hide()
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
        self._chat_pane.show()
        self.input_bar.show()

    def _on_tab_selected(self, tab_id: str):
        if self._generating:
            self.tab_bar.set_active(self.tab_manager.active_tab_id)
            return  # Don't switch while generating
        if PHONE_LAYOUT and self.nav.isVisible():
            self.nav.hide()                   # phone: picking a section closes the menu
            self._chats_btn.setChecked(False)
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

        # Sending an edited message: the conversation continues from there —
        # the original message and everything after it are replaced
        editing = getattr(self, "_editing_msg", None)
        if editing is not None:
            idx = next((i for i, m in enumerate(tab.history) if m is editing), None)
            if idx is not None:
                del tab.history[idx:]
                self.chat_view.load_tab(tab)
            self._stop_editing()

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

        # Learn what they say about themselves ("my sister Kate", "I live in
        # Cork") — shown briefly so nothing is learned silently
        from core.you.profile import learn
        # (shown once the reply is done, so the "thinking" status doesn't hide it)
        learned = learn(text, self.memory)
        self._last_user_text = text           # for the model's own look, after the reply
        self._learned_note = ("To confirm in the Review tab: " + "; ".join(learned)) if learned else ""
        if learned:
            self._on_review_changed()

        # Add user message
        tab.add_message("user", text)
        self.chat_view.add_message("user", text)
        self.chat_view.attach_last(tab.history[-1])
        self.input_bar.remember_sent(text)
        self.tab_manager.save()
        self.chats_panel.refresh(tab)

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
        self.tts.begin_reply()
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
        gen_id = self._generation_id

        # Show what it's working on (cheap keyword match — no model call)
        concept = self.training_engine.get_concept_or_request(user_input, tab.id)
        if concept:
            self.chat_view.show_researching(f"Researching {concept['name']}")

        self._training_worker = TrainingWorker(self.training_engine, user_input, tab.id)
        self._training_worker.progress.connect(
            lambda text: self.chat_view.show_researching(text)
            if gen_id == self._generation_id else None
        )
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
        self.chat_view.hide_researching()
        self.chat_view.start_assistant_message()
        self._on_token(text)          # records speak-start and feeds the voice
        self.tts.flush()

        timing = self._finish_trace(text, tab)
        self.chat_view.finish_assistant_message(**timing)
        tab.add_message("assistant", text)
        self.chat_view.attach_last(tab.history[-1])
        self.tab_manager.save()

        # No verdict asked — the engine's own three-way check already set trust
        self._end_generation()

    def _on_training_fallback(self, gen_id: int, tab: Tab, user_input: str,
                              routing_plan, trace, result: dict):
        """Derivation not possible — answer from the library instead."""
        if gen_id != self._generation_id:
            return
        trace.path = "knowledge"
        trace.training_status = f"fallback: {result.get('status', '')}"
        self.chat_view.hide_researching()
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
        The Knowledge Path. Steps 2–10 run in core/answers/pipeline.py (shared with
        Android); this method only handles the UI and step 11 (streaming).
        """
        # Steps 2–10 run in the background (with two models they include the
        # speaker's library request and the librarian's facts); a late result
        # from a stopped query is ignored
        from ui.workers import PrepareWorker
        gen = self._generation_id
        self._prepare_worker = PrepareWorker(self.pipeline, tab, user_input, routing_plan, trace)
        self._prepare_worker.progress.connect(
            lambda text: gen == self._generation_id and self.chat_view.show_researching(text))
        self._prepare_worker.prepared.connect(
            lambda prepared: gen == self._generation_id and self._answer_prepared(tab, prepared, trace))
        self._prepare_worker.failed.connect(
            lambda err: gen == self._generation_id and self._on_error(err))
        self._prepare_worker.start()

    def _answer_prepared(self, tab: Tab, prepared, trace):
        """The prompt is ready: show a clarifying question, or let the speaker talk."""
        self.chat_view.hide_researching()
        # Images and source names belong to THIS answer (never leftovers)
        self._answer_media = (prepared.images, prepared.sources)

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
            self.chat_view.attach_last(tab.history[-1])
            self.tab_manager.save()
            self._end_generation()
            return

        # Step 11: stream the response (tokens go to the chat and the voice).
        # The history is sent exactly as last time and this question's
        # context rides with the newest message, so the model only has to
        # read what's new (see pipeline.with_turn_context)
        from core.answers.pipeline import with_turn_context
        reserve = len(prepared.system_prompt or "") + len(prepared.turn_context or "")
        messages = with_turn_context(self.context_mgr.messages_for(tab, reserve), prepared.turn_context)
        import time as _time
        trace.prep_ms = int((_time.time() - trace.timestamp) * 1000)
        self.llm.last_stats = {}
        self.chat_view.start_assistant_message()

        self._llm_worker = LLMWorker(
            self.llm, messages, prepared.system_prompt,   # fixed instructions only
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
        return {"first_token_ms": trace.first_token_ms, "response_ms": trace.response_ms,
                "breakdown": trace.breakdown()}

    def _end_generation(self):
        self._generating = False
        self.input_bar.set_generating(False)

    def _on_response_done(self, tab: Tab, full_response: str):
        self.tts.flush()
        trace = tracer.get_current()
        if trace and self.llm.last_stats:
            for k, v in self.llm.last_stats.items():
                setattr(trace, k, v)
        images, sources = getattr(self, "_answer_media", ([], []))
        self._answer_media = ([], [])
        if trace:   # which pictures went with the reply, for the log
            trace.images = [os.path.basename(p) for p in images or []]
        timing = self._finish_trace(full_response, tab)
        self.chat_view.finish_assistant_message(
            image_paths=images or None, sources=sources or None, **timing
        )
        tab.add_message("assistant", full_response)
        self.chat_view.attach_last(tab.history[-1])
        if self.context_mgr.should_summarize(tab):
            QTimer.singleShot(1000, lambda: self._background_summarize(tab))
        self.tab_manager.save()
        self.chats_panel.refresh(tab)
        self._end_generation()
        note = getattr(self, "_learned_note", "")
        self._learned_note = ""
        self.status_bar.showMessage(note, 8000 if note else 0)
        self._notice_facts(getattr(self, "_last_user_text", ""))
        # The models kept swapping in and out of the graphics card → say so once
        if getattr(self.llm, "thrashing", False) and not getattr(self, "_told_thrashing", False):
            self._told_thrashing = True
            self.status_bar.showMessage(
                "Graphics card memory is nearly full (other programs are using it) — "
                "using one model for now so replies stay quick", 15000)

    def _notice_facts(self, text: str):
        """
        After the reply (never slowing it): the librarian looks for things
        they said about themselves that the fixed patterns missed, on a
        background thread. Anything found waits in the Review tab.
        Off in low-power mode, with one model, or in Settings → You.
        """
        import threading
        cfg = self.config
        if not text or not cfg.notice_facts or not cfg.two_models or \
                getattr(cfg, "low_power_active", False) or getattr(self.llm, "thrashing", False):
            return
        from core.you import notice
        if not notice.worth_asking(text):
            return

        def work():
            from core.you import claims
            try:
                added = claims.stage(notice.notice(self.llm, text), self.memory)
            except Exception:
                added = []
            if added:
                self._noticed_bridge.found.emit([c.note for c in added])
        threading.Thread(target=work, daemon=True).start()

    def _on_noticed(self, notes):
        self._on_review_changed()
        if not self._generating:
            self.status_bar.showMessage("To confirm in the Review tab: " + "; ".join(notes), 8000)

    def _background_summarize(self, tab: Tab):
        """
        Summarise the oldest messages of a long chat on a background thread
        (it's a model call — it used to run here and freeze the window).
        """
        import threading
        if getattr(self, "_summarising", False):
            return
        self._summarising = True
        old, text = self.context_mgr.summarise_job(tab)

        def work():
            try:
                summary = self.llm.summarize(text)
            except Exception:
                summary = ""
            self._summary_bridge.done.emit(tab, old, summary)
        threading.Thread(target=work, daemon=True).start()

    def _summary_ready(self, tab, old, summary):
        self._summarising = False
        if self.context_mgr.apply_summary(tab, old, summary):
            self.tab_manager.save()

    def _on_error(self, error: str):
        tracer.discard()
        self.chat_view.hide_researching()
        self.chat_view.finish_assistant_message()
        self.chat_view.add_error(error)
        self._end_generation()

    # ── Voice: stop button, hold-to-talk, voice conversation ──────────────

    def _on_mic_clicked(self):
        """
        The mic button:
          while the voice is talking → stop it (a black square)
          in a voice conversation    → end the conversation
          otherwise                  → start one
        """
        if self.tts.is_speaking():
            self._stop_speaking()
        elif self._voice_mode:
            self._end_voice_mode()
        elif not self.input_bar.voice_ok():
            self.status_bar.showMessage(self.stt.error or "Voice input isn't set up — run: python tools/setup_voice.py", 6000)
        else:
            self._voice_mode = True
            self.status_bar.showMessage("Voice conversation on — just talk. Click the mic to end it.", 6000)

    def _end_voice_mode(self):
        self._voice_mode = False
        if self.stt.listening:
            self.stt.cancel_listening()
        self.status_bar.showMessage("Voice conversation off", 3000)

    def _start_push_to_talk(self):
        """Send button held: listen until it's let go."""
        if self._voice_mode and self.stt.listening:
            self.stt.cancel_listening()
        self.tts.stop()
        if self.stt.listen(lambda text: self._heard.heard.emit(text, False), auto_stop=False):
            self.status_bar.showMessage("Listening — let go to send", 0)
        else:
            self.status_bar.showMessage(self.stt.error or "Couldn't open the microphone", 6000)

    def _voice_tick(self):
        """
        Runs every 120 ms.

        Step 1: the mic button's look (black square while the voice talks)
        Step 2: in a voice conversation, keep the mic open — even while it
                talks or writes, so you can interrupt
        Step 3: you started talking over it → stop the voice and the reply;
                what you say is sent when you pause
        """
        speaking = self.tts.is_speaking()
        # Step 1
        self.input_bar.set_mic_mode("speaking" if speaking else
                                    "listening" if self._voice_mode else "idle")
        if not self._voice_mode:
            return
        busy = speaking or self._generating
        # Step 2
        if not self.stt.listening and not self.stt.transcribing:
            if self.stt.listen(lambda text: self._heard.heard.emit(text, True), auto_stop=True):
                if not busy:
                    self.status_bar.showMessage("Listening…", 0)
            else:
                self._voice_mode = False
                self.status_bar.showMessage(self.stt.error or "Couldn't open the microphone", 6000)
                return
        self.stt.set_strict(busy)
        # Step 3
        if busy and self.stt.heard_speech():
            if self._generating:
                self._force_stop(keep_voice_mode=True)
            self.tts.stop()
            self.status_bar.showMessage("Listening…", 0)

    def _on_heard(self, text: str, voice_mode: bool):
        """Words came back from Whisper → send them."""
        if not text:
            if not voice_mode:
                self.status_bar.showMessage("Didn't catch that", 3000)
            return
        if voice_mode and not self._voice_mode:
            return                      # conversation ended while it was working
        if self._generating:
            self._force_stop(keep_voice_mode=True)
        self.status_bar.showMessage("", 0)
        self._on_send(text)

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

    def _stop_speaking(self):
        """Cut the voice now. A reply still being written carries on silently."""
        self.tts.hush(reply_still_coming=self._generating)
        self.input_bar.set_mic_mode("listening" if self._voice_mode else "idle")

    def _force_stop(self, keep_voice_mode: bool = False):
        """
        Force-stop any current generation immediately.
        Resets all state. Used when model is stuck or
        user wants to abort a response in progress.
        Escape while editing a message (and nothing generating) cancels the edit.
        """
        if not self._generating and getattr(self, "_editing_msg", None) is not None:
            self._stop_editing()
            self.input_bar.clear_input()
            return
        # Esc / ⏹ also ends a voice conversation (talking over it doesn't)
        if not keep_voice_mode and getattr(self, "_voice_mode", False):
            self._end_voice_mode()
        # Ignore any late signals from the stopped query
        self._generation_id += 1

        # Kill the LLM and training worker threads
        if self._llm_worker and self._llm_worker.isRunning():
            self._llm_worker.terminate()
            self._llm_worker.wait(500)
        if self._training_worker and self._training_worker.isRunning():
            self._training_worker.terminate()
            self._training_worker.wait(500)
        # The library step can't be cut mid-request; its result is ignored
        # (the generation id moved on) and it finishes in the background
        self.chat_view.hide_researching()
        tracer.discard()

        # Clear TTS queue and stop speech
        self.tts.stop()

        # Finish any open bubble cleanly
        self.chat_view.hide_researching()
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

        clear_tab_btn = QPushButton(f"🗑  Clear this {tab_name} chat")
        clear_tab_btn.setObjectName("navBtn")
        clear_tab_btn.clicked.connect(lambda: self._reset_tab(dialog))
        layout.addWidget(clear_tab_btn)

        # Reset all tab conversations
        clear_all_tabs_btn = QPushButton("🗑  Clear all chats in every tab")
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
        self.chats_panel.refresh(tab)
        if parent_dialog:
            parent_dialog.accept()
        self.status_bar.showMessage(
            f"✓ {tab.name} conversation cleared", 3000
        )

    def _reset_all_tabs(self, parent_dialog=None):
        """Clear all tab conversation histories."""
        reply = QMessageBox.question(
            self, "Clear all conversations",
            "Delete every chat in every tab?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        self.backup.backup(label="pre_all_tabs_reset")
        for tab in self.tab_manager.tabs:
            self.tab_manager.clear_tab(tab.id, every_chat=True)
        tab = self.tab_manager.get_active_tab()
        if tab:
            self.chat_view.load_tab(tab)
            self.chats_panel.refresh(tab)
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
            self.tab_manager.clear_tab(tab.id, every_chat=True)
        tab = self.tab_manager.get_active_tab()
        if tab:
            self.chat_view.load_tab(tab)
            self.chats_panel.refresh(tab)
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
            self._chat_pane.setVisible(visible)
            self.input_bar.setVisible(visible)
            self._sidebar_btn.setText("Chat" if not visible else "Info")

    def _show_settings(self):
        from ui.dialogs.settings_dialog import SettingsDialog
        dialog = SettingsDialog(self.config, self.memory, self, obsidian_sync=self._obsidian_sync)
        dialog.exec()
        self.memory.save()
        self.config.save()
        from core.library import obsidian
        obsidian.set_vault(self.config.obsidian_vault, self.config.obsidian_use_notes)
        # Performance may have changed (Automatic keeps the hardware's last choice)
        self._apply_power(self.config.power_last or "full", self.config.power_reason,
                          self.config.hardware_summary, tell=False)
        # Apply changes now — no restart needed
        self._apply_assistant_name()
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

    def _obsidian_sync(self) -> str:
        """Read back Me.md edits, then write the mind map. Returns a status line."""
        from core.library import obsidian
        if not obsidian.vault_path():
            return "Choose your Obsidian vault folder first."
        try:
            msg = obsidian.sync(self.memory, self.tab_manager, self.config.assistant_name or "Prometheus")
        except Exception as e:
            return f"Couldn't write to the vault: {e}"
        self.tab_manager.save()
        self.sidebar.refresh()
        return msg

    def closeEvent(self, event):
        self.tts.shutdown()
        self.p2p.stop()
        # Stop the Ollama we started for prometheus/models (never anyone else's)
        from core.ai import ollama_local
        ollama_local.stop()
        self.tab_manager.save()
        self.memory.save()
        self.config.save()
        # Write the Obsidian mind map (only changed notes)
        self._obsidian_sync()
        # Silent backup on every close
        self.backup.backup(label=f"day{self.memory.data['user']['day_count']}")
        event.accept()
        self._finish_threads()

    @staticmethod
    def _finish_threads(wait_ms: int = 2000):
        """
        Background jobs still running at close (an Ollama check waiting on a
        slow server, a reply being written…) crashed the app on the way out:
        "QThread: Destroyed while thread is still running" (exit -1073740791).

        Step 1: ask each one to stop and give it up to 2 s
        Step 2: one stuck in a network call can't be stopped — everything is
                saved by now, so leave at once instead of crashing
        """
        import gc
        import warnings
        from PySide6.QtCore import QThread
        with warnings.catch_warnings():          # touching torch's objects warns (harmless)
            warnings.simplefilter("ignore")
            running = [o for o in gc.get_objects()
                       if isinstance(o, QThread) and o is not QThread.currentThread() and o.isRunning()]
        for t in running:                                   # Step 1
            t.requestInterruption()
            t.quit()
        for t in running:
            t.wait(wait_ms)
        if any(t.isRunning() for t in running):             # Step 2
            sys.stdout.flush()
            sys.stderr.flush()
            os._exit(0)


class _NoticedBridge(QObject):
    """Facts the librarian noticed (staged for Review), back to the window."""
    found = Signal(list)


class _PowerBridge(QObject):
    """Carries the hardware check's choice (full / low power) to the window."""
    decided = Signal(str, str, str)        # choice, why, what was detected


class _SummaryBridge(QObject):
    """Carries a finished chat summary from its background thread to the window."""
    done = Signal(object, object, str)     # tab, the messages summarised, summary


class _HeardBridge(QObject):
    """Carries Whisper's result from its background thread to the window."""
    heard = Signal(str, bool)      # text, came from voice conversation


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
