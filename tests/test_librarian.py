"""Two models: the speaker briefs the librarian; the librarian extracts; the speaker answers from facts."""

import unittest
from unittest import mock

from core.app.config import Config
from core.ai.librarian import Librarian, facts_block


from core.ai.llm import LLMEngine


class FakeLLM(LLMEngine):
    """Plays both models: records who was asked what, answers from a script."""

    def __init__(self, brief="SEARCH: water boiling time\nQUESTION: How long should water be boiled?",
                 facts="- Boil water for 1 minute [1]\n- At altitude boil 3 minutes [1]", fail=False):
        super().__init__(Config())
        self.calls = []
        self.brief, self.facts, self.fail = brief, facts, fail

    def complete(self, system_prompt, prompt, model="", **kw):
        self.calls.append((model, system_prompt, prompt))
        if self.fail:
            raise ConnectionError("Ollama isn't running")
        return self.brief if "librarian" in system_prompt.lower() and "requests" in system_prompt else self.facts


class TestLibrarian(unittest.TestCase):
    def test_brief_uses_the_speaker_and_parses_two_lines(self):
        llm = FakeLLM()
        b = Librarian(llm).brief("how long do i boil it", "is river water safe", "Not raw, no.")
        self.assertEqual(b.search, "water boiling time")
        self.assertEqual(b.question, "How long should water be boiled?")
        model, _, prompt = llm.calls[0]
        self.assertEqual(model, llm.config.speaker_model)
        self.assertIn("is river water safe", prompt)          # the last exchange goes with it

    def test_extract_uses_the_librarian_and_keeps_only_fact_lines(self):
        llm = FakeLLM(facts="Sure! Here you go:\n- Boil for 1 minute [1]\nHope that helps")
        f = Librarian(llm).extract("How long?", [("Water Manual", "Boil for 1 minute. " * 50)])
        self.assertTrue(f.found)
        self.assertEqual(f.text, "- Boil for 1 minute [1]")
        model, system, prompt = llm.calls[0]
        self.assertEqual(model, llm.config.librarian_model)
        self.assertIn("never answer from memory", system)
        self.assertLess(len(prompt.split()), 450)               # passages are cut to fit

    def test_not_found(self):
        f = Librarian(FakeLLM(facts="NOT FOUND")).extract("Who is BT?", [("x", "unrelated text")])
        self.assertFalse(f.found)
        self.assertFalse(f.failed)
        self.assertIn("nothing that answers this", facts_block(f))

    def test_unreachable_librarian_is_not_not_found(self):
        f = Librarian(FakeLLM(fail=True)).extract("Q", [("x", "text")])
        self.assertTrue(f.failed)
        b = Librarian(FakeLLM(fail=True)).brief("how do i boil water")
        self.assertEqual(b.question, "how do i boil water")    # falls back to the message itself


class TestPipelineWithTwoModels(unittest.TestCase):
    def setUp(self):
        from core.you.memory import Memory
        from core.library.rag import KnowledgeBase
        from core.answers.pipeline import QueryPipeline
        from core.you.tabs import TabManager
        self.llm = FakeLLM()
        self.pipe = QueryPipeline(Memory(), KnowledgeBase(), self.llm)
        self.tabs = TabManager()

    def prepare(self, q, tab_id):
        tab = self.tabs.get_tab(tab_id)
        return self.pipe.prepare_knowledge(tab, q, self.pipe.route(q, tab_id))

    def test_knowledge_tab_briefs_then_extracts(self):
        out = self.prepare("how do i purify water", "survival")
        models = [m for m, _, _ in self.llm.calls]
        self.assertEqual(models, [self.llm.config.speaker_model, self.llm.config.librarian_model])
        self.assertIn("How long should water be boiled?", self.llm.calls[1][2])   # the brief's question
        self.assertIn("LIBRARY FACTS", out.system_prompt)
        self.assertIn("Boil water for 1 minute", out.system_prompt)
        self.assertNotIn("Retrieved knowledge — use as primary source:\n[", out.system_prompt)

    def test_emergency_skips_the_librarian(self):
        self.prepare("he's not breathing what do i do", "medical")
        self.assertEqual(self.llm.calls, [])

    def test_small_talk_is_one_call(self):
        with mock.patch("core.library.wiki_lookup.find_articles", return_value=[]):
            out = self.prepare("hey how's it going", "prometheus")
        self.assertEqual(self.llm.calls, [])
        self.assertNotIn("LIBRARY FACTS", out.system_prompt)

    def test_chat_lookup_goes_through_the_librarian(self):
        from pathlib import Path
        import tempfile
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        art = Path(d.name) / "Inception_film.txt"
        art.write_text("# Inception (film)\n\nInception is a 2010 film by Christopher Nolan. " * 20)
        with mock.patch("core.library.wiki_lookup.find_articles", return_value=[("Inception (film)", art)]):
            out = self.prepare("have you seen inception", "prometheus")
        self.assertEqual([m for m, _, _ in self.llm.calls], [self.llm.config.librarian_model])
        self.assertIn("LIBRARY FACTS", out.system_prompt)
        self.assertNotIn("Christopher Nolan. Inception", out.system_prompt)     # no raw article text
        self.assertTrue(out.system_prompt.rstrip().split("\n")[-1].startswith("Right now:"))

    def test_off_switch_is_the_old_way(self):
        self.llm.config.two_models = False
        self.prepare("how do i purify water", "survival")
        self.assertEqual(self.llm.calls, [])


if __name__ == "__main__":
    unittest.main()
