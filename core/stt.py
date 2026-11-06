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


class STTEngine:
    def __init__(self, config):
        self.config = config
        self.enabled = config.stt_enabled
        self.model = None
        self.available = False
        self.error = ""            # why it isn't available, in plain words
        self._recording = False
        self._audio_data = []

    def initialize(self, status_callback: Optional[Callable] = None):
        """
        Load the Whisper model. Called after the window is shown.

        Step 1: faster-whisper must be installed (python setup_voice.py)
        Step 2: use models/whisper/<size> if setup_voice.py downloaded it
                (works offline); otherwise let faster-whisper fetch it into
                models/whisper_cache the first time
        Step 3: any failure → voice input off, with the reason in self.error
        """
        say = status_callback or (lambda _m: None)
        try:
            from faster_whisper import WhisperModel
        except Exception as e:
            self.available = False
            self.error = ("faster-whisper not installed — run: python setup_voice.py"
                          if isinstance(e, ImportError) else f"faster-whisper won't load: {e}")
            say(self.error)
            return

        from core.paths import PROJECT_DIR
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
            self.error = f"Whisper model '{size}' couldn't load ({e}) — run: python setup_voice.py"
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

    def start_recording(self) -> bool:
        """Start recording from microphone."""
        try:
            import sounddevice as sd
            self._audio_data = []
            self._recording = True

            self._stream = sd.InputStream(
                samplerate=16000,
                channels=1,
                dtype='int16',
                callback=self._audio_callback
            )
            self._stream.start()
            return True

        except ImportError:
            return False
        except Exception:
            return False

    def _audio_callback(self, indata, frames, time, status):
        if self._recording:
            self._audio_data.extend(indata.flatten().tolist())

    def stop_recording(self) -> Optional[str]:
        """Stop recording and return transcribed text."""
        if not hasattr(self, '_stream'):
            return None

        self._recording = False

        try:
            self._stream.stop()
            self._stream.close()
        except Exception:
            pass

        if not self._audio_data:
            return None

        # Save to temp wav file
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path = tmp.name

            with wave.open(tmp_path, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)  # 16-bit
                wf.setframerate(16000)
                import struct
                data = struct.pack(f'{len(self._audio_data)}h', *self._audio_data)
                wf.writeframes(data)

            text = self.transcribe_file(tmp_path)

            try:
                os.unlink(tmp_path)
            except Exception:
                pass

            return text if text else None

        except Exception:
            return None

    def set_enabled(self, enabled: bool):
        self.enabled = enabled
