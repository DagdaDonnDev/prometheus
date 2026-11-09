"""
Configuration management for Prometheus
"""

import json
import os
from dataclasses import dataclass, field, asdict
from typing import Dict, Optional


CONFIG_PATH = "memory/config.json"
DEFAULT_MODEL = "hf.co/LiquidAI/LFM2.5-1.2B-Instruct-GGUF:latest"
# Two models work together (core/ai/librarian.py):
#   speaker   — the only one that talks to you (Qwen3 1.7B, thinking off)
#   librarian — reads the library and lists facts; never talks to you (LFM2.5)
DEFAULT_SPEAKER = "qwen3:1.7b"
DEFAULT_LIBRARIAN = DEFAULT_MODEL


@dataclass
class Config:
    # Model settings
    # Default: LFM2.5 1.2B Instruct — fast and good on a modest PC/GPU.
    # Get it with:  python -m core.ai.ollama_local --pull hf.co/LiquidAI/LFM2.5-1.2B-Instruct-GGUF:latest
    # (kept in prometheus/models — see core/ai/ollama_local.py)
    llm_model: str = DEFAULT_MODEL           # summaries, checks (mirrors fast_model)
    companion_model: str = DEFAULT_MODEL     # chat tab
    fast_model: str = DEFAULT_MODEL          # knowledge tabs
    speaker_model: str = DEFAULT_SPEAKER       # every reply you read or hear
    librarian_model: str = DEFAULT_LIBRARIAN   # pulls facts out of the library
    two_models: bool = True                    # off = the speaker reads the library itself (old way)
    stt_model: str = "tiny"
    tts_voice: str = ""
    ollama_url: str = "http://localhost:11434"

    # Performance
    max_tokens: int = 300
    # Same context size on every request — Ollama reloads the model when it changes
    context_window: int = 4096
    # Keep the model in memory between messages (Ollama's default is 5 minutes)
    keep_alive: str = "30m"
    context_messages: int = 20
    rag_results: int = 3
    stream_tokens: bool = True

    # Voice
    voice_enabled: bool = True
    stt_enabled: bool = True
    wake_word_enabled: bool = False
    tts_rate: float = 1.0

    # UI
    theme: str = "dark"
    font_size: int = 13
    show_day_counter: bool = True

    # Assistant — what it's called and how it comes across (Settings → Assistant)
    # The ACTIVE voice's name and personality (everything reads these two);
    # each voice keeps its own in voice_profiles: {voice: {"name", "persona"}}
    assistant_name: str = "Prometheus"
    assistant_persona: str = ""   # e.g. "a calm old sailor who's seen a lot" — empty = plain friend
    voice_profiles: Dict[str, Dict[str, str]] = field(default_factory=dict)

    # Obsidian (Settings → Obsidian): the vault folder, and whether your own
    # notes there are used as a source
    obsidian_vault: str = ""
    obsidian_use_notes: bool = True

    # User
    user_name: Optional[str] = None
    day_start: Optional[str] = None

    def model_for_tab(self, tab_id: str) -> str:
        """The model that talks to you — the same in every tab."""
        return self.speaker_model or self.companion_model

    def use_voice(self, voice: str):
        """
        Switch to a voice and to that voice's own name and personality.
        A voice with no profile yet keeps the current one (so nothing is lost).
        """
        self.tts_voice = voice or ""
        prof = self.voice_profiles.get(self.tts_voice)
        if prof:
            self.assistant_name = prof.get("name") or "Prometheus"
            self.assistant_persona = prof.get("persona", "")

    def store_profile(self, voice: str, name: str, persona: str):
        """Remember a voice's name and personality (and use them if it's the active voice)."""
        if voice:
            self.voice_profiles[voice] = {"name": name or "Prometheus", "persona": persona or ""}
        if voice == self.tts_voice or not voice:
            self.assistant_name = name or "Prometheus"
            self.assistant_persona = persona or ""

    def save(self):
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls):
        """
        Settings saved last time (memory/config.json), or the defaults.
        main.py used to create Config() directly, so nothing chosen in
        Settings — persona, voice, models — survived a restart.
        """
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, ValueError):
                return cls()            # unreadable — start from defaults rather than crash
            cfg = cls(**{k: v for k, v in data.items()
                         if k in cls.__dataclass_fields__})
            # Before per-voice profiles: the one persona belongs to the chosen voice
            if not cfg.voice_profiles and cfg.tts_voice and \
                    (cfg.assistant_persona or cfg.assistant_name != "Prometheus"):
                cfg.voice_profiles[cfg.tts_voice] = {"name": cfg.assistant_name,
                                                     "persona": cfg.assistant_persona}
            cfg.use_voice(cfg.tts_voice)
            # Older Settings only changed llm_model, which chats never used.
            # If that was changed and the per-tab models weren't, carry it over.
            default = cls.__dataclass_fields__["fast_model"].default
            if cfg.llm_model and cfg.llm_model != default and cfg.fast_model == default:
                cfg.fast_model = cfg.llm_model
                if cfg.companion_model == default:
                    cfg.companion_model = cfg.llm_model
            return cfg
        return cls()
