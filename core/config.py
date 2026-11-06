"""
Configuration management for Prometheus
"""

import json
import os
from dataclasses import dataclass, field, asdict
from typing import Optional


CONFIG_PATH = "memory/config.json"
DEFAULT_MODEL = "hf.co/LiquidAI/LFM2.5-1.2B-Instruct-GGUF:latest"


@dataclass
class Config:
    # Model settings
    # Default: LFM2.5 1.2B Instruct — fast and good on a modest PC/GPU.
    # Get it with:  python -m core.ollama_local --pull hf.co/LiquidAI/LFM2.5-1.2B-Instruct-GGUF:latest
    # (kept in prometheus/models — see core/ollama_local.py)
    llm_model: str = DEFAULT_MODEL           # summaries, checks (mirrors fast_model)
    companion_model: str = DEFAULT_MODEL     # chat tab
    fast_model: str = DEFAULT_MODEL          # knowledge tabs
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
    assistant_name: str = "Prometheus"
    assistant_persona: str = ""   # e.g. "a calm old sailor who's seen a lot" — empty = plain friend

    # Obsidian (Settings → Obsidian): the vault folder, and whether your own
    # notes there are used as a source
    obsidian_vault: str = ""
    obsidian_use_notes: bool = True

    # User
    user_name: Optional[str] = None
    day_start: Optional[str] = None

    def model_for_tab(self, tab_id: str) -> str:
        """Return the right model for a given tab."""
        if tab_id == "prometheus":
            return self.companion_model
        return self.fast_model

    def save(self):
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, "w") as f:
            json.dump(asdict(self), f, indent=2)

    @classmethod
    def load(cls):
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r") as f:
                data = json.load(f)
            cfg = cls(**{k: v for k, v in data.items()
                         if k in cls.__dataclass_fields__})
            # Older Settings only changed llm_model, which chats never used.
            # If that was changed and the per-tab models weren't, carry it over.
            default = cls.__dataclass_fields__["fast_model"].default
            if cfg.llm_model and cfg.llm_model != default and cfg.fast_model == default:
                cfg.fast_model = cfg.llm_model
                if cfg.companion_model == default:
                    cfg.companion_model = cfg.llm_model
            return cfg
        return cls()
