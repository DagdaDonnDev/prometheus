"""Disagreement between passages: only real ones about what was asked."""

import unittest

from core.answers.contradiction import ContradictionDetector


class TestContradiction(unittest.TestCase):
    def setUp(self):
        self.c = ContradictionDetector()

    def check(self, a, b, query):
        return self.c.detect([{"content": a}, {"content": b}], query=query)

    def test_real_disagreements(self):
        found, desc = self.check("Hemlock is edible when young.", "Hemlock is poisonous.", "is hemlock edible")
        self.assertTrue(found)
        self.assertIn("poisonous", desc)
        found, desc = self.check("Boil water for 1 minute to purify water.",
                                 "Boil water for 10 minutes to purify it.", "how long to boil water")
        self.assertTrue(found)
        self.assertIn("minute", desc)

    def test_no_false_alarms(self):
        # From the owner's log: a log-shelter answer became "Source A says… Source B says…"
        self.assertFalse(self.check("For a log shelter you should stack logs. Do not use rotten wood.",
                                    "Do place the shelter on high ground.",
                                    "how do I build a simple log shelter")[0])
        # Different things in different units, and opposite words about other subjects
        self.assertFalse(self.check("Give 500 mg of aspirin for the wound.",
                                    "Clean the wound for 2 minutes.", "how do I treat a wound")[0])
        self.assertFalse(self.check("Pottery: boil the clay slip.", "Wounds: do not boil the dressing.",
                                    "how do I clean a wound")[0])


if __name__ == "__main__":
    unittest.main()
