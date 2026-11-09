"""Settings survive a restart, and each voice keeps its own name and personality."""

import json
import os
import tempfile
import unittest
from unittest import mock

from core.app import config as cfgmod
from core.app.config import Config


class TestConfig(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "memory", "config.json")
        self.p = mock.patch.object(cfgmod, "CONFIG_PATH", self.path)
        self.p.start()

    def tearDown(self):
        self.p.stop()
        self.tmp.cleanup()

    def test_saved_settings_load_back(self):
        c = Config.load()
        c.store_profile("Data", "Data", "precise android")
        c.use_voice("Data")
        c.save()
        back = Config.load()
        self.assertEqual((back.tts_voice, back.assistant_name, back.assistant_persona),
                         ("Data", "Data", "precise android"))

    def test_each_voice_has_its_own_profile(self):
        c = Config()
        c.store_profile("Data", "Data", "precise android")
        c.store_profile("Vasco", "Vasco", "old sailor")
        c.use_voice("Vasco")
        self.assertEqual(c.assistant_persona, "old sailor")
        c.use_voice("Data")
        self.assertEqual(c.assistant_name, "Data")

    def test_old_single_persona_moves_to_the_chosen_voice(self):
        os.makedirs(os.path.dirname(self.path))
        with open(self.path, "w") as f:
            json.dump({"tts_voice": "Vasco", "assistant_name": "Vasco",
                       "assistant_persona": "old sailor"}, f)
        c = Config.load()
        self.assertEqual(c.voice_profiles["Vasco"]["persona"], "old sailor")

    def test_unreadable_file_gives_defaults(self):
        os.makedirs(os.path.dirname(self.path))
        with open(self.path, "w") as f:
            f.write("{not json")
        self.assertEqual(Config.load().assistant_name, "Prometheus")


if __name__ == "__main__":
    unittest.main()
