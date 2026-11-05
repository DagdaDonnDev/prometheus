"""
TTS Engine
==========
Piper-based text-to-speech with token streaming.
Uses VoiceManager to load voices by character name.
Fully offline.
"""

import os
import re
import sys
import time
import wave
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
        # Bumped by stop(): queued or playing speech from before is dropped
        self._generation   = 0
        self._player: Optional[subprocess.Popen] = None

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
                item = self._speak_queue.get(timeout=0.5)
                if item is None:
                    break
                gen, text = item
                if gen == self._generation:      # skip speech queued before a stop
                    self._speak(text, gen)
                self._speak_queue.task_done()
            except queue.Empty:
                continue

    def _speak(self, text: str, gen: int):
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

            # Stopped while Piper was working? Don't play the stale sentence
            if success and os.path.exists(tmp) and gen == self._generation:
                self._play(tmp, gen)

        except Exception:
            pass
        finally:
            if tmp:
                try:
                    os.unlink(tmp)
                except Exception:
                    pass

    def _play(self, path: str, gen: int):
        """Play a wav file, returning early if stop() is called."""
        if sys.platform == "win32":
            self._play_windows(path, gen)
            return

        # Linux / macOS: first player that exists
        for player in ["aplay", "paplay", "afplay", "mpg123"]:
            try:
                self._player = subprocess.Popen(
                    [player, path],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            except FileNotFoundError:
                continue
            except Exception:
                return
            try:
                self._player.wait(timeout=60)
            except subprocess.TimeoutExpired:
                self._player.kill()
            finally:
                self._player = None
            return

    def _play_windows(self, path: str, gen: int):
        """Windows has no aplay — use the built-in winsound, polled so stop() works."""
        import winsound
        try:
            with wave.open(path, "rb") as w:
                seconds = w.getnframes() / float(w.getframerate() or 1)
        except Exception:
            seconds = 10.0
        winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        end = time.time() + seconds + 0.1
        while time.time() < end:
            if gen != self._generation:
                winsound.PlaySound(None, 0)      # stop the current sound
                return
            time.sleep(0.05)

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
                self._speak_queue.put((self._generation, text))

    def flush(self):
        """Speak any remaining buffered text."""
        if self._token_buffer.strip():
            self._speak_queue.put((self._generation, self._token_buffer.strip()))
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
        # Drop anything queued or being synthesised, and cut the current sound.
        # Only Prometheus's own player is stopped (pkill used to stop every
        # aplay on the machine).
        self._generation += 1
        player = self._player
        if player and player.poll() is None:
            try:
                player.terminate()
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
