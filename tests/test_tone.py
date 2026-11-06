"""Tone read from the message (core/tone.py). Run: python -m unittest discover tests"""

import unittest

from core.tone import detect_tone


class TestTone(unittest.TestCase):
    def check(self, text, want, previous=""):
        self.assertEqual(detect_tone(text, previous)[0], want, text)

    def test_annoyed(self):
        self.check("wait the juror isnt about that at all", "annoyed")
        self.check("your not hearing me", "annoyed")
        self.check("NO STOP", "annoyed")
        self.check("no it isnt", "annoyed", previous="wait the juror isnt about that at all")

    def test_low(self):
        self.check("i had a really rough day", "low")
        self.check("yeah", "low", previous="i had a really rough day")

    def test_excited(self):
        self.check("I GOT THE JOB!!", "excited")     # capitals amplify, not anger
        self.check("guess what, i finally finished the shed 😄", "excited")

    def test_curious_and_neutral(self):
        self.check("similar movies?", "curious")
        self.check("Tell me about To Kill a Mockingbird", "curious")
        self.check("hey", "neutral")
        self.check("cool", "neutral")


if __name__ == "__main__":
    unittest.main()
