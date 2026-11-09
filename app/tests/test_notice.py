"""Facts the model notices: only from what was said, and only into Review."""

import os
import tempfile
import unittest
from unittest import mock

from core.you import claims, notice


class _Mem:
    def __init__(self):
        self.data = {"user": {"mentioned_people": [], "likes": [], "dislikes": [], "known_skills": []}}

    def save(self):
        pass


class FakeLibrarian:
    def __init__(self, answer):
        from core.app.config import Config
        self.config, self.answer, self.calls = Config(), answer, 0

    def complete(self, system, prompt, **kw):
        self.calls += 1
        return self.answer


class TestNotice(unittest.TestCase):
    def test_only_asks_about_messages_about_themselves(self):
        self.assertTrue(notice.worth_asking("we moved to Galway last year"))
        self.assertFalse(notice.worth_asking("how do I purify water?"))
        self.assertFalse(notice.worth_asking("ok"))
        llm = FakeLibrarian("location: Galway")
        self.assertEqual(notice.notice(llm, "what is the capital of France?"), [])
        self.assertEqual(llm.calls, 0)

    def test_finds_what_the_patterns_miss(self):
        text = "we moved to Galway last year and my brother Tom fixes cars for a living"
        llm = FakeLibrarian("location: Galway\nperson: Tom (brother)\nskill: fixes cars")
        got = {(c.field, c.value) for c in notice.notice(llm, text)}
        self.assertEqual(got, {("location_estimate", "Galway"), ("mentioned_people", "Tom (brother)"),
                               ("known_skills", "fixes cars")})

    def test_values_not_in_their_words_are_dropped(self):
        text = "my sister came round and we went hiking"
        llm = FakeLibrarian("person: Kate (sister)\nlike: hiking\nlocation: Dublin\nwork: nurse")
        got = {(c.field, c.value) for c in notice.notice(llm, text)}
        self.assertEqual(got, {("likes", "hiking")})       # Kate, Dublin, nurse were never said

    def test_none_means_nothing(self):
        self.assertEqual(notice.parse("NONE", "my day was fine"), [])

    def test_staged_for_review_as_noticed_by_the_model(self):
        with tempfile.TemporaryDirectory() as t, \
                mock.patch.object(claims, "DB_PATH", os.path.join(t, "c.sqlite")):
            text = "we moved to Galway last year"
            m = _Mem()
            claims.stage(notice.parse("location: Galway", text), m)
            [c] = claims.pending()
            self.assertEqual((c.origin, c.note), ("model", "you live in Galway"))
            self.assertLess(c.confidence, 0.65)                # shown as "not sure"
            claims.accept(c.id, m)
            self.assertEqual(m.data["user"]["location_estimate"], "Galway")


if __name__ == "__main__":
    unittest.main()
