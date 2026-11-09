"""
Speech-to-Text engine using faster-whisper.
Fully offline. No internet required.
"""

import threading
import queue
import tempfile
import os
import wave
from typing import Optional, Callable


SAMPLE_RATE = 16000
BLOCK = 480                     # 30 ms
KEEP_WAITING = 34               # blocks kept (~1 s) while waiting for speech


class SpeechDetector:
    """
    Decides when someone has finished talking (voice conversation mode).

    Step 1: the first ~0.3 s sets the room's noise level
    Step 2: speech = blocks clearly louder than that (3× the noise, at least
            a fixed floor so a silent mic doesn't count every click)
    Step 3: "done" after 0.9 s of quiet following at least 0.25 s of speech,
            or after 30 s of talking
    feed() returns "waiting", "speaking" or "done".
    """

    def __init__(self, rate: int = SAMPLE_RATE, end_silence: float = 0.9,
                 min_speech: float = 0.25, max_speech: float = 30.0, floor: float = 350.0):
        self.rate, self.floor = rate, floor
        self.end_silence, self.min_speech, self.max_speech = end_silence, min_speech, max_speech
        self.noise = None
        self._calib, self._calib_n = 0.0, 0
        self.started = False
        self.speech = self.quiet = 0.0
        # While the voice is talking the mic also hears the speakers, so
        # interrupting needs louder, longer speech (set by the window)
        self.strict = False
        self._i = 0                 # blocks fed
        self._run_start = 0         # first block of the current loud stretch
        self.start_block = 0        # where their speech began (minus a little lead-in)

    def feed(self, block) -> str:
        import numpy as np
        secs = len(block) / self.rate
        self._i += 1
        level = float(np.sqrt(np.mean(np.square(block.astype(np.float32))))) if len(block) else 0.0
        # Step 1
        if self.noise is None:
            self._calib += level
            self._calib_n += 1
            if self._calib_n * secs >= 0.3:
                self.noise = self._calib / self._calib_n
            return "waiting"
        # Step 2
        factor, needed = (5.0, 0.4) if self.strict else (3.0, self.min_speech)
        loud = level > max(self.floor * (2 if self.strict else 1), self.noise * factor)
        if not loud and not self.started:
            self.noise = 0.95 * self.noise + 0.05 * level      # follow the room slowly
        # Step 3
        if loud:
            if self.speech == 0.0:
                self._run_start = self._i - 1
            self.speech += secs
            self.quiet = 0.0
            if self.speech >= needed and not self.started:
                self.started = True
                self.start_block = max(0, self._run_start - int(0.3 * self.rate / max(1, len(block))))
        elif self.started:
            self.quiet += secs
        else:
            self.quiet += secs                       # a cough or a click isn't speech:
            if self.quiet >= 0.3:                    # forget it after 0.3 s of quiet
                self.speech = self.quiet = 0.0
        if self.started and (self.quiet >= self.end_silence or self.speech >= self.max_speech):
            return "done"
        return "speaking" if self.started else "waiting"


def _close(stream):
    try:
        stream.close()
    except Exception:
        pass


class STTEngine:
    def __init__(self, config):
        self.config = config
        self.enabled = config.stt_enabled
        self.model = None
        self.available = False
        self.error = ""            # why it isn't available, in plain words
        self.listening = False         # the microphone is open
        self.transcribing = False      # working out what was said

    def initialize(self, status_callback: Optional[Callable] = None):
        """
        Load the Whisper model. Called after the window is shown.

        Step 1: faster-whisper must be installed (python tools/setup_voice.py)
        Step 2: use models/whisper/<size> if tools/setup_voice.py downloaded it
                (works offline); otherwise let faster-whisper fetch it into
                models/whisper_cache the first time
        Step 3: any failure → voice input off, with the reason in self.error
        """
        say = status_callback or (lambda _m: None)
        try:
            from faster_whisper import WhisperModel
        except Exception as e:
            self.available = False
            self.error = ("faster-whisper not installed — run: python tools/setup_voice.py"
                          if isinstance(e, ImportError) else f"faster-whisper won't load: {e}")
            say(self.error)
            return

        from core.app.paths import PROJECT_DIR
        size = self.config.stt_model or "tiny"
        local = PROJECT_DIR / "models" / "whisper" / size
        say("Loading speech recognition model...")
        try:
            self.model = WhisperModel(
                str(local) if (local / "model.bin").is_file() else size,
                device="cpu",
                compute_type="int8",
                download_root=str(PROJECT_DIR / "models" / "whisper_cache"),
            )
            self.available = True
            self.error = ""
            say("Speech recognition ready.")
        except Exception as e:
            self.model = None
            self.available = False
            self.error = f"Whisper model '{size}' couldn't load ({e}) — run: python tools/setup_voice.py"
            say(self.error)

    def transcribe_file(self, audio_path: str) -> str:
        """Transcribe an audio file to text."""
        if not self.available or not self.model:
            return ""

        try:
            segments, _ = self.model.transcribe(
                audio_path,
                beam_size=5,
                language="en"
            )
            return " ".join(s.text for s in segments).strip()
        except Exception:
            return ""

    # ── Listening ───────────────────────────────────────────────────────────

    def listen(self, on_done: Callable[[str], None], auto_stop: bool) -> bool:
        """
        Start the microphone. Returns False if it can't.

        auto_stop=True  (voice conversation): ends by itself once you've spoken
                        and then gone quiet (SpeechDetector)
        auto_stop=False (holding the send button): ends at finish_listening()
        Either way the words are worked out on a background thread and passed
        to on_done(text) — "" if nothing was understood. cancel_listening()
        ends it without calling on_done.
        """
        if not self.available or self.listening:
            return False
        try:
            import sounddevice as sd
        except Exception as e:
            self.error = f"Microphone library missing ({e}) — run: python tools/setup_voice.py"
            return False
        self._blocks = []
        self._on_done = on_done
        self._cancelled = False
        self._detector = SpeechDetector() if auto_stop else None

        self._dropped = 0

        def callback(indata, frames, time_info, status):
            block = indata[:, 0].copy()
            self._blocks.append(block)
            d = self._detector
            if d is not None:
                if d.feed(block) == "done":
                    raise sd.CallbackStop
                # Waiting for them to speak: keep only the last second, not every
                # minute of a quiet room (or of the voice talking)
                if not d.started and len(self._blocks) > KEEP_WAITING:
                    del self._blocks[0]
                    self._dropped += 1

        self.listening = True           # before start(): it can finish at once
        try:
            self._stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                                          blocksize=BLOCK, callback=callback,
                                          finished_callback=self._finished)
            self._stream.start()
        except Exception as e:
            self.error = f"Couldn't open the microphone: {e}"
            self._stream = None
            self.listening = False
            return False
        return True

    def finish_listening(self):
        """Push-to-talk released: stop and work out what was said."""
        stream = getattr(self, "_stream", None)
        if stream is not None:
            try:
                stream.stop()       # → _finished
            except Exception:
                self._finished()

    def cancel_listening(self):
        """Stop without sending anything."""
        self._cancelled = True
        self.finish_listening()

    def set_strict(self, strict: bool):
        """The voice is talking: only clearly louder speech counts (interrupting)."""
        d = getattr(self, "_detector", None)
        if d is not None:
            d.strict = strict

    def heard_speech(self) -> bool:
        """True once the voice-conversation listener has heard you start talking."""
        d = getattr(self, "_detector", None)
        return bool(d and d.started)

    def _finished(self):
        """The stream has stopped: transcribe on a background thread."""
        if not self.listening:
            return
        self.listening = False
        stream, self._stream = getattr(self, "_stream", None), None
        if stream is not None:
            threading.Thread(target=lambda: _close(stream), daemon=True).start()
        if self._cancelled:
            return
        blocks, on_done = self._blocks, self._on_done
        d = self._detector
        if d is not None and d.started:
            # drop what came before they spoke (room noise, the voice's echo)
            blocks = blocks[max(0, d.start_block - self._dropped):]
        self.transcribing = True

        def work():
            try:
                text = self.transcribe_samples(blocks)
            except Exception:
                text = ""
            finally:
                self.transcribing = False
            on_done(text)
        threading.Thread(target=work, daemon=True).start()

    def transcribe_samples(self, blocks) -> str:
        """int16 blocks at 16 kHz → text ('' for silence or under half a second)."""
        import numpy as np
        if not blocks or not self.model:
            return ""
        audio = np.concatenate(blocks).astype(np.float32) / 32768.0
        if len(audio) < SAMPLE_RATE // 2:
            return ""
        segments, _ = self.model.transcribe(audio, beam_size=5, language="en",
                                            vad_filter=True)
        return " ".join(s.text for s in segments).strip()

    def set_enabled(self, enabled: bool):
        self.enabled = enabled
