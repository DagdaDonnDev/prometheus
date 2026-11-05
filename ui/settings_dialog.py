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

from core.config import Config
from core.memory import Memory


class SettingsDialog(QDialog):
    def __init__(self, config: Config, memory: Memory, parent=None):
        super().__init__(parent)
        self.config = config
        self.memory = memory

        self.setWindowTitle("Prometheus — Settings")
        self.setMinimumWidth(450)
        self.setMinimumHeight(400)

        layout = QVBoxLayout(self)

        tabs = QTabWidget()

        tabs.addTab(self._build_user_tab(), "👤 You")
        tabs.addTab(self._build_assistant_tab(), "💬 Assistant")
        tabs.addTab(self._build_model_tab(), "🤖 Model")
        tabs.addTab(self._build_voice_tab(), "🎤 Voice")
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

        self._day_spin = QSpinBox()
        self._day_spin.setMinimum(1)
        self._day_spin.setMaximum(9999)
        self._day_spin.setValue(u.get("day_count", 1))
        form.addRow("Current day:", self._day_spin)

        return w

    def _build_assistant_tab(self) -> QWidget:
        """What the assistant is called and how it comes across."""
        from PySide6.QtWidgets import QPlainTextEdit
        w = QWidget()
        form = QFormLayout(w)
        form.setSpacing(12)

        self._assistant_name = QLineEdit(self.config.assistant_name or "Prometheus")
        self._assistant_name.setPlaceholderText("Prometheus")
        self._assistant_name.setMaxLength(40)
        form.addRow("Name:", self._assistant_name)

        self._assistant_persona = QPlainTextEdit(self.config.assistant_persona or "")
        self._assistant_persona.setPlaceholderText(
            "How it comes across — leave empty for a plain, easy-going friend.\n"
            "e.g. a calm old sailor who's seen a lot and doesn't rush you\n"
            "e.g. dry sense of humour, straight talker, loves a tangent"
        )
        self._assistant_persona.setFixedHeight(96)
        form.addRow("Personality:", self._assistant_persona)

        note = QLabel(
            "The name shows in the header and on the chat tab, and the model uses it.\n"
            "Personality shapes the chat tab. Knowledge tabs stay factual."
        )
        note.setObjectName("noteLabel")
        from PySide6.QtWidgets import QSizePolicy
        note.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        form.addRow(note)
        return w

    def _build_model_tab(self) -> QWidget:
        """
        Pick the models. Each box lists what's installed in Ollama, and
        you can also type any model name (pull it first with ollama pull).
        """
        from core.llm import LLMEngine

        w = QWidget()
        form = QFormLayout(w)
        form.setSpacing(12)

        self._ollama_url = QLineEdit(self.config.ollama_url)
        self._ollama_url.setPlaceholderText("http://localhost:11434")
        form.addRow("Ollama address:", self._ollama_url)

        # Pick from what Ollama has installed — no typing
        self._fast_model = QComboBox()
        form.addRow("Knowledge tabs model:", self._fast_model)

        self._companion_model = QComboBox()
        form.addRow("Chat tab model:", self._companion_model)

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

        note = QLabel(
            "The lists show the models installed in Ollama. To add one:\n"
            "    ollama pull <model name>     then press Check Ollama.\n"
            "The chat tab can use a different model from the knowledge tabs."
        )
        note.setObjectName("noteLabel")
        form.addRow(note)

        self._llm_probe = LLMEngine(self.config)
        self._refresh_models()
        return w

    def _refresh_models(self):
        """Step 1: reach Ollama at the typed address. Step 2: fill both boxes."""
        from core.config import Config as _C
        probe = self._llm_probe
        probe.config = _C(**{**self.config.__dict__,
                             "ollama_url": self._ollama_url.text().strip() or self.config.ollama_url})
        current = (self._fast_model.currentData() or self.config.fast_model,
                   self._companion_model.currentData() or self.config.companion_model)

        if probe.is_available():
            installed = probe.list_models()
            self._ollama_status.setText(
                f"Connected — {len(installed)} model(s) installed." if installed
                else "Connected, but no models yet. Run: ollama pull llama3.2:3b"
            )
        else:
            installed = []
            self._ollama_status.setText(
                f"Can't reach Ollama ({probe.last_error}). Open the Ollama app, "
                f"or run: ollama serve"
            )

        # Each item's data is the exact Ollama name. A saved model that isn't
        # installed stays visible (marked) so you can see what's set.
        from core.llm import LLMEngine as _L
        for box, value in ((self._fast_model, current[0]), (self._companion_model, current[1])):
            box.blockSignals(True)
            box.clear()
            for m in installed:
                box.addItem(f"{m}   ▾", m)   # ▾ shows it's a list (styled arrows draw nothing)
            match = next((m for m in installed if _L._has_model([m], value)), None)
            if match:
                box.setCurrentIndex(box.findData(match))
            elif value:
                box.addItem(f"{value}  (not installed)   ▾", value)
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

        # Voice selector — populated from voices/ folder
        self._voice_combo = QComboBox()
        from core.voice_manager import VoiceManager
        vm = VoiceManager()
        voices = vm.all_voices()

        if voices:
            for v in voices:
                self._voice_combo.addItem(v.name)
            # Select current voice
            current = self.config.tts_voice
            idx = self._voice_combo.findText(current)
            if idx >= 0:
                self._voice_combo.setCurrentIndex(idx)
            else:
                self._voice_combo.setCurrentIndex(0)
        else:
            self._voice_combo.addItem("No voices found")
            self._voice_combo.setEnabled(False)

        form.addRow("Voice character:", self._voice_combo)

        self._stt_model = QComboBox()
        self._stt_model.addItems(["tiny", "base", "small", "medium"])
        self._stt_model.setCurrentText(self.config.stt_model)
        form.addRow("Whisper model:", self._stt_model)

        # Status note
        status = vm.status_summary()
        note = QLabel(
            f"{status}\n\n"
            "Add voices by placing each character in its own\n"
            "subfolder under voices/ containing the .onnx model.\n\n"
            "Voice input requires:\n"
            "pip install faster-whisper sounddevice"
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
            "• Llama 3.2 3B (via Ollama)<br>"
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
        # Save user settings
        u = self.memory.data["user"]
        u["name"] = self._name_edit.text().strip() or None
        u["location_estimate"] = self._location_edit.text().strip() or None
        u["day_count"] = self._day_spin.value()

        skills_text = self._skills_edit.text().strip()
        if skills_text:
            u["known_skills"] = [s.strip() for s in skills_text.split(",") if s.strip()]

        # Save model settings
        fast = (self._fast_model.currentData() or self.config.fast_model).strip()
        self.config.fast_model      = fast
        self.config.llm_model       = fast      # summaries and checks use the same model
        self.config.companion_model = (self._companion_model.currentData() or fast).strip()

        # Assistant
        self.config.assistant_name    = self._assistant_name.text().strip() or "Prometheus"
        self.config.assistant_persona = self._assistant_persona.toPlainText().strip()
        self.config.ollama_url      = self._ollama_url.text().strip() or "http://localhost:11434"
        self.config.max_tokens = self._max_tokens.value()
        self.config.rag_results = self._rag_results.value()

        # Save voice settings
        self.config.voice_enabled = self._voice_enabled.isChecked()
        self.config.stt_enabled   = self._stt_enabled.isChecked()
        self.config.tts_voice     = self._voice_combo.currentText()
        self.config.stt_model     = self._stt_model.currentText()

        self.accept()
