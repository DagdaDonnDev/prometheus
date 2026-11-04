"""
Voice Manager
=============
Scans voices/ directory for Piper voice models.
Each subfolder = one character/voice.
Character name = folder name.

Expected structure:
    voices/
        Rocky/
            en_US-rocky-medium.onnx
            en_US-rocky-medium.onnx.json
        Amy/
            en_US-amy-medium.onnx
            en_US-amy-medium.onnx.json
        Alan/
            en_GB-alan-medium.onnx
            en_GB-alan-medium.onnx.json

The .onnx.json config file is required by Piper alongside the model.
Both files must be in the same folder.
Download voices from: https://huggingface.co/rhasspy/piper-voices
"""

import subprocess
import tempfile
import os
from pathlib import Path
from typing import Optional, List, Dict
from dataclasses import dataclass


VOICES_DIR = Path("voices")


@dataclass
class PiperVoice:
    name: str           # Character name (folder name)
    model: Path         # .onnx file
    config: Path        # .onnx.json file
    folder: Path        # Parent folder


class VoiceManager:
    """
    Scans voices/ directory and manages all Piper voices.
    Character name = subfolder name.
    """

    def __init__(self):
        self._voices: Dict[str, PiperVoice] = {}
        self.scan()

    def scan(self):
        """Scan voices/ directory and detect all Piper voices."""
        self._voices = {}

        if not VOICES_DIR.exists():
            VOICES_DIR.mkdir(parents=True, exist_ok=True)
            return

        for folder in sorted(VOICES_DIR.iterdir()):
            if not folder.is_dir():
                continue

            voice = self._detect_piper_voice(folder)
            if voice:
                self._voices[folder.name] = voice

    def _detect_piper_voice(self, folder: Path) -> Optional[PiperVoice]:
        """Find .onnx + .onnx.json pair in a voice folder."""
        onnx_files = list(folder.glob("*.onnx"))

        # Filter out .onnx.json files — we want only the model
        model_files = [f for f in onnx_files if not f.name.endswith(".onnx.json")]

        if not model_files:
            return None

        model = model_files[0]  # Use first .onnx found

        # Look for matching config — same name with .json appended
        config = Path(str(model) + ".json")
        if not config.exists():
            # Try any .json in the folder
            json_files = list(folder.glob("*.json"))
            if json_files:
                config = json_files[0]
            else:
                # Piper can sometimes run without config — try anyway
                config = config  # keep the expected path even if missing

        return PiperVoice(
            name=folder.name,
            model=model,
            config=config,
            folder=folder,
        )

    # ── Public API ─────────────────────────────────────────────────────────

    def all_voices(self) -> List[PiperVoice]:
        """Return all detected voices, sorted by character name."""
        return sorted(self._voices.values(), key=lambda v: v.name.lower())

    def get(self, name: str) -> Optional[PiperVoice]:
        """Get a voice by character name."""
        return self._voices.get(name)

    def names(self) -> List[str]:
        """Return list of all character names."""
        return sorted(self._voices.keys())

    def count(self) -> int:
        return len(self._voices)

    def first(self) -> Optional[PiperVoice]:
        """Return first available voice (alphabetical)."""
        voices = self.all_voices()
        return voices[0] if voices else None

    def speak(
        self,
        text: str,
        voice: PiperVoice,
        output_path: str,
        rate: float = 1.0,
    ) -> bool:
        """
        Synthesise text to a wav file using Piper.
        Returns True on success.
        """
        if not text.strip():
            return False

        cmd = ["piper", "--model", str(voice.model)]

        if voice.config.exists():
            cmd += ["--config", str(voice.config)]

        cmd += ["--output_file", output_path]

        # Piper controls speed via sentence silence and length scale
        # length_scale > 1 = slower, < 1 = faster
        length_scale = 1.0 / rate  # invert: rate 0.85 → scale 1.18
        cmd += ["--length_scale", f"{length_scale:.2f}"]

        try:
            result = subprocess.run(
                cmd,
                input=text.encode("utf-8"),
                capture_output=True,
                timeout=30,
            )
            return result.returncode == 0
        except FileNotFoundError:
            return False  # piper binary not found
        except subprocess.TimeoutExpired:
            return False

    def piper_available(self) -> bool:
        """Check if piper binary is on PATH."""
        try:
            result = subprocess.run(
                ["piper", "--version"],
                capture_output=True,
                timeout=3,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def status_summary(self) -> str:
        """Human-readable status for settings/status bar."""
        if not self.piper_available():
            return "Piper not found — install from github.com/rhasspy/piper"
        if not self._voices:
            return "No voices found — add folders to voices/"
        names = ", ".join(self.names())
        return f"{self.count()} voice(s): {names}"
