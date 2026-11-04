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

        tabs.addTab(self._build_user_tab(), "👤 Identity")
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

    def _build_model_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setSpacing(12)

        self._model_edit = QLineEdit(self.config.llm_model)
        self._model_edit.setPlaceholderText("e.g. llama3.2:3b")
        form.addRow("LLM model:", self._model_edit)

        self._ollama_url = QLineEdit(self.config.ollama_url)
        form.addRow("Ollama URL:", self._ollama_url)

        self._max_tokens = QSpinBox()
        self._max_tokens.setMinimum(50)
        self._max_tokens.setMaximum(2000)
        self._max_tokens.setValue(self.config.max_tokens)
        form.addRow("Max response tokens:", self._max_tokens)

        self._rag_results = QSpinBox()
        self._rag_results.setMinimum(1)
        self._rag_results.setMaximum(10)
        self._rag_results.setValue(self.config.rag_results)
        form.addRow("Knowledge results:", self._rag_results)

        note = QLabel(
            "Recommended model: llama3.2:3b\n"
            "Pull with: ollama pull llama3.2:3b\n\n"
            "Companion tab can use a different model:\n"
            "ollama pull llama3.2:3b\n\n"
            "Smaller fallback: llama3.2:1b\n"
            "Larger quality: mistral:7b-instruct-q4_0"
        )
        note.setObjectName("noteLabel")
        form.addRow(note)

        return w

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
        self.config.llm_model = self._model_edit.text().strip()
        self.config.ollama_url = self._ollama_url.text().strip()
        self.config.max_tokens = self._max_tokens.value()
        self.config.rag_results = self._rag_results.value()

        # Save voice settings
        self.config.voice_enabled = self._voice_enabled.isChecked()
        self.config.stt_enabled   = self._stt_enabled.isChecked()
        self.config.tts_voice     = self._voice_combo.currentText()
        self.config.stt_model     = self._stt_model.currentText()

        self.accept()
