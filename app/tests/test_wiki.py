"""
Wikipedia title lookup and search — no Qt, no Ollama.
Run from the project root:  python -m unittest discover tests
"""

import tempfile
import unittest
from pathlib import Path

import core.library.wiki_lookup as w


ARTICLES = {
    "Inception": "Inception may refer to: a film, a beginning.",
    "Inception_film": "Inception is a 2010 science fiction film directed by Christopher Nolan.",
    "The_Matrix": "The Matrix is a 1999 science fiction action film.",
    "Yesterday": "Yesterday is the day before today.",
    "Yesterday_song": "Yesterday is a song by the Beatles.",
    "Breaking_Bad": "Breaking Bad is an American crime drama television series.",
    "Movie": "A movie is a film.",
    "Your_Name": "Your Name is a 2016 Japanese animated film.",
}


class TestWiki(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = w.WIKI_DIR
        w.WIKI_DIR = Path(self.tmp.name)
        w._cache.update({"mtime": None, "titles": {}})
        for stem, body in ARTICLES.items():
            title = stem.replace("_film", " (film)").replace("_song", " (song)").replace("_", " ")
            (w.WIKI_DIR / f"{stem}.txt").write_text(f"# {title}\n\n{body}", encoding="utf-8")

    def tearDown(self):
        w.WIKI_DIR = self.old
        w._cache.update({"mtime": None, "titles": {}})
        self.tmp.cleanup()

    def titles(self, text):
        return [t for t, _ in w.find_articles(text)]

    def test_finds_named_things(self):
        self.assertEqual(self.titles("have you seen inception?"), ["Inception (film)"])   # lower case, after "seen"
        self.assertEqual(self.titles("what did you think of the matrix"), ["The Matrix"])
        self.assertEqual(self.titles("breaking bad is so good"), ["Breaking Bad"])
        self.assertEqual(self.titles("i love the song Yesterday"), ["Yesterday (song)"])

    def test_skips_everyday_words(self):
        self.assertEqual(self.titles("I watched a movie yesterday"), [])
        self.assertEqual(self.titles("hey how's it going"), [])

    def test_small_talk_is_not_a_title(self):
        # From the owner's log: "your name" pulled up the anime "Your Name"
        self.assertEqual(self.titles("what's your name"), [])
        self.assertEqual(self.titles("i forgot your name sorry"), [])
        # …but it still works when it's plainly the film
        self.assertEqual(self.titles("have you seen your name"), ["Your Name"])
        self.assertEqual(self.titles("I loved Your Name"), ["Your Name"])
        self.assertEqual(self.titles("is your name a good film"), ["Your Name"])

    def test_passage_answers_the_question(self):
        # "what's the story of it?" — the plot is far below the article's opening
        art = w.WIKI_DIR / "Halo_series.txt"
        art.write_text("# Halo (series)\n\nHalo is a military science fiction video game series. "
                       + "It sold many copies on many machines over many years. " * 60
                       + "The story follows Master Chief, a super-soldier fighting the Covenant. "
                       + "Reviews praised the music. " * 30, encoding="utf-8")
        story = w.passage_for(art, "Halo (series)", "tell me about halo the game what's the story of it?", 80)
        self.assertIn("Master Chief", story)
        self.assertTrue(story.startswith("Halo is a military science fiction video game series."))
        opening = w.passage_for(art, "Halo (series)", "tell me about halo", 80)
        self.assertNotIn("Master Chief", opening)                      # just about it: the opening

    def test_disambiguation_prefers_the_real_article(self):
        self.assertEqual(self.titles("Have you seen Inception"), ["Inception (film)"])

    def test_search_ranks_titles(self):
        r = [x["title"] for x in w.search("inception")]
        self.assertEqual(r[:2], ["Inception", "Inception (film)"])
        self.assertEqual(w.search("xyzzy"), [])
        self.assertIn("Breaking Bad", [x["title"] for x in w.search("breaking")])

    def test_lead(self):
        p = w.WIKI_DIR / "Inception_film.txt"
        self.assertTrue(w.lead(p, 5).startswith("Inception is a 2010"))
        self.assertNotIn("# ", w.lead(p, 50))

    def test_full_text_finds_words_inside_articles(self):
        from core.library import wiki_index
        idx = w.WIKI_DIR.parent / "wikipedia_search.sqlite"
        self.assertEqual(wiki_index.build_index(w.WIKI_DIR, idx, progress=lambda m: None), len(ARTICLES))
        try:
            self.assertTrue(w.full_text_ready())
            r = w.search("christopher nolan")            # only in Inception (film)'s text
            self.assertEqual(r[0]["title"], "Inception (film)")
            self.assertIn("Nolan", r[0]["snippet"])
            self.assertEqual(w.search("beatles")[0]["title"], "Yesterday (song)")
            self.assertEqual(w.search("incep")[0]["title"], "Inception")   # title prefix stays on top
            self.assertEqual(w.search("qqqzzz"), [])
            self.assertEqual(wiki_index.search('"; DROP TABLE articles; --', index_path=idx), [])  # safe
        finally:
            idx.unlink()

    def test_asked_about(self):
        cases = {
            "have you seen the juror?": "the juror",
            "what do you think of Green Book": "Green Book",
            "Tell me about To Kill a Mockingbird": "To Kill a Mockingbird",
            "the film named Arrival was great": "Arrival",
            "tell me about your day": "",
            "have you seen it?": "",
            "what's up": "",
            "tell me about fire": "",       # lower case, vague lead-in → not a named thing
            "hey do you know about bt 7274": "bt 7274",                 # a number makes it a name
            "tell me what you know of titanfall 2": "titanfall 2",
            "do you know about cooking": "",
            "why dont you tell me what you know": "",
        }
        for text, want in cases.items():
            self.assertEqual(w.asked_about(text), want, text)

    def test_no_folder(self):
        w.WIKI_DIR = Path(self.tmp.name) / "missing"
        w._cache.update({"mtime": None, "titles": {}})
        self.assertEqual(w.find_articles("have you seen inception"), [])
        self.assertEqual(w.search("inception"), [])


if __name__ == "__main__":
    unittest.main()
