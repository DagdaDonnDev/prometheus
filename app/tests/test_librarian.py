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
        self.assertIn("Nothing new in the library for this", facts_block(f))

    def test_unreachable_librarian_is_not_not_found(self):
        f = Librarian(FakeLLM(fail=True)).extract("Q", [("x", "text")])
        self.assertTrue(f.failed)
        b = Librarian(FakeLLM(fail=True)).brief("how do i boil water")
        self.assertEqual(b.question, "how do i boil water")    # falls back to the message itself


class TestFromTheLog(unittest.TestCase):
    """Owner's debug log, 2026-11-09 15:24."""

    def test_copied_instructions_are_not_searched(self):
        llm = FakeLLM(brief="SEARCH: 3-8 keywords to look up (names, things, the topic)\n"
                            "QUESTION: the person's question, written out in full on one line")
        b = Librarian(llm).brief("what are some poisonous mushrooms in ireland")
        self.assertEqual(b.search, "what are some poisonous mushrooms in ireland")

    def test_long_keyword_lists_are_cut(self):
        llm = FakeLLM(brief="SEARCH: halo, halo 4, halo infinite, halo: combatants, halo: combatants 2, "
                            "xbox, game, console\nQUESTION: what is halo?")
        self.assertLessEqual(len(Librarian(llm).brief("halo the game").search.split()), 8)

    def test_relevant(self):
        from core.ai.librarian import relevant
        self.assertTrue(relevant("what are some posionous mushrooms in ireland with images",
                                 "Many mushrooms are poisonous; the death cap kills."))
        self.assertTrue(relevant("How do I make lye from wood ash?",
                                 "Fill the container with wood ash and pour water to leach lye."))
        self.assertFalse(relevant("halo the game", "Apply a pressure dressing to the wound."))
        self.assertTrue(relevant("who are you", "anything"))         # nothing to judge by

    def test_cited(self):
        from core.ai.librarian import Facts
        self.assertEqual(Facts("- a [1]\n- b [3]", True).cited(), {1, 3})


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
        # It names its subject, so no rewrite step (it turned "log shelter" into
        # "materials construction safety") — straight to the librarian
        self.assertEqual(models, [self.llm.config.librarian_model])
        # The librarian gets their own words, not the speaker's rewrite (it
        # turned "soap from fat" into "soap from coconut oil")
        self.assertIn("QUESTION: how do i purify water", self.llm.calls[-1][2])
        self.assertIn("LIBRARY FACTS", out.full_prompt)
        self.assertIn("Boil water for 1 minute", out.full_prompt)
        self.assertNotIn("Retrieved knowledge — use as primary source:\n[", out.full_prompt)

    def test_emergency_skips_the_librarian(self):
        self.prepare("he's not breathing what do i do", "medical")
        self.assertEqual(self.llm.calls, [])

    def test_small_talk_is_one_call(self):
        with mock.patch("core.library.wiki_lookup.find_articles", return_value=[]):
            out = self.prepare("hey how's it going", "prometheus")
        self.assertEqual(self.llm.calls, [])
        self.assertNotIn("LIBRARY FACTS", out.full_prompt)

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
        self.assertIn("LIBRARY FACTS", out.full_prompt)
        self.assertNotIn("Christopher Nolan. Inception", out.full_prompt)     # no raw article text
        self.assertTrue(out.full_prompt.rstrip().split("\n")[-1].startswith("Right now:"))

    def test_not_found_but_on_the_subject_reads_the_passages(self):
        # The soap guide has "Making Lye from Wood Ash"; the librarian said NOT FOUND
        self.llm.facts = "NOT FOUND"
        out = self.prepare("How do I make lye from wood ash?", "chemistry")
        self.assertIn("FROM THE LIBRARY", out.full_prompt)
        self.assertIn("ash", out.full_prompt.split("FROM THE LIBRARY", 1)[1].lower())
        self.assertNotIn("Nothing new in the library for this", out.full_prompt)
        self.assertTrue(out.sources)

    def test_not_found_and_off_subject_shows_nothing(self):
        # "halo the game" pulled a first-aid manual's cover page in as a picture
        self.llm.facts = "NOT FOUND"
        self.llm.brief = "SEARCH: halo game\nQUESTION: what is the game halo?"
        with mock.patch("core.library.wiki_lookup.find_articles", return_value=[]):
            out = self.prepare("halo the game", "survival")
        self.assertIn("Nothing new in the library for this", out.full_prompt)
        self.assertEqual(out.images, [])
        self.assertEqual(out.sources, [])

    def test_sources_are_the_cited_passages(self):
        self.llm.facts = "- Boil water for 1 minute [1]"
        out = self.prepare("how do i purify water", "survival")
        self.assertEqual(len(out.sources), 1)

    def test_chat_not_found_on_the_subject_reads_the_article(self):
        from pathlib import Path
        import tempfile
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        art = Path(d.name) / "Magic_The_Gathering.txt"
        art.write_text("# Magic: The Gathering\n\nMagic: The Gathering is a trading card game "
                       "made by Richard Garfield in 1993. Players are wizards casting spells.")
        self.llm.facts = "NOT FOUND"
        with mock.patch("core.library.wiki_lookup.find_articles",
                        return_value=[("Magic: The Gathering", art)]):
            out = self.prepare("what can you tell me about magic the gathering", "prometheus")
        self.assertIn("Richard Garfield", out.full_prompt)

    def test_who_are_you_does_not_carry_the_last_subject(self):
        from core.answers.pipeline import QueryPipeline
        from types import SimpleNamespace
        tab = SimpleNamespace(history=[{"role": "user", "content": "have you seen Inception"},
                                       {"role": "assistant", "content": "Yes."}])
        with mock.patch("core.library.wiki_lookup.find_articles",
                        side_effect=lambda t, max_articles=2: [("x", None)] if "Inception" in t else []):
            self.assertEqual(QueryPipeline._subject_text(tab, "who are you"), "who are you")

    def test_off_switch_is_the_old_way(self):
        self.llm.config.two_models = False
        self.prepare("how do i purify water", "survival")
        self.assertEqual(self.llm.calls, [])


class TestFromTheLog1110(unittest.TestCase):
    """Owner's debug log, 2026-11-10 08:41 — "it's still quite dumb"."""

    def setUp(self):
        import tempfile
        from pathlib import Path
        from core.library import wiki_lookup as w
        from core.you.memory import Memory
        from core.library.rag import KnowledgeBase
        from core.answers.pipeline import QueryPipeline
        from core.you.tabs import TabManager
        self.tmp = tempfile.TemporaryDirectory()
        wiki = Path(self.tmp.name) / "wikipedia"
        wiki.mkdir()
        for stem, title, body in [
                ("Magic_The_Gathering", "Magic: The Gathering",
                 "Magic: The Gathering is a trading card game created by Richard Garfield in 1993."),
                ("Confucius", "Confucius",
                 "Confucius was a Chinese philosopher and teacher who lived from 551 to 479 BC."),
                ("Your_Name", "Your Name", "Your Name is a 2016 Japanese animated film."),
                ("Halo", "Halo", "A halo is a ring of light around the Sun or Moon."),
                ("Halo_series", "Halo (series)",
                 "Halo is a military science fiction video game series made by Bungie. "
                 "The story follows Master Chief fighting the Covenant.")]:
            (wiki / f"{stem}.txt").write_text(f"# {title}\n\n" + (body + " ") * 5)
        self.old = (w.WIKI_DIR, w.FULL_DB)
        w.WIKI_DIR, w.FULL_DB = wiki, wiki / "none.sqlite"
        w._cache.update({"mtime": None, "titles": {}})
        w._closest_cache.clear()
        self.llm = FakeLLM()
        self.pipe = QueryPipeline(Memory(), KnowledgeBase(), self.llm)
        self.tabs = TabManager()

    def tearDown(self):
        from core.library import wiki_lookup as w
        w.WIKI_DIR, w.FULL_DB = self.old
        w._cache.update({"mtime": None, "titles": {}})
        w._closest_cache.clear()
        self.pipe.config.assistant_name = "Prometheus"
        self.tmp.cleanup()

    def prepare(self, q, tab):
        tab = self.tabs.get_tab(tab) if isinstance(tab, str) else tab
        return self.pipe.prepare_knowledge(tab, q, self.pipe.route(q, tab.id))

    def test_facts_written_as_numbered_lines_are_kept(self):
        from core.ai.librarian import parse_facts
        raw = ("[1] Pour lye into fat, stirring constantly; saponification takes up to an hour. "
               "[2] Add vegetable oil to sand or pumice; melt it\nNOT FOUND")
        self.assertEqual(parse_facts(raw), [
            "- Pour lye into fat, stirring constantly; saponification takes up to an hour. [1]",
            "- Add vegetable oil to sand or pumice; melt it [2]"])
        self.assertEqual(parse_facts("[2] The passage lists several authors and works"), [])
        self.llm.facts = raw
        out = self.prepare("How do I make soap from fat?", "chemistry")
        self.assertIn("LIBRARY FACTS", out.full_prompt)
        self.assertIn("Pour lye into fat", out.full_prompt)
        self.assertIn("No links, file names", out.full_prompt)

    def test_librarian_gets_their_words_not_the_rewrite(self):
        self.llm.brief = "SEARCH: soap fat lye\nQUESTION: I want to make soap from coconut oil and lye."
        self.prepare("How do I make soap from fat?", "chemistry")
        self.assertNotIn("coconut", self.llm.calls[-1][2])
        self.assertIn("QUESTION: How do I make soap from fat?", self.llm.calls[-1][2])

    def test_entertainment_tab_reads_wikipedia(self):
        from core.you.tabs import Tab
        tab = Tab(id="custom_entertainment_9", name="Entertainment", icon="", domains=["general"],
                  system_prompt="You are Prometheus, focused on: films and games.", custom=True)
        self.llm.facts = "- Magic: The Gathering is a trading card game made in 1993 [1]"
        out = self.prepare("tell me about magic the gathering", tab)
        self.assertIn("Richard Garfield", self.llm.calls[-1][2])            # the article went in
        self.assertIn("Wikipedia — Magic: The Gathering", out.sources)

    def test_asking_about_its_name(self):
        self.pipe.config.assistant_name = "confuscious"
        out = self.prepare("who is confuscious", "prometheus")
        self.assertIn("your name is confuscious, after Confucius", out.full_prompt)
        self.assertIn("Chinese philosopher", out.full_prompt)
        self.assertNotIn("Your Name is a 2016", out.full_prompt)
        out = self.prepare("confucious is based on a real person who is that person", "prometheus")
        self.assertIn("after Confucius", out.full_prompt)
        self.assertIn("never say you don't have one", out.full_prompt)

    def test_picture_request_says_whether_one_is_shown(self):
        self.llm.facts = "NOT FOUND"
        out = self.prepare("can you show me a picture of hemlock for reference", "survival")
        self.assertIn("PICTURE:", out.full_prompt)

    def test_follow_up_without_a_subject_still_gets_the_request(self):
        tab = self.tabs.get_tab("survival")
        saved = list(tab.history)
        self.addCleanup(setattr, tab, "history", saved)
        tab.history = [{"role": "user", "content": "how do i purify water"},
                       {"role": "assistant", "content": "Boil it."}]
        self.prepare("do you have some pictures of instructions?", tab)
        self.assertEqual(self.llm.calls[0][0], self.llm.config.speaker_model)    # the request
        self.assertIn("purify water", self.llm.calls[-1][2])                     # librarian: last subject

    def test_noise_and_meta_lines_are_not_facts(self):
        from core.ai.librarian import parse_facts
        raw = ("- (FM 21-10 Field Hygiene Sanitation) pw2PIEIHGwgéÇ2REIIFIh [1]\n"
               "- The guide mentions using a \"compressive method\" for straw. [2]\n"
               "- It references building under a marquee. [3]\n"
               "- Boil water for one full minute to kill germs. [4]")
        self.assertEqual(parse_facts(raw), ["- Boil water for one full minute to kill germs. [4]"])

    def test_no_subject_no_library(self):
        from core.you.tabs import Tab
        tab = Tab(id="custom_entertainment_9", name="Entertainment", icon="", domains=["general"],
                  system_prompt="You are Prometheus, focused on: films.", custom=True)
        out = self.prepare("list 50 movies", tab)
        self.assertNotIn(self.llm.config.librarian_model, [m for m, _, _ in self.llm.calls])
        self.assertNotIn("Nothing new in the library for this", out.full_prompt)
        out = self.prepare("okay what do you know about magic the gathering", tab)
        self.assertIn("Wikipedia — Magic: The Gathering", out.sources)          # "okay" isn't a subject

    def test_halo_the_game(self):
        from core.library.wiki_lookup import find_articles
        self.assertEqual([t for t, _ in find_articles("halo the game")], ["Halo (series)"])
        self.assertEqual([t for t, _ in find_articles("what do you know about the halo games")],
                         ["Halo (series)"])

    def test_follow_up_remembers_the_last_question(self):
        # Owner: "it doesn't remember the context of the last message at all"
        from core.you.tabs import Tab
        tab = Tab(id="custom_entertainment_9", name="Entertainment", icon="", domains=["general"],
                  system_prompt="You are Prometheus, focused on: games.", custom=True)
        tab.history = [{"role": "user", "content": "tell me about halo the game"},
                       {"role": "assistant", "content": "Halo is a video game series by Bungie."}]
        self.llm.facts = "- The story follows Master Chief fighting the Covenant [1]"
        out = self.prepare("what's the story of it?", tab)
        self.assertIn("Master Chief", self.llm.calls[-1][2])            # the Halo article went in
        self.assertIn("Wikipedia — Halo (series)", out.sources)

    def test_chat_tab_follow_up_keeps_the_article(self):
        tab = self.tabs.get_tab("prometheus")
        saved = list(tab.history)
        self.addCleanup(setattr, tab, "history", saved)
        tab.history = [{"role": "user", "content": "have you played halo the game"},
                       {"role": "assistant", "content": "A bit."}]
        self.llm.facts = "- The story follows Master Chief [1]"
        out = self.prepare("what's the story of it?", tab)
        self.assertIn("Master Chief", out.full_prompt)

    def test_nothing_on_the_subject_skips_the_librarian(self):
        with mock.patch("core.library.wiki_lookup.find_articles", return_value=[]):
            out = self.prepare("tell me about the xyzzyplugh engine", "build")
        self.assertEqual(self.llm.calls, [])           # names its subject: no brief, no librarian
        self.assertIn("Nothing new in the library for this", out.full_prompt)


if __name__ == "__main__":
    unittest.main()
