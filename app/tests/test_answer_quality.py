"""Owner's report (2026-11-09): always low confidence, and extra/redundant suggestions in Build."""

import unittest

from core.answers.confidence import ConfidenceScorer
from core.answers.decision_gate import ResponseMode
from core.answers.intent_router import IntentRouter
from core.ai.llm_bounds import build_bounds
from core.library.rag import KnowledgeBase

BOOK = ("To make a box waterproof the joints must be close fitting and set in thick paint "
        "before they are nailed. Two coats of boiled linseed oil, 24 hours apart, protect the wood.")


class TestConfidence(unittest.TestCase):
    def test_books_are_graded_by_their_folder(self):
        s = ConfidenceScorer()
        # ingest names each book after its file, which isn't in the list of graded names
        old_way = s.score_chunk(BOOK, "practicalcarpen01radfgoog")
        by_folder = s.score_chunk(BOOK, "practicalcarpen01radfgoog", "build")
        self.assertLess(old_way["score"], 70)                    # what every book used to get
        self.assertGreaterEqual(by_folder["score"], 82)
        self.assertIn(by_folder["level"], ("MEDIUM", "HIGH"))
        self.assertEqual(s.score_chunk(BOOK, "x", "medical")["level"], "HIGH")
        # a book that IS listed keeps its own grade
        self.assertEqual(s.score_chunk("text " * 40, "where_no_doctor", "medical")["score"], 95)


class TestInstructions(unittest.TestCase):
    def bounds(self, q, tab, has_sources=True, conflict=False, mode=ResponseMode.DIRECT):
        plan = IntentRouter().route(q, tab)
        return build_bounds(plan, mode, has_sources, conflict, tab)

    def test_build_with_good_sources_gets_no_failure_block_or_question_prompt(self):
        b = self.bounds("how do i waterproof a wooden box", "build")
        self.assertNotIn("When the library falls short", b)
        self.assertNotIn("clarifying question", b)

    def test_failure_rules_stay_where_they_matter(self):
        self.assertIn("When the library falls short", self.bounds("how do i waterproof a box", "build", has_sources=False))
        self.assertIn("When the library falls short", self.bounds("how do i waterproof a box", "build", conflict=True))
        med = self.bounds("how do i clean a wound", "medical")
        self.assertIn("When the library falls short", med)


class TestLeanPrompt(unittest.TestCase):
    """It was 520 words of rules around two facts; the facts now come last, the rules short."""

    def test_lye_question(self):
        from tests.test_librarian import FakeLLM
        from core.you.memory import Memory
        from core.library.rag import KnowledgeBase
        from core.answers.pipeline import QueryPipeline
        from core.you.tabs import TabManager
        llm = FakeLLM(facts="- Pour rainwater slowly through hardwood ash [1]")
        pipe = QueryPipeline(Memory(), KnowledgeBase(), llm)
        q = "How do I make lye from wood ash?"
        out = pipe.prepare_knowledge(TabManager().get_tab("chemistry"), q, pipe.route(q, "chemistry"))
        ctx = out.turn_context
        rules = ctx.split("The steps as the books give them")[0]
        self.assertLess(len(rules.split()), 190)                      # was ~480 words of rules
        self.assertIn("Making Lye from Wood Ash", ctx.split("The steps as the books give them")[1])
        for parroted in ("Say: \"", "SOURCE STATUS", "BEHAVIOURAL", "DOMAIN GUARD", "Source guidance",
                         "soap_from_ash", "chemistry_reference", "Day: 1", "LIBRARY FACTS",
                         "clarifying question"):
            self.assertNotIn(parroted, out.full_prompt)

    def test_facts_come_last_without_markers(self):
        from tests.test_librarian import FakeLLM
        from core.you.memory import Memory
        from core.library.rag import KnowledgeBase
        from core.answers.pipeline import QueryPipeline
        from core.you.tabs import TabManager
        llm = FakeLLM(facts="- Lye is made by leaching hardwood ash with water [1]")
        pipe = QueryPipeline(Memory(), KnowledgeBase(), llm)
        q = "tell me about lye from wood ash"
        out = pipe.prepare_knowledge(TabManager().get_tab("chemistry"), q, pipe.route(q, "chemistry"))
        self.assertTrue(out.turn_context.rstrip().endswith("hardwood ash with water"))

    def test_not_breathing_gets_the_steps(self):
        # The passage was cut off at "If person is unconscious and not breathing: 1. …"
        from tests.test_librarian import FakeLLM
        from core.you.memory import Memory
        from core.library.rag import KnowledgeBase
        from core.answers.pipeline import QueryPipeline
        from core.you.tabs import TabManager
        pipe = QueryPipeline(Memory(), KnowledgeBase(), FakeLLM())
        q = "he's not breathing what do i do"
        out = pipe.prepare_knowledge(TabManager().get_tab("medical"), q, pipe.route(q, "medical"))
        self.assertIn("Tilt head back", out.full_prompt)
        self.assertIn("30 chest compressions", out.full_prompt)
        self.assertNotIn("emergency_procedures", out.full_prompt)          # no file names
        self.assertNotIn("When the library falls short", out.full_prompt)  # emergencies stay lean


class TestRepeatedPassages(unittest.TestCase):
    def test_overlapping_passages_are_used_once(self):
        a = {"content": BOOK + " Keep the lid overlapping by an inch.", "source": "carpentry", "domain": "build"}
        b = {"content": "Keep the lid overlapping by an inch. " + BOOK, "source": "carpentry", "domain": "build"}
        c = {"content": "Choose a dry raised site so water runs away from the walls, at least 30 feet "
                        "from any stream that may flood.", "source": "masonry", "domain": "build"}
        kept = KnowledgeBase._diverse([a, b, c])
        self.assertEqual(kept, [a, c])


if __name__ == "__main__":
    unittest.main()
