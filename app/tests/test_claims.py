"""A fact's life: captured → pending review → accepted (verified) or rejected."""

import os
import sqlite3
import tempfile
import unittest
from unittest import mock

from core.you import claims, profile


class _Mem:
    def __init__(self):
        self.data = {"user": {"name": None, "location_estimate": None, "mentioned_people": [],
                              "likes": [], "dislikes": [], "known_skills": [], "notes": []}}

    def save(self):
        pass


class TestClaims(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "claims.sqlite")
        self.p = mock.patch.object(claims, "DB_PATH", self.db)
        self.p.start()
        self.m = _Mem()

    def tearDown(self):
        self.p.stop()
        self.tmp.cleanup()

    def test_capture_keeps_the_words_time_and_confidence(self):
        profile.learn("honestly my sister Kate is coming over tonight", self.m)
        [c] = claims.pending()
        self.assertEqual((c.field, c.value, c.note), ("mentioned_people", "Kate (sister)", "Kate is your sister"))
        self.assertEqual(c.utterance, "honestly my sister Kate is coming over tonight")
        self.assertTrue(c.created)
        self.assertGreater(c.confidence, 0.5)
        self.assertEqual(claims.pending_count(), 1)

    def test_accept_promotes_with_provenance(self):
        profile.learn("I live in Cork", self.m)
        c = claims.pending()[0]
        claims.accept(c.id, self.m)
        self.assertEqual(self.m.data["user"]["location_estimate"], "Cork")
        self.assertEqual(claims.pending(), [])
        self.assertEqual(claims.provenance("location_estimate", "Cork"), "I live in Cork")
        row = sqlite3.connect(self.db).execute("SELECT verified_by_user FROM verified").fetchone()
        self.assertEqual(row[0], 1)

    def test_edit_then_accept(self):
        profile.learn("my sister Kate is here", self.m)
        c = claims.pending()[0]
        claims.accept(c.id, self.m, edited_value="Katie (sister)")
        self.assertEqual(self.m.data["user"]["mentioned_people"], ["Katie (sister)"])

    def test_reject_is_never_promoted_or_asked_again(self):
        profile.learn("I love hiking", self.m)
        c = next(c for c in claims.pending() if c.value == "hiking")
        claims.reject(c.id)
        self.assertEqual(self.m.data["user"]["likes"], [])
        self.assertEqual(profile.learn("I love hiking", self.m), [])      # not raised again
        self.assertEqual(claims.pending(), [])

    def test_already_in_profile_is_not_raised(self):
        self.m.data["user"]["likes"] = ["hiking"]                          # set in Settings
        self.assertEqual(profile.learn("I love hiking", self.m), [])


if __name__ == "__main__":
    unittest.main()
