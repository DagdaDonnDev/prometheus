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
        self.assertEqual(out.intent, "chat_low")      # tone read from the message
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

    def test_companion_prompt_is_small(self):
        # The old companion prompt was ~2,600 tokens — the main cause of a 3 s wait
        plan, out = self.prepare("hey, how's it going?", "prometheus")
        self.assertLess(len(out.system_prompt), 1400)
        self.assertNotIn("I hear you\" must", out.system_prompt)
        self.assertEqual(out.images, [])
        self.assertEqual(out.sources, [])

    def test_companion_knows_them_and_stays_small(self):
        # What they've told it plus earlier chat titles, and tone still last
        import copy
        from core.tabs import Tab
        saved = copy.deepcopy(self.pipe.memory.data)
        try:
            u = self.pipe.memory.data["user"]
            u.update(location_estimate="Cork", work="nurse",
                     mentioned_people=["Kate (sister)", "Max (dog)"],
                     likes=["hiking", "Inception (favourite film)"], dislikes=["mornings"])
            tab = Tab(id="prometheus", name="Chat", icon="", domains=[], system_prompt="")
            for title in ("space films", "sourdough", "my new job"):
                tab.add_message("user", title)
                tab.new_chat()
            plan = self.pipe.route("hey, how's it going?", "prometheus")
            out = self.pipe.prepare_knowledge(tab, "hey, how's it going?", plan)
            p = out.system_prompt
            for bit in ("Cork", "Kate (sister)", "hiking", "sourdough"):
                self.assertIn(bit, p)
            self.assertTrue(p.rstrip().split("\n")[-1].startswith("Right now:"))
            self.assertLess(len(p), 2000)
        finally:
            self.pipe.memory.data = saved

    def test_knowledge_prompt_trimmed(self):
        plan, out = self.prepare("how do i purify water", "survival")
        self.assertLess(len(out.system_prompt), 8000)

    def test_everyday_help_is_not_emergency(self):
        for q in ("can you help me plan my week", "help me think something through"):
            self.assertNotEqual(self.pipe.route(q, "survival").intent.value, "emergency", q)
        self.assertEqual(self.pipe.route("help he's not breathing", "medical").intent.value, "emergency")

    def test_crisis_any_tab(self):
        for tab in ("prometheus", "survival", "electronics"):
            plan, out = self.prepare("i want to kill myself", tab)
            self.assertTrue(plan.is_crisis, tab)
            self.assertEqual(out.mode.value, "emergency")
            self.assertIn("safe right now", out.system_prompt)

    def test_assistant_name(self):
        self.pipe.config.assistant_name = "Ember"
        self.pipe.config.assistant_persona = "dry humour"
        try:
            plan, out = self.prepare("hey", "prometheus")
            self.assertTrue(out.system_prompt.startswith("You are Ember."))
            self.assertIn("dry humour", out.system_prompt)
            plan, out = self.prepare("how do i purify water", "survival")
            self.assertIn("You are Ember", out.system_prompt)
        finally:
            self.pipe.config.assistant_name = "Prometheus"
            self.pipe.config.assistant_persona = ""

    def test_missing_thing_is_admitted(self):
        # No article for it → the model is told to say so (patched so a real
        # local Wikipedia that does have "The Juror" can't change the result)
        from unittest import mock
        with mock.patch("core.wiki_lookup.find_articles", return_value=[]):
            plan, out = self.prepare("have you seen the juror?", "prometheus")
        self.assertIn('NOT IN YOUR LIBRARY: you have nothing about "the juror"', out.system_prompt)
        plan, out = self.prepare("tell me about your day", "prometheus")
        self.assertNotIn("NOT IN YOUR LIBRARY", out.system_prompt)

    def test_default_model(self):
        from core.config import Config
        self.assertEqual(Config().companion_model, "hf.co/LiquidAI/LFM2.5-1.2B-Instruct-GGUF:latest")

    def test_not_android_here(self):
        self.assertFalse(IS_ANDROID)


if __name__ == "__main__":
    unittest.main()
