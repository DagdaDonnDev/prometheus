"""Voice: where speech is cut into pieces, what's spoken, and Whisper failing gracefully."""

import builtins
import unittest
from unittest import mock

from core.config import Config
from core.tts import TTSEngine, clean_for_speech
from core.stt import STTEngine


def _engine():
    c = Config()
    c.voice_enabled = False          # no Piper, no threads — just the splitting logic
    t = TTSEngine(c)
    t.available, t.enabled, t._active_voice = True, True, object()
    return t


def _pieces(text):
    t = _engine()
    for word in text.split(" "):
        t.on_token(word + " ")
    out = []
    while not t._speak_queue.empty():
        out.append(t._speak_queue.get()[1])
    t.flush()
    while not t._speak_queue.empty():
        out.append(t._speak_queue.get()[1])
    return out


class TestPieces(unittest.TestCase):
    def test_whole_sentences_not_clauses(self):
        pieces = _pieces("Boil the water for a minute and then let it cool down slowly. "
                         "Store it in a clean container but keep it covered. Done.")
        self.assertEqual(pieces[-2:], ["Store it in a clean container but keep it covered.", "Done."])
        self.assertFalse(any(p.endswith(" and") or p.endswith(" but") for p in pieces))

    def test_first_piece_can_end_at_a_comma(self):
        pieces = _pieces("Right, if the water looks cloudy at all, filter it through cloth first. "
                         "Then boil it, and let it cool, before drinking.")
        self.assertEqual(pieces[0], "Right, if the water looks cloudy at all,")
        self.assertEqual(pieces[-1], "Then boil it, and let it cool, before drinking.")

    def test_numbers_are_not_sentence_ends(self):
        self.assertEqual(_pieces("It needs about 3.5 litres a day."), ["It needs about 3.5 litres a day."])

    def test_clean_for_speech(self):
        self.assertEqual(clean_for_speech("**Boil** it — then `cool` it.\n- step one\n# Title"),
                         "Boil it, then cool it. step one Title")
        self.assertEqual(clean_for_speech("See [the guide](http://x.y) now"), "See the guide now")


class TestWhisper(unittest.TestCase):
    def test_not_installed_is_reported(self):
        real = builtins.__import__
        def no_whisper(name, *a, **k):
            if name.startswith("faster_whisper"):
                raise ImportError("No module named 'faster_whisper'")
            return real(name, *a, **k)
        stt = STTEngine(Config())
        notes = []
        with mock.patch("builtins.__import__", no_whisper):
            stt.initialize(notes.append)
        self.assertFalse(stt.available)
        self.assertIn("setup_voice.py", stt.error)
        self.assertEqual(notes, [stt.error])

    def test_model_failure_is_reported_not_raised(self):
        fake = mock.MagicMock()
        fake.WhisperModel.side_effect = RuntimeError("no internet")
        with mock.patch.dict("sys.modules", {"faster_whisper": fake}):
            stt = STTEngine(Config())
            stt.initialize()
        self.assertFalse(stt.available)
        self.assertIn("no internet", stt.error)


if __name__ == "__main__":
    unittest.main()
