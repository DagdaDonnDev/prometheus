"""Learning about the person from what they say, and the companion line."""

import unittest

from core import profile
from core.tabs import Tab


class _Mem:
    def __init__(self):
        self.data = {"user": {"name": None, "location_estimate": None, "known_skills": [],
                              "mentioned_people": [], "notes": []}}
        self.saved = 0

    def save(self):
        self.saved += 1


class _TempClaims(unittest.TestCase):
    """Each test gets its own claims database."""

    def setUp(self):
        import os, tempfile
        from unittest import mock
        from core import claims
        self.tmp = tempfile.TemporaryDirectory()
        self.p = mock.patch.object(claims, "DB_PATH", os.path.join(self.tmp.name, "claims.sqlite"))
        self.p.start()

    def tearDown(self):
        self.p.stop()
        self.tmp.cleanup()


class TestLearn(_TempClaims):
    def test_learns_plain_statements(self):
        m = _Mem()
        cases = {
            "my name is Ethan": "your name is Ethan",
            "I live in Cork and it rains": "you live in Cork",
            "my sister Kate is visiting": "Kate is your sister",
            "my dog is called Max": "Max is your dog",
            "I love hiking but it's cold": "you like hiking",
            "I hate horror films": "you don't like horror films",
            "my favourite film is Inception": "your favourite film is Inception",
            "I work as a nurse": "you work as nurse",
            "I know how to tie knots": "you can tie knots",
        }
        for text, note in cases.items():
            self.assertEqual(profile.learn(text, m), [note], text)

    def test_nothing_reaches_the_profile_before_review(self):
        m = _Mem()
        profile.learn("my sister Kate is visiting and I love hiking", m)
        self.assertEqual(m.data["user"]["mentioned_people"], [])
        self.assertEqual(m.saved, 0)
        self.assertEqual(profile.about_line(m), "")

    def test_learns_nothing_from_ordinary_talk(self):
        m = _Mem()
        for text in ["I love you", "i like that", "I'm tired", "I'm in trouble",
                     "I would like to know how to purify water", "my mum is sick",
                     "I like it when you're short", "I'm from the countryside"]:
            self.assertEqual(profile.learn(text, m), [], text)

    def test_no_duplicates(self):
        m = _Mem()
        profile.learn("I love hiking", m)
        self.assertEqual(profile.learn("I really love Hiking", m), [])


class TestCompanionLines(_TempClaims):
    def test_about_line_uses_only_accepted_facts(self):
        from core import claims
        m = _Mem()
        self.assertEqual(profile.about_line(m), "")
        profile.learn("I live in Cork. My sister Kate is great. I love hiking.", m)
        for c in claims.pending():
            claims.accept(c.id, m)
        line = profile.about_line(m)
        for bit in ("Cork", "Kate (sister)", "hiking"):
            self.assertIn(bit, line)
        self.assertLess(len(line.split()), 80)

    def test_earlier_topics_are_titles_only(self):
        t = Tab(id="prometheus", name="Chat", icon="", domains=[], system_prompt="")
        self.assertEqual(profile.earlier_topics(t), "")
        t.add_message("user", "Best films about space")
        t.add_message("assistant", "SECRET REPLY TEXT")
        t.new_chat()
        t.add_message("user", "hello")
        line = profile.earlier_topics(t)
        self.assertIn("Best films about space", line)
        self.assertNotIn("SECRET", line)
        self.assertNotIn("hello", line)          # not the current chat


if __name__ == "__main__":
    unittest.main()
