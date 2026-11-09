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
        self.assertNotIn("FAILURE-AWARE", b)
        self.assertNotIn("clarifying question", b)

    def test_failure_rules_stay_where_they_matter(self):
        self.assertIn("FAILURE-AWARE", self.bounds("how do i waterproof a box", "build", has_sources=False))
        self.assertIn("FAILURE-AWARE", self.bounds("how do i waterproof a box", "build", conflict=True))
        med = self.bounds("how do i clean a wound", "medical")
        self.assertIn("FAILURE-AWARE", med)


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
