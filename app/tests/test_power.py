"""Low-power mode: picked from the hardware, applied, and kept out of the saved settings."""

import json
import os
import tempfile
import unittest
from unittest import mock

from core.app import hardware, config as cfgmod
from core.app.config import Config
from core.app.hardware import Hardware, recommend


class TestRecommend(unittest.TestCase):
    def test_choices(self):
        pc = Hardware(ram_gb=16, cores=8, arch="AMD64", gpu_name="NVIDIA GeForce RTX 3060", gpu_vram_gb=12)
        self.assertEqual(recommend(pc, True)[0], "full")
        self.assertEqual(recommend(pc, False)[0], "low")          # Ollama isn't using the card
        pi = Hardware(ram_gb=15.6, cores=8, arch="aarch64")
        self.assertEqual(recommend(pi, None), ("low", "there's no graphics card and the processor is an ARM chip"))
        self.assertEqual(recommend(Hardware(ram_gb=4, cores=8, arch="x86_64"), True)[0], "low")
        self.assertEqual(recommend(Hardware(ram_gb=32, cores=12, arch="x86_64"), None)[0], "full")

    def test_summary_reads_plainly(self):
        self.assertEqual(Hardware(16, 8, "aarch64").summary(), "8 cores · 16 GB memory · ARM processor · no graphics card found")

    def test_detect_runs_here(self):
        hw = hardware.detect()
        self.assertGreater(hw.cores, 0)


class TestLowPowerEffects(unittest.TestCase):
    def test_runtime_flag_is_not_saved(self):
        with tempfile.TemporaryDirectory() as t, \
                mock.patch.object(cfgmod, "CONFIG_PATH", os.path.join(t, "config.json")):
            c = Config()
            c.low_power_active = True
            c.power_last = "low"
            c.save()
            data = json.load(open(os.path.join(t, "config.json")))
            self.assertNotIn("low_power_active", data)
            back = Config.load()
            self.assertTrue(back.low_power_active)               # last time's choice until re-checked
            back.power_mode = "full"
            back.__post_init__()
            self.assertFalse(back.low_power_active)

    def test_low_power_skips_the_request_step_and_trims(self):
        from tests.test_librarian import FakeLLM
        from core.you.memory import Memory
        from core.library.rag import KnowledgeBase
        from core.answers.pipeline import QueryPipeline
        from core.you.tabs import TabManager
        llm = FakeLLM()
        llm.config.low_power_active = True
        pipe = QueryPipeline(Memory(), KnowledgeBase(), llm)
        tab = TabManager().get_tab("survival")
        pipe.prepare_knowledge(tab, "how do i purify water", pipe.route("how do i purify water", "survival"))
        models = [m for m, _, _ in llm.calls]
        self.assertEqual(models, [llm.config.librarian_model])     # no speaker request step
        self.assertLess(len(llm.calls[0][2].split()), 330)         # librarian reads less


if __name__ == "__main__":
    unittest.main()
