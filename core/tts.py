"""
TTS Engine
==========
Piper-based text-to-speech with token streaming.
Uses VoiceManager to load voices by character name.
Fully offline.
"""

import os
import re
import queue
import tempfile
import threading
import subprocess
from typing import Optional

from core.voice_manager import VoiceManager, PiperVoice


class TTSEngine:

    def __init__(self, config):
        self.config        = config
        self.enabled       = config.voice_enabled
        self.voice_manager = VoiceManager()

        # Resolve active voice from config (character name)
        self._active_voice: Optional[PiperVoice] = self._resolve_voice(
            config.tts_voice
        )

        self._speak_queue: queue.Queue = queue.Queue()
        self._stop_event   = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None
        self._token_buffer = ""

        self.available = self.voice_manager.piper_available()

        if self.available and self.enabled and self._active_voice:
            self._start_worker()

    def _resolve_voice(self, name: str) -> Optional[PiperVoice]:
        """
        Resolve a voice by character name.
        Falls back to first available voice if name not found.
        """
        if name:
            voice = self.voice_manager.get(name)
            if voice:
                return voice
        return self.voice_manager.first()

    # ── Worker thread ──────────────────────────────────────────────────────

    def _start_worker(self):
        self._stop_event.clear()
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            daemon=True,
        )
        self._worker_thread.start()

    def _worker_loop(self):
        while not self._stop_event.is_set():
            try:
                text = self._speak_queue.get(timeout=0.5)
                if text is None:
                    break
                self._speak(text)
                self._speak_queue.task_done()
            except queue.Empty:
                continue

    def _speak(self, text: str):
        if not text.strip() or not self._active_voice:
            return

        tmp = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                tmp = f.name

            success = self.voice_manager.speak(
                text=text,
                voice=self._active_voice,
                output_path=tmp,
                rate=self.config.tts_rate,
            )

            if success and os.path.exists(tmp):
                self._play(tmp)

        except Exception:
            pass
        finally:
            if tmp:
                try:
                    os.unlink(tmp)
                except Exception:
                    pass

    def _play(self, path: str):
        for player in ["aplay", "paplay", "afplay", "mpg123"]:
            try:
                subprocess.run(
                    [player, path],
                    capture_output=True,
                    timeout=60,
                )
                return
            except FileNotFoundError:
                continue
            except Exception:
                return

    # ── Token streaming interface ──────────────────────────────────────────

    def on_token(self, token: str):
        """Called for each token from LLM stream. Buffers until natural boundary."""
        if not self.available or not self.enabled or not self._active_voice:
            return

        self._token_buffer += token

        if self._should_speak(self._token_buffer):
            text = self._token_buffer.strip()
            self._token_buffer = ""
            if text:
                self._speak_queue.put(text)

    def flush(self):
        """Speak any remaining buffered text."""
        if self._token_buffer.strip():
            self._speak_queue.put(self._token_buffer.strip())
            self._token_buffer = ""

    def _should_speak(self, buffer: str) -> bool:
        """
        Fire on natural speech boundaries.
        Tuned for conversational feel — speak early and often
        rather than waiting for long chunks.
        """
        stripped = buffer.strip()
        if not stripped:
            return False

        # Hard sentence endings — always speak
        if re.search(r'[.!?]\s*$', buffer):
            return True

        # Comma with enough content — natural breath point
        if ',' in buffer and len(stripped) > 35:
            return True

        # Em dash or ellipsis — natural pause
        if re.search(r'(—|\.\.\.)\s*$', buffer):
            return True

        # Natural clause connectors — speak before continuing
        clause_endings = [
            ' and ', ' but ', ' so ', ' yet ',
            ' then ', ' because ', ' however ',
            ' although ', ' while ', ' since ',
        ]
        if any(buffer.endswith(e) for e in clause_endings) and len(stripped) > 40:
            return True

        # Safety valve — never buffer more than 120 chars
        # Shorter than before — keeps speech flowing
        if len(stripped) > 120:
            return True

        return False

    # ── Voice switching ────────────────────────────────────────────────────

    def set_voice(self, name: str) -> bool:
        """
        Switch to a different voice by character name.
        Returns True if voice found and switched.
        """
        voice = self.voice_manager.get(name)
        if voice:
            self._active_voice = voice
            self.config.tts_voice = name
            return True
        return False

    def current_voice_name(self) -> str:
        return self._active_voice.name if self._active_voice else "None"

    def available_voices(self):
        return self.voice_manager.all_voices()

    # ── Control ────────────────────────────────────────────────────────────

    def stop(self):
        """Stop all speech immediately."""
        while not self._speak_queue.empty():
            try:
                self._speak_queue.get_nowait()
            except queue.Empty:
                break
        self._token_buffer = ""
        try:
            subprocess.run(["pkill", "-f", "aplay"], capture_output=True)
            subprocess.run(["pkill", "-f", "afplay"], capture_output=True)
        except Exception:
            pass

    def set_enabled(self, enabled: bool):
        self.enabled = enabled
        if enabled and self.available and self._active_voice \
                and not self._worker_thread:
            self._start_worker()

    def shutdown(self):
        self._stop_event.set()
        self._speak_queue.put(None)
