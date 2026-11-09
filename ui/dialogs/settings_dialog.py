"""
Settings dialog - configure model, voice, user info.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QComboBox, QCheckBox, QPushButton,
    QTabWidget, QWidget, QSpinBox, QDoubleSpinBox,
    QGroupBox, QFormLayout
)
from PySide6.QtCore import Qt

from core.app.config import Config
from core.you.memory import Memory


class SettingsDialog(QDialog):
    def __init__(self, config: Config, memory: Memory, parent=None, obsidian_sync=None):
        super().__init__(parent)
        self.config = config
        self.memory = memory
        self._obsidian_sync = obsidian_sync     # MainWindow._obsidian_sync

        self.setWindowTitle("Prometheus — Settings")
        from core.app.platform_info import PHONE_LAYOUT
        self.setMinimumWidth(450 if PHONE_LAYOUT else 560)
        self.setMinimumHeight(400)

        layout = QVBoxLayout(self)

        tabs = QTabWidget()

        tabs.addTab(self._build_user_tab(), "👤 You")
        tabs.addTab(self._build_assistant_tab(), "💬 Assistant")
        tabs.addTab(self._build_model_tab(), "🤖 Model")
        tabs.addTab(self._build_voice_tab(), "🎤 Voice")
        tabs.addTab(self._build_obsidian_tab(), "📓 Obsidian")
        tabs.addTab(self._build_about_tab(), "ℹ About")

        layout.addWidget(tabs)

        btns = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Save")
        save.setObjectName("primaryBtn")
        save.clicked.connect(self._save)
        btns.addStretch()
        btns.addWidget(cancel)
        btns.addWidget(save)
        layout.addLayout(btns)

    def _build_user_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setSpacing(12)

        u = self.memory.data["user"]

        self._name_edit = QLineEdit(u.get("name") or "")
        self._name_edit.setPlaceholderText("What should I call you?")
        form.addRow("Your name:", self._name_edit)

        self._location_edit = QLineEdit(u.get("location_estimate") or "")
        self._location_edit.setPlaceholderText("e.g. Temperate forest, Northern Europe")
        form.addRow("Estimated location:", self._location_edit)

        self._skills_edit = QLineEdit(", ".join(u.get("known_skills", [])))
        self._skills_edit.setPlaceholderText("e.g. nursing, carpentry, electronics")
        form.addRow("Known skills:", self._skills_edit)

        # What it has picked up from your chats — fix or remove anything wrong.
        # Lists are comma-separated.
        self._work_edit = QLineEdit(u.get("work") or "")
        self._work_edit.setPlaceholderText("e.g. nurse, at the hospital")
        form.addRow("Work:", self._work_edit)

        self._people_edit = QLineEdit(", ".join(u.get("mentioned_people", [])))
        self._people_edit.setPlaceholderText("e.g. Kate (sister), Max (dog)")
        form.addRow("People and pets:", self._people_edit)

        self._likes_edit = QLineEdit(", ".join(u.get("likes", [])))
        self._likes_edit.setPlaceholderText("e.g. hiking, Inception (favourite film)")
        form.addRow("Likes:", self._likes_edit)

        self._dislikes_edit = QLineEdit(", ".join(u.get("dislikes", [])))
        self._dislikes_edit.setPlaceholderText("e.g. horror films, mornings")
        form.addRow("Doesn't like:", self._dislikes_edit)

        notes = [n for n in u.get("notes", []) if isinstance(n, str)]
        self._notes_edit = QLineEdit("; ".join(notes))
        self._notes_edit.setPlaceholderText("Anything else it should know, separated by ;")
        form.addRow("Notes:", self._notes_edit)

        learned = QLabel("Filled in as you chat. Change or clear anything that's wrong.")
        learned.setObjectName("noteLabel")
        form.addRow(learned)

        self._notice = QCheckBox("Let the model notice things about you too (you confirm each in Review)")
        self._notice.setChecked(self.config.notice_facts)
        form.addRow(self._notice)

        self._day_spin = QSpinBox()
        self._day_spin.setMinimum(1)
        self._day_spin.setMaximum(9999)
        self._day_spin.setValue(u.get("day_count", 1))
        form.addRow("Current day:", self._day_spin)

        return w

    def _refresh_user_fields(self):
        """Show memory again after Obsidian edits were read back into it."""
        u = self.memory.data["user"]
        self._name_edit.setText(u.get("name") or "")
        self._location_edit.setText(u.get("location_estimate") or "")
        self._skills_edit.setText(", ".join(u.get("known_skills", [])))
        self._work_edit.setText(u.get("work") or "")
        self._people_edit.setText(", ".join(u.get("mentioned_people", [])))
        self._likes_edit.setText(", ".join(u.get("likes", [])))
        self._dislikes_edit.setText(", ".join(u.get("dislikes", [])))
        self._notes_edit.setText("; ".join(n for n in u.get("notes", []) if isinstance(n, str)))
        self._day_spin.setValue(u.get("day_count", 1))

    def _build_obsidian_tab(self) -> QWidget:
        """
        The vault folder, whether your own notes are used, and Update now.

        Step 1: choose the vault (the folder Obsidian opened)
        Step 2: Update now — saves what's in the You tab, reads back Me.md
                edits, writes the mind map (also done when the app closes)
        """
        from PySide6.QtWidgets import QCheckBox, QFileDialog
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(10)

        row = QHBoxLayout()
        self._vault_edit = QLineEdit(self.config.obsidian_vault or "")
        self._vault_edit.setPlaceholderText("Your vault folder")
        browse = QPushButton("Browse…")

        def pick():
            d = QFileDialog.getExistingDirectory(self, "Choose your Obsidian vault",
                                                 self._vault_edit.text() or "")
            if d:
                self._vault_edit.setText(d)
        browse.clicked.connect(pick)
        row.addWidget(self._vault_edit, 1)
        row.addWidget(browse)
        lay.addWidget(QLabel("Vault folder:"))
        lay.addLayout(row)

        self._use_notes = QCheckBox("Use my other notes as a source")
        self._use_notes.setChecked(self.config.obsidian_use_notes)
        lay.addWidget(self._use_notes)

        sync_row = QHBoxLayout()
        sync_btn = QPushButton("Update now")
        sync_btn.setObjectName("primaryBtn")
        self._obsidian_status = QLabel("")
        self._obsidian_status.setObjectName("noteLabel")
        self._obsidian_status.setWordWrap(True)
        self._obsidian_status.hide()                 # shown once there's something to say
        sync_btn.clicked.connect(self._sync_obsidian_now)
        sync_btn.setEnabled(self._obsidian_sync is not None)
        sync_row.addWidget(sync_btn, 0, Qt.AlignLeft)
        sync_row.addWidget(self._obsidian_status, 1)
        lay.addLayout(sync_row)

        about = QLabel(
            "Adds a Prometheus folder to your vault. Open Graph view in Obsidian to see the map.\n\n"
            "Me: what it knows about you. Change the properties there and it picks the change up.\n\n"
            "One note per tab, linking that tab's chats and the topics in them.\n\n"
            "Your own notes are never changed. With the box ticked, the knowledge tabs can use "
            "them, and the chat tab reads a note when you mention it by name.\n\n"
            "It also updates when you close Prometheus."
        )
        about.setObjectName("noteLabel")
        about.setWordWrap(True)
        lay.addWidget(about)
        lay.addStretch()
        return w

    def _sync_obsidian_now(self):
        from core.library import obsidian
        self._save_user_fields()
        self.config.obsidian_vault = self._vault_edit.text().strip()
        self.config.obsidian_use_notes = self._use_notes.isChecked()
        obsidian.set_vault(self.config.obsidian_vault, self.config.obsidian_use_notes)
        msg = self._obsidian_sync() if self._obsidian_sync else ""
        n = obsidian.note_count() if self.config.obsidian_use_notes else 0
        if obsidian.vault_path() and self.config.obsidian_use_notes:
            msg += f" {n} of your notes available as a source."
        self._obsidian_status.setText(msg)
        self._obsidian_status.setVisible(bool(msg))
        self._refresh_user_fields()

    def _build_assistant_tab(self) -> QWidget:
        """
        Who's talking: pick a voice, and give that voice its own name and
        personality. Each voice remembers its own; switching voices here
        brings back that voice's name and personality.
        """
        from PySide6.QtWidgets import QPlainTextEdit
        import copy
        w = QWidget()
        form = QFormLayout(w)
        form.setSpacing(12)

        # Step 1: the voice (from voices/ — one folder per character)
        self._profiles = copy.deepcopy(self.config.voice_profiles)
        self._voice_combo = QComboBox()
        from core.voice.voice_manager import VoiceManager
        voices = VoiceManager().all_voices()
        if voices:
            for v in voices:
                self._voice_combo.addItem(v.name)
            idx = self._voice_combo.findText(self.config.tts_voice)
            self._voice_combo.setCurrentIndex(idx if idx >= 0 else 0)
        else:
            self._voice_combo.addItem("No voices found")
            self._voice_combo.setEnabled(False)
        form.addRow("Voice:", self._voice_combo)
        self._shown_voice = self._current_voice()

        # Step 2: that voice's name and personality
        self._assistant_name = QLineEdit(self.config.assistant_name or "Prometheus")
        self._assistant_name.setPlaceholderText("Prometheus")
        self._assistant_name.setMaxLength(40)
        form.addRow("Name:", self._assistant_name)

        self._assistant_persona = QPlainTextEdit(self.config.assistant_persona or "")
        self._assistant_persona.setPlaceholderText(
            "How this voice comes across — leave empty for a plain, easy-going friend.\n"
            "e.g. a calm old sailor who's seen a lot and doesn't rush you\n"
            "e.g. dry sense of humour, straight talker, loves a tangent"
        )
        self._assistant_persona.setFixedHeight(96)
        form.addRow("Personality:", self._assistant_persona)
        self._voice_combo.currentTextChanged.connect(self._swap_profile)

        note = QLabel(
            "Each voice keeps its own name and personality.\n"
            "The name shows in the header and on the chat tab. Personality shapes\n"
            "how it talks to you; library answers stay factual."
        )
        note.setObjectName("noteLabel")
        from PySide6.QtWidgets import QSizePolicy
        note.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        form.addRow(note)
        return w

    def _current_voice(self) -> str:
        return self._voice_combo.currentText() if self._voice_combo.isEnabled() else ""

    def _keep_profile(self):
        """The fields as typed → the profile of the voice they belong to."""
        if self._shown_voice:
            self._profiles[self._shown_voice] = {
                "name": self._assistant_name.text().strip() or "Prometheus",
                "persona": self._assistant_persona.toPlainText().strip()}

    def _swap_profile(self, voice: str):
        """Voice changed: keep what was typed for the old one, show the new one's."""
        self._keep_profile()
        self._shown_voice = voice
        prof = self._profiles.get(voice)
        if prof:
            self._assistant_name.setText(prof.get("name") or "Prometheus")
            self._assistant_persona.setPlainText(prof.get("persona", ""))
        # a voice with no profile yet starts from what's showing — edit it from there

    def _build_model_tab(self) -> QWidget:
        """
        Pick the models. Each box lists what's installed in Ollama, and
        you can also type any model name (get it first with python -m core.ai.ollama_local --pull).
        """
        from core.ai.llm import LLMEngine

        w = QWidget()
        form = QFormLayout(w)
        form.setSpacing(12)

        self._ollama_url = QLineEdit(self.config.ollama_url)
        self._ollama_url.setPlaceholderText("http://localhost:11434")
        form.addRow("Ollama address:", self._ollama_url)

        # Pick from what Ollama has installed — no typing.
        # Two models work together: the speaker talks to you; the librarian
        # only reads the library and passes the speaker the facts.
        self._fast_model = QComboBox()            # the speaker
        form.addRow("Speaker (talks to you):", self._fast_model)

        self._companion_model = QComboBox()       # the librarian
        form.addRow("Librarian (reads the library):", self._companion_model)

        self._two_models = QCheckBox("Use the librarian (the speaker only states facts it found)")
        self._two_models.setChecked(self.config.two_models)
        self._two_models.toggled.connect(self._companion_model.setEnabled)
        self._companion_model.setEnabled(self.config.two_models)
        form.addRow(self._two_models)

        # Performance: Automatic picks full or low power from the hardware
        self._power = QComboBox()
        for label, value in (("Automatic (recommended)", "auto"), ("Full", "full"),
                             ("Low power — leaner, quicker answers on slow computers", "low")):
            self._power.addItem(f"{label}   ▾", value)
        self._power.setCurrentIndex(max(0, self._power.findData(self.config.power_mode)))
        form.addRow("Performance:", self._power)
        found = getattr(self.config, "hardware_summary", "")
        why = getattr(self.config, "power_reason", "")
        now = "low power" if getattr(self.config, "low_power_active", False) else "full"
        detected = QLabel((f"This computer: {found}.\n" if found else
                           "This computer: checked once the models have loaded.\n") +
                          f"Now using: {now}" + (f" — {why}." if why else "."))
        detected.setObjectName("noteLabel")
        detected.setWordWrap(True)
        form.addRow(detected)

        row = QHBoxLayout()
        refresh = QPushButton("Check Ollama")
        refresh.clicked.connect(self._refresh_models)
        self._ollama_status = QLabel("")
        self._ollama_status.setObjectName("infoLabel")
        self._ollama_status.setWordWrap(True)
        row.addWidget(refresh)
        row.addWidget(self._ollama_status, 1)
        form.addRow(row)

        self._max_tokens = QSpinBox()
        self._max_tokens.setMinimum(50)
        self._max_tokens.setMaximum(2000)
        self._max_tokens.setValue(self.config.max_tokens)
        form.addRow("Max response length:", self._max_tokens)

        self._rag_results = QSpinBox()
        self._rag_results.setMinimum(1)
        self._rag_results.setMaximum(10)
        self._rag_results.setValue(self.config.rag_results)
        form.addRow("Library passages used:", self._rag_results)

        from core.ai import ollama_local
        if ollama_local.has_local_models():
            where = ("Models are kept in prometheus\\models. To add one:\n"
                     "    python -m core.ai.ollama_local --pull <model name>\n"
                     "then press Check Ollama.")
        else:
            where = ("The lists show the models installed in Ollama. To keep them in\n"
                     "the prometheus folder instead:  python -m core.ai.ollama_local --move")
        note = QLabel(where + "\nSuggested: speaker qwen3:1.7b, librarian LFM2.5 1.2B.")
        note.setObjectName("noteLabel")
        form.addRow(note)

        self._llm_probe = LLMEngine(self.config)
        self._refresh_models()
        return w

    def _refresh_models(self):
        """
        Ask Ollama which models are installed — on a background thread, so the
        window opens straight away and never freezes while Ollama answers.

        Step 1: show the current choices immediately (marked "checking…")
        Step 2: probe the typed address in the background
        Step 3: fill both lists with what's installed
        """
        from core.app.config import Config as _C
        from PySide6.QtCore import QThread, Signal

        current = (self._fast_model.currentData() or self.config.speaker_model,
                   self._companion_model.currentData() or self.config.librarian_model)

        # Step 1
        self._ollama_status.setText("Checking Ollama…")
        if self._fast_model.count() == 0:
            self._fill_model_boxes([], current)

        # Step 2
        probe = self._llm_probe
        saved = {k: v for k, v in self.config.__dict__.items() if k in _C.__dataclass_fields__}
        probe.config = _C(**{**saved,
                             "ollama_url": self._ollama_url.text().strip() or self.config.ollama_url})

        class _Probe(QThread):
            done = Signal(dict)
            def run(inner):
                ok = probe.is_available()
                inner.done.emit({"ok": ok, "error": getattr(probe, "last_error", ""),
                                 "installed": probe.list_models() if ok else []})

        if getattr(self, "_probe_thread", None) and self._probe_thread.isRunning():
            return
        self._probe_thread = _Probe(self)
        self._probe_thread.done.connect(lambda r, cur=current: self._on_models(r, cur))
        self._probe_thread.start()

    def _on_models(self, result: dict, current):
        # Step 3
        installed = result["installed"]
        if result["ok"]:
            self._ollama_status.setText(
                f"Connected — {len(installed)} model(s) installed." if installed
                else "Connected, but no models yet. Run: python -m core.ai.ollama_local --pull <model name>"
            )
        else:
            self._ollama_status.setText(
                f"Can't reach Ollama ({result['error']}). Open the Ollama app, "
                f"or run: ollama serve"
            )
        # Keep whatever was picked while the check ran
        current = (self._fast_model.currentData() or current[0],
                   self._companion_model.currentData() or current[1])
        self._fill_model_boxes(installed, current)

    def _fill_model_boxes(self, installed, current):
        """Each item's data is the exact Ollama name. A saved model that isn't
        installed stays visible (marked) so you can see what's set."""
        from core.ai.llm import LLMEngine as _L
        checking = not installed and self._ollama_status.text().startswith("Checking")
        for box, value in ((self._fast_model, current[0]), (self._companion_model, current[1])):
            box.blockSignals(True)
            box.clear()
            for m in installed:
                box.addItem(f"{m}   ▾", m)   # ▾ shows it's a list (styled arrows draw nothing)
            match = next((m for m in installed if _L._has_model([m], value)), None)
            if match:
                box.setCurrentIndex(box.findData(match))
            elif value:
                note = "checking…" if checking else "not installed"
                box.addItem(f"{value}  ({note})   ▾", value)
                box.setCurrentIndex(box.count() - 1)
            box.setEnabled(box.count() > 0)
            box.blockSignals(False)

    def _build_voice_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setSpacing(12)

        self._voice_enabled = QCheckBox("Enable text-to-speech")
        self._voice_enabled.setChecked(self.config.voice_enabled)
        form.addRow(self._voice_enabled)

        self._stt_enabled = QCheckBox("Enable voice input (microphone)")
        self._stt_enabled.setChecked(self.config.stt_enabled)
        form.addRow(self._stt_enabled)

        self._stt_model = QComboBox()
        self._stt_model.addItems(["tiny", "base", "small", "medium"])
        self._stt_model.setCurrentText(self.config.stt_model)
        form.addRow("Whisper model:", self._stt_model)

        # Status note
        from core.voice.voice_manager import VoiceManager
        status = VoiceManager().status_summary()
        note = QLabel(
            f"{status}\n\n"
            "Add voices by placing each character in its own\n"
            "subfolder under voices/ containing the .onnx model.\n\n"
            "To set up or check voice (Piper, Whisper, microphone):\n"
            "python tools/setup_voice.py"
        )
        note.setObjectName("noteLabel")
        form.addRow(note)

        return w

    def _build_about_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setAlignment(Qt.AlignTop)

        about = QLabel(
            "<h2>⚡ Prometheus</h2>"
            "<p>A complete offline AI companion for survival, "
            "rebuilding and human connection.</p>"
            "<p><b>Fully offline. Completely unlimited. Forever free.</b></p>"
            "<p>No internet. No subscription. No servers.<br>"
            "No token limits. No rate limits. No data leaving your device.</p>"
            "<p>Built on:<br>"
            "• LFM2.5 1.2B Instruct by default, any Ollama model (Settings → Model)<br>"
            "• Piper TTS<br>"
            "• Faster-Whisper STT<br>"
            "• ChromaDB + sentence-transformers<br>"
            "• PySide6</p>"
            "<p><i>\"The sum of everything a human needs to know<br>"
            "to go from nothing to thriving civilization.\"</i></p>"
        )
        about.setWordWrap(True)
        about.setTextFormat(Qt.RichText)
        layout.addWidget(about)

        return w

    def _save(self):
        self._save_user_fields()
        self.config.obsidian_vault = self._vault_edit.text().strip()
        self.config.obsidian_use_notes = self._use_notes.isChecked()
        self._save_rest()

    def _save_user_fields(self):
        # Save user settings
        u = self.memory.data["user"]
        u["name"] = self._name_edit.text().strip() or None
        u["location_estimate"] = self._location_edit.text().strip() or None
        u["day_count"] = self._day_spin.value()

        # Lists: comma-separated, notes: ";"-separated. An empty box clears it.
        def items(text, sep=","):
            return [s.strip() for s in text.split(sep) if s.strip()]
        u["known_skills"]     = items(self._skills_edit.text())
        u["work"]             = self._work_edit.text().strip() or None
        u["mentioned_people"] = items(self._people_edit.text())
        u["likes"]            = items(self._likes_edit.text())
        u["dislikes"]         = items(self._dislikes_edit.text())
        u["notes"]            = items(self._notes_edit.text(), ";")
        self.config.notice_facts = self._notice.isChecked()

    def _save_rest(self):

        # Save model settings
        speaker = (self._fast_model.currentData() or self.config.speaker_model).strip()
        self.config.speaker_model   = speaker
        self.config.librarian_model = (self._companion_model.currentData()
                                       or self.config.librarian_model).strip()
        self.config.two_models      = self._two_models.isChecked()
        self.config.power_mode      = self._power.currentData() or "auto"

        # Assistant
        # Assistant: every voice's profile, then switch to the chosen voice
        self._keep_profile()
        self.config.voice_profiles = self._profiles
        voice = self._current_voice()
        self.config.store_profile(voice, self._assistant_name.text().strip(),
                                  self._assistant_persona.toPlainText().strip())
        self.config.use_voice(voice or self.config.tts_voice)
        self.config.ollama_url      = self._ollama_url.text().strip() or "http://localhost:11434"
        self.config.max_tokens = self._max_tokens.value()
        self.config.rag_results = self._rag_results.value()

        # Save voice settings
        self.config.voice_enabled = self._voice_enabled.isChecked()
        self.config.stt_enabled   = self._stt_enabled.isChecked()
        self.config.stt_model     = self._stt_model.currentText()

        self.accept()
