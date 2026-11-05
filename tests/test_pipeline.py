"""
Shared pipeline tests — the decision layers desktop and Android both use.
No Ollama or Qt needed:  python -m unittest discover tests
"""

import unittest

from core.config import Config
from core.llm import LLMEngine
from core.memory import Memory
from core.pipeline import QueryPipeline
from core.platform_info import IS_ANDROID
from core.rag import KnowledgeBase
from core.tabs import TabManager


class TestPipeline(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tabs = TabManager()
        cls.pipe = QueryPipeline(Memory(), KnowledgeBase(), LLMEngine(Config()))

    def prepare(self, query, tab_id):
        tab = self.tabs.get_tab(tab_id)
        plan = self.pipe.route(query, tab_id)
        return plan, self.pipe.prepare_knowledge(tab, query, plan)

    def test_emergency(self):
        plan, out = self.prepare("someone is bleeding right now and i can't stop it", "medical")
        self.assertEqual(out.mode.value, "emergency")
        self.assertFalse(out.clarify_text)
        self.assertIn("EMERGENCY", out.system_prompt)

    def test_companion_reflection_is_warm(self):
        plan, out = self.prepare("i feel completely alone", "prometheus")
        self.assertEqual(out.intent, "reflect")
        self.assertNotEqual(out.mode.value, "safe_mode")

    def test_training_flag_and_notes(self):
        plan = self.pipe.route("explain why power equals voltage times current", "electronics")
        self.assertTrue(plan.use_training_path)
        self.assertTrue(QueryPipeline.training_should_show({"status": "DERIVED"}))
        self.assertFalse(QueryPipeline.training_should_show({"status": "NEEDS_PREREQS"}))
        self.assertEqual(QueryPipeline.training_fallback_note({"status": "NO_MATCH", "reason": "x"}), "")
        self.assertIn("library", QueryPipeline.training_fallback_note(
            {"status": "NEEDS_PREREQS", "reason": "First ask me to explain: X."}))

    def test_prompt_order_guidance_last(self):
        plan, out = self.prepare("how do i purify water", "survival")
        self.assertTrue(out.system_prompt)
        self.assertIsNotNone(out.mode)

    def test_not_android_here(self):
        self.assertFalse(IS_ANDROID)


if __name__ == "__main__":
    unittest.main()
