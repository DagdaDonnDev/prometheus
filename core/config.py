"""
Configuration management for Prometheus
"""

import json
import os
from dataclasses import dataclass, field, asdict
from typing import Optional


CONFIG_PATH = "memory/config.json"


@dataclass
class Config:
    # Model settings
    llm_model: str = "llama3.2:3b"          # default — smooth streaming, good reasoning
    companion_model: str = "llama3.2:3b"    # companion tab — can set higher quality here
    fast_model: str = "llama3.2:3b"         # knowledge tabs — can set smaller here
    stt_model: str = "tiny"
    tts_voice: str = ""
    ollama_url: str = "http://localhost:11434"

    # Performance
    max_tokens: int = 300
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
