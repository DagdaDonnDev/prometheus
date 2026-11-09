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
import json
import subprocess
from pathlib import Path
from typing import Optional

from core.voice.voice_manager import VoiceManager, PiperVoice


class _PiperProcess:
    """
    One Piper that stays running, so the voice is loaded once — not for every
    sentence (loading it each time was the pause before every piece).
    Sentences go in as JSON lines; Piper writes each to the wav file named
    in the line and prints the path when it's done.
    """

    def __init__(self, voice_manager: VoiceManager):
        self.vm = voice_manager
        self.proc: Optional[subprocess.Popen] = None
        self.key = None
        self.lock = threading.Lock()

    def _start(self, voice: PiperVoice, rate: float):
        self.close()
        piper = self.vm.find_piper()
        if not piper:
            return
        cmd = [piper, "--model", str(Path(voice.model).resolve()), "--json-input", "--quiet",
               "--length_scale", f"{1.0 / (rate or 1.0):.2f}",
               "--sentence_silence", "0.12"]
        if voice.config.exists():
            cmd += ["--config", str(Path(voice.config).resolve())]
        self.proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", bufsize=1,
            cwd=str(Path(piper).parent),          # Piper finds espeak-ng-data next to itself
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self.key = (voice.model, rate)

    def synth(self, text: str, voice: PiperVoice, rate: float, out_path: str) -> bool:
        """Text → wav file. Restarts Piper if the voice or speed changed, or it died."""
        with self.lock:
            for attempt in (1, 2):
                if self.proc is None or self.proc.poll() is not None or self.key != (voice.model, rate):
                    self._start(voice, rate)
                if self.proc is None:
                    return False
                try:
                    self.proc.stdin.write(json.dumps({"text": text, "output_file": out_path}) + "\n")
                    self.proc.stdin.flush()
                    done = self.proc.stdout.readline().strip()
                except (OSError, ValueError):
                    done = ""
                if done and os.path.exists(out_path):
                    return True
                self.close()                      # broken — one fresh try
            return False

    def close(self):
        if self.proc is not None:
            try:
                self.proc.stdin.close()
            except Exception:
                pass
            try:
                self.proc.terminate()
            except Exception:
                pass
        self.proc = None
        self.key = None


def clean_for_speech(text: str) -> str:
    """Markdown and symbols the voice would read out or stumble on."""
    t = re.sub(r"```.*?```", " ", text, flags=re.S)
    t = re.sub(r"`([^`]*)`", r"\1", t)
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)        # [link](url) → link
    t = re.sub(r"(^|\s)[#>*-]+\s+", r"\1", t)               # headings, quotes, bullets
    t = re.sub(r"[*_~#|]+", "", t)
    t = re.sub(r"\s*(—|–)\s*", ", ", t)                      # dashes → a short pause
    return " ".join(t.split())


class TTSEngine:
    """
    Speaks replies while they stream in.

    Step 1: tokens are buffered into whole sentences (the first piece of a
            reply may end at a comma, so speech starts sooner)
    Step 2: a synth thread turns each piece into a wav with one long-running
            Piper (_PiperProcess)
    Step 3: a player thread plays them in order — so the next sentence is
            being made while the current one plays, with no gap between
    stop() bumps a generation number: anything older is dropped at any step.
    """

    def __init__(self, config):
        self.config        = config
        self.enabled       = config.voice_enabled
        self.voice_manager = VoiceManager()

        # Resolve active voice from config (character name)
        self._active_voice: Optional[PiperVoice] = self._resolve_voice(
            config.tts_voice
        )

        self._speak_queue: queue.Queue = queue.Queue()     # (gen, text)
        self._play_queue: queue.Queue = queue.Queue()      # (gen, wav path)
        self._stop_event   = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None
        self._player_thread: Optional[threading.Thread] = None
        self._token_buffer = ""
        self._pieces_this_reply = 0
        # Bumped by stop(): queued or playing speech from before is dropped
        self._generation   = 0
        self._player: Optional[subprocess.Popen] = None
        self._piper = _PiperProcess(self.voice_manager)
        self._busy = 0          # pieces being made or played right now
        self._busy_lock = threading.Lock()
        self._muted = False     # "Stop speaking" pressed: silent until the next reply

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

    # ── Worker threads ─────────────────────────────────────────────────────

    def _start_worker(self):
        self._stop_event.clear()
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()
        self._player_thread = threading.Thread(target=self._player_loop, daemon=True)
        self._player_thread.start()
        # Load the voice now, so the first reply doesn't wait for it
        self._speak_queue.put((self._generation, None))

    def _worker_loop(self):
        """Step 2: text → wav, as fast as Piper can, ahead of playback."""
        while not self._stop_event.is_set():
            try:
                item = self._speak_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if item is None:
                break
            gen, text = item
            if text is None:                     # warm-up: start Piper, say nothing
                self._warm_up()
                continue
            if gen == self._generation:          # skip speech queued before a stop
                self._count(+1)
                try:
                    path = self._synth(text)
                    if path and gen == self._generation:
                        self._play_queue.put((gen, path))
                    elif path:
                        _remove(path)
                finally:
                    self._count(-1)

    def _player_loop(self):
        """Step 3: play the wavs in order."""
        while not self._stop_event.is_set():
            try:
                item = self._play_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if item is None:
                break
            gen, path = item
            self._count(+1)
            try:
                if gen == self._generation:
                    self._play(path, gen)
            except Exception:
                pass
            finally:
                self._count(-1)
                _remove(path)

    def _count(self, delta: int):
        with self._busy_lock:
            self._busy += delta

    def _warm_up(self):
        path = self._synth("Ready.")
        if path:
            _remove(path)

    def _synth(self, text: str) -> Optional[str]:
        text = clean_for_speech(text)
        if not text or not self._active_voice:
            return None
        fd, path = tempfile.mkstemp(suffix=".wav", prefix="prometheus_tts_")
        os.close(fd)
        try:
            ok = self._piper.synth(text, self._active_voice, self.config.tts_rate, path)
        except Exception:
            ok = False
        if ok and os.path.getsize(path) > 44:
            return path
        _remove(path)
        return None

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
        end = time.time() + seconds
        while time.time() < end:
            if gen != self._generation:
                winsound.PlaySound(None, 0)      # stop the current sound
                return
            time.sleep(0.02)

    # ── Token streaming interface ──────────────────────────────────────────

    def on_token(self, token: str):
        """Called for each token from LLM stream. Buffers until natural boundary."""
        if not self.available or not self.enabled or not self._active_voice or self._muted:
            return

        self._token_buffer += token

        if self._should_speak(self._token_buffer):
            text = self._token_buffer.strip()
            self._token_buffer = ""
            if text:
                self._pieces_this_reply += 1
                self._speak_queue.put((self._generation, text))

    def flush(self):
        """Speak any remaining buffered text (end of a reply)."""
        if self._muted:                         # this reply was hushed; the next one speaks
            self._muted = False
            self._token_buffer = ""
            self._pieces_this_reply = 0
            return
        if self._token_buffer.strip():
            self._speak_queue.put((self._generation, self._token_buffer.strip()))
        self._token_buffer = ""
        self._pieces_this_reply = 0

    def _should_speak(self, buffer: str) -> bool:
        """
        Where to cut the stream into pieces for Piper.

        Whole sentences sound natural — Piper says each piece as a complete
        utterance, so cutting at "and"/commas made odd pauses mid-thought.
          - a sentence end (. ! ? followed by a space) → speak
          - the FIRST piece of a reply may end at a comma after ~25 characters,
            so the voice starts quickly
          - a very long sentence (220+ characters) is cut at a comma or space
        """
        stripped = buffer.strip()
        if not stripped:
            return False
        # "3." in "3.5" or "e.g." mid-sentence: wait for the space after it
        if re.search(r'[.!?]["\')\]]?\s+$', buffer) and len(stripped) > 3:
            return True
        if re.search(r'\n\s*$', buffer) and len(stripped) > 3:   # end of a line/bullet
            return True
        if self._pieces_this_reply == 0 and re.search(r'[,;:]\s+$', buffer) and len(stripped) > 25:
            return True
        if len(stripped) > 220 and re.search(r'[,;:]?\s+$', buffer):
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

    def is_speaking(self) -> bool:
        """True while anything is queued, being made, or playing (drives the stop button)."""
        queued = [item for item in list(self._speak_queue.queue) if item and item[1] is not None]
        return bool(queued) or not self._play_queue.empty() or self._busy > 0

    def stop(self):
        """Stop all speech immediately."""
        while not self._speak_queue.empty():
            try:
                self._speak_queue.get_nowait()
            except queue.Empty:
                break
        while not self._play_queue.empty():
            try:
                _remove(self._play_queue.get_nowait()[1])
            except (queue.Empty, TypeError):
                break
        self._token_buffer = ""
        self._pieces_this_reply = 0
        self._muted = False
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

    def begin_reply(self):
        """A new reply is starting — speak it, even if the last one was hushed."""
        self._muted = False
        self._token_buffer = ""
        self._pieces_this_reply = 0

    def hush(self, reply_still_coming: bool):
        """Stop speaking button: cut the voice, and stay quiet for the rest of this reply."""
        self.stop()
        self._muted = reply_still_coming

    def set_enabled(self, enabled: bool):
        self.enabled = enabled
        if enabled and self.available and self._active_voice \
                and not self._worker_thread:
            self._start_worker()

    def shutdown(self):
        self._stop_event.set()
        self._speak_queue.put(None)
        self._play_queue.put(None)
        self._piper.close()


def _remove(path: str):
    try:
        os.unlink(path)
    except OSError:
        pass
