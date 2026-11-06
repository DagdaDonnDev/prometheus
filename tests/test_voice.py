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


class TestStopSpeaking(unittest.TestCase):
    def test_hush_mutes_the_rest_of_this_reply_only(self):
        t = _engine()
        t.begin_reply()
        t.on_token("First sentence here. ")
        self.assertTrue(t.is_speaking())
        t.hush(reply_still_coming=True)
        self.assertFalse(t.is_speaking())
        t.on_token("More of the same reply. ")       # still streaming — stays quiet
        t.flush()
        self.assertTrue(t._speak_queue.empty())
        t.begin_reply()                              # next reply speaks again
        t.on_token("Next reply. ")
        self.assertTrue(t.is_speaking())

    def test_esc_after_hush_does_not_leave_it_muted(self):
        t = _engine()
        t.hush(reply_still_coming=True)
        t.stop()                                     # Esc / ⏹
        t.on_token("A new sentence. ")
        self.assertTrue(t.is_speaking())


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


# ── Voice conversation: knowing when they've stopped, and interrupting ─────

import numpy as np
import sys
import threading
import time
from core import stt as stt_mod


def _blocks(level, seconds, seed=0):
    rng = np.random.default_rng(seed)
    n = int(seconds * stt_mod.SAMPLE_RATE / stt_mod.BLOCK)
    return [(rng.standard_normal(stt_mod.BLOCK) * level).astype(np.int16) for _ in range(n)]


class TestSpeechDetector(unittest.TestCase):
    def run_through(self, d, blocks):
        states = [d.feed(b) for b in blocks]
        return states

    def test_talk_then_pause_is_done(self):
        d = stt_mod.SpeechDetector()
        audio = _blocks(80, 0.6) + _blocks(3000, 1.0, 1) + _blocks(80, 1.2, 2)
        states = self.run_through(d, audio)
        self.assertIn("speaking", states)
        self.assertEqual(states[-1], "done")
        # it ends about 0.9 s into the pause, not before
        first_done = states.index("done")
        self.assertGreater(first_done, len(_blocks(1, 1.6)) + 25)
        # speech starts ~0.6 s in; start_block keeps a little lead-in before it
        self.assertLess(d.start_block, 20)
        self.assertGreater(d.start_block, 5)

    def test_a_click_is_not_speech(self):
        d = stt_mod.SpeechDetector()
        states = self.run_through(d, _blocks(80, 0.6) + _blocks(4000, 0.06, 1) + _blocks(80, 2, 2))
        self.assertNotIn("done", states)
        self.assertFalse(d.started)

    def test_echo_of_the_voice_doesnt_interrupt_but_talking_over_it_does(self):
        d = stt_mod.SpeechDetector()
        d.strict = True
        echo = _blocks(1200, 2.0)                       # the speakers, heard by the mic
        self.run_through(d, echo)
        self.assertFalse(d.started)
        self.run_through(d, _blocks(9000, 0.6, 3))      # they talk over it, clearly louder
        self.assertTrue(d.started)


class _FakeStream:
    """Stands in for sounddevice.InputStream: plays blocks into the callback."""
    feed = []

    def __init__(self, samplerate, channels, dtype, blocksize, callback, finished_callback):
        self.cb, self.fin, self._stop = callback, finished_callback, False

    def start(self):
        def run():
            for b in self.feed:
                if self._stop:
                    break
                try:
                    self.cb(b.reshape(-1, 1), len(b), None, None)
                except _FakeSD.CallbackStop:
                    break
                time.sleep(0.003)             # 10× real time, like a mic that keeps going
            self.fin()
        threading.Thread(target=run, daemon=True).start()

    def stop(self):
        self._stop = True

    def close(self):
        pass


class _FakeSD:
    class CallbackStop(Exception):
        pass
    InputStream = _FakeStream


class TestListening(unittest.TestCase):
    def setUp(self):
        self.sd = mock.patch.dict(sys.modules, {"sounddevice": _FakeSD})
        self.sd.start()
        self.stt = STTEngine(Config())
        self.stt.available, self.stt.model = True, object()
        self.got = []
        self.stt.transcribe_samples = lambda blocks: (self.got.append(blocks), "hello there")[1]

    def tearDown(self):
        self.sd.stop()

    def wait_for(self, cond, secs=3):
        end = time.time() + secs
        while time.time() < end and not cond():
            time.sleep(0.02)

    def test_voice_conversation_sends_only_their_words(self):
        quiet, speech = _blocks(80, 1.5), _blocks(3000, 1.0, 1)
        _FakeStream.feed = quiet + speech + _blocks(80, 1.5, 2)
        heard = []
        self.assertTrue(self.stt.listen(heard.append, auto_stop=True))
        self.wait_for(lambda: heard)
        self.assertEqual(heard, ["hello there"])
        self.assertFalse(self.stt.listening)
        sent = self.got[0]
        # the 1.5 s of room before they spoke isn't sent, just a short lead-in
        self.assertLess(len(sent), len(speech) + 45)
        self.assertGreaterEqual(len(sent), len(speech))

    def test_hold_to_talk_sends_on_release(self):
        _FakeStream.feed = _blocks(3000, 30)               # long enough to still be going
        heard = []
        self.stt.listen(heard.append, auto_stop=False)
        time.sleep(0.1)
        self.stt.finish_listening()
        self.wait_for(lambda: heard)
        self.assertEqual(heard, ["hello there"])

    def test_cancel_sends_nothing(self):
        _FakeStream.feed = _blocks(3000, 30)
        heard = []
        self.stt.listen(heard.append, auto_stop=False)
        time.sleep(0.1)
        self.stt.cancel_listening()
        time.sleep(0.3)
        self.assertEqual(heard, [])
        self.assertFalse(self.stt.listening)
