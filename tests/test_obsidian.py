"""Obsidian: properties, mind-map export, reading Me.md edits back, notes as a source."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import obsidian
from core.tabs import Tab


class _Mem:
    def __init__(self):
        self.data = {"user": {"name": "Ethan", "location_estimate": "Cork", "day_count": 3,
                              "work": None, "mentioned_people": ["Kate (sister)"],
                              "likes": ["hiking"], "dislikes": [], "known_skills": [], "notes": []}}

    def save(self):
        pass


class _Tabs:
    def __init__(self, tabs):
        self.tabs = tabs


def _tab(id_, name):
    return Tab(id=id_, name=name, icon="", domains=[], system_prompt="")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.vault = root / "vault"
        self.vault.mkdir()
        self.state = mock.patch.object(obsidian, "STATE_PATH", root / "state.json")
        self.state.start()
        self.nowiki = mock.patch("core.wiki_lookup.find_articles", return_value=[])
        self.nowiki.start()
        obsidian.set_vault(str(self.vault))

    def tearDown(self):
        self.nowiki.stop()
        self.state.stop()
        obsidian.set_vault("")
        self.tmp.cleanup()


class TestFrontmatter(unittest.TestCase):
    def test_round_trip(self):
        props = {"name": "Ethan", "location": "Cork, Ireland", "day": 3,
                 "people": ["Kate (sister)", 'Says "hi": often'], "likes": [], "work": ""}
        back, body = obsidian.parse_frontmatter(obsidian.dump_frontmatter(props) + "\nbody")
        self.assertEqual(back["name"], "Ethan")
        self.assertEqual(back["location"], "Cork, Ireland")
        self.assertEqual(back["day"], "3")
        self.assertEqual(back["people"], ["Kate (sister)", 'Says "hi": often'])
        self.assertEqual(back["likes"], [])
        self.assertIsNone(back["work"])
        self.assertEqual(body.strip(), "body")

    def test_obsidian_styles(self):
        text = "---\nlikes: [hiking, 'sea swims']\nskills:\n  - knots\n  - \"first aid\"\n---\n"
        props, _ = obsidian.parse_frontmatter(text)
        self.assertEqual(props["likes"], ["hiking", "sea swims"])
        self.assertEqual(props["skills"], ["knots", "first aid"])

    def test_safe_name(self):
        self.assertEqual(obsidian.safe_name('What? is "this": a/b#c'), "What is this abc")


class TestExport(Base):
    def _setup_tabs(self):
        chat = _tab("prometheus", "Prometheus")
        chat.add_message("user", "how do I purify water")
        chat.add_message("assistant", "Boil it for a minute.")
        chat.new_chat()
        chat.add_message("user", "I'm feeling lonely")
        surv = _tab("survival", "Survival")
        wiki = _tab("wikipedia", "Wikipedia")
        return _Tabs([chat, wiki, surv])

    def test_mind_map_files(self):
        tabs = self._setup_tabs()
        msg = obsidian.sync(_Mem(), tabs)
        root = self.vault / "Prometheus"
        self.assertTrue((root / "Me.md").exists(), msg)
        self.assertTrue((root / "Prometheus.md").exists())
        self.assertTrue((root / "Survival.md").exists())
        self.assertFalse((root / "Wikipedia.md").exists())
        chats = sorted(p.name for p in (root / "Chats").glob("*.md"))
        self.assertEqual(len(chats), 2)
        hub = (root / "Prometheus.md").read_text(encoding="utf-8")
        self.assertIn("[[Prometheus/Topics/Water purification|Water purification]]", hub)
        self.assertIn("[[Prometheus/Topics/Loneliness|Loneliness]]", hub)
        self.assertIn("[[Prometheus/Me|Me]]", hub)
        self.assertTrue((root / "Topics" / "Water purification.md").exists())
        me = (root / "Me.md").read_text(encoding="utf-8")
        self.assertIn("  - Kate (sister)", me)
        self.assertIn("[[Prometheus/Survival|Survival]]", me)
        # Nothing changed → nothing rewritten
        self.assertEqual(obsidian.sync(_Mem(), tabs), "Up to date.")

    def test_deleted_chat_note_removed_only_if_untouched(self):
        tabs = self._setup_tabs()
        obsidian.sync(_Mem(), tabs)
        chat_tab = tabs.tabs[0]
        notes = sorted((self.vault / "Prometheus" / "Chats").glob("*.md"))
        # The person edits the lonely chat's note; then both chats are deleted
        edited = next(p for p in notes if "lonely" in p.name)
        edited.write_text(edited.read_text(encoding="utf-8") + "\nmy own thoughts\n", encoding="utf-8")
        for c in chat_tab.all_chats():
            chat_tab.delete_chat(c["id"])
        obsidian.sync(_Mem(), tabs)
        left = list((self.vault / "Prometheus" / "Chats").glob("*.md"))
        self.assertEqual(left, [edited])


class TestReadBack(Base):
    def test_edits_in_obsidian_come_back(self):
        mem = _Mem()
        tabs = _Tabs([_tab("prometheus", "Prometheus")])
        obsidian.sync(mem, tabs)
        me = self.vault / "Prometheus" / "Me.md"
        text = me.read_text(encoding="utf-8")
        # In Obsidian: fix the location, remove "hiking", add "climbing", set work
        text = text.replace("location: Cork", "location: Galway")
        text = text.replace("  - hiking", "  - climbing")
        text = text.replace("work:\n", "work: nurse\n")
        me.write_text(text, encoding="utf-8")
        # Meanwhile the app learned something new
        mem.data["user"]["likes"].append("chess")
        msg = obsidian.sync(mem, tabs)
        u = mem.data["user"]
        self.assertEqual(u["location_estimate"], "Galway")
        self.assertEqual(u["work"], "nurse")
        self.assertEqual(sorted(u["likes"]), ["chess", "climbing"])
        self.assertIn("read back", msg)
        # And Me.md now shows the merged result
        self.assertIn("  - chess", me.read_text(encoding="utf-8"))

    def test_unchanged_me_changes_nothing(self):
        mem = _Mem()
        tabs = _Tabs([])
        obsidian.sync(mem, tabs)
        mem.data["user"]["likes"] = ["new thing"]
        self.assertEqual(obsidian.read_back_only(mem), [])
        self.assertEqual(mem.data["user"]["likes"], ["new thing"])


class TestOwnNotes(Base):
    def setUp(self):
        super().setUp()
        (self.vault / "Garden").mkdir()
        (self.vault / "Garden" / "Sourdough Starter.md").write_text(
            "---\ntags: [food]\n---\nFeed the starter flour and water every day. Keep it warm.",
            encoding="utf-8")
        (self.vault / "Radio.md").write_text("My radio is a Baofeng UV-5R on 145.500.", encoding="utf-8")
        (self.vault / ".obsidian").mkdir()
        (self.vault / ".obsidian" / "x.md").write_text("starter starter starter", encoding="utf-8")
        (self.vault / "Prometheus").mkdir()
        (self.vault / "Prometheus" / "Me.md").write_text("starter flour", encoding="utf-8")

    def test_search_skips_own_folder_and_hidden(self):
        hits = obsidian.search_notes("how do I feed a sourdough starter")
        self.assertEqual([h["source"] for h in hits], ["Obsidian — Sourdough Starter"])
        self.assertIn("flour", hits[0]["content"])
        self.assertNotIn("tags", hits[0]["content"])
        self.assertEqual(obsidian.note_count(), 2)

    def test_named_in_message(self):
        self.assertEqual(obsidian.notes_named_in("what did I write about my sourdough starter?")[0][0],
                         "Sourdough Starter")
        self.assertEqual(obsidian.notes_named_in("what's on the Radio tonight")[0][0], "Radio")
        self.assertEqual(obsidian.notes_named_in("turn the radio on"), [])

    def test_chat_links_to_their_note(self):
        t = _tab("prometheus", "Prometheus")
        t.add_message("user", "is my sourdough starter ok?")
        obsidian.sync(_Mem(), _Tabs([t]))
        note = next((self.vault / "Prometheus" / "Chats").glob("*.md")).read_text(encoding="utf-8")
        self.assertIn("[[Garden/Sourdough Starter|Sourdough Starter]]", note)
        hub = (self.vault / "Prometheus" / "Prometheus.md").read_text(encoding="utf-8")
        self.assertRegex(hub, r"\|\d+ \w{3} · is my sourdough starter ok\]\]")

    def test_note_named_after_question_is_used(self):
        from core.rag import KnowledgeBase
        kb = KnowledgeBase.__new__(KnowledgeBase)
        KnowledgeBase.__init__(kb)
        kb.prompt_passages = 1
        # An ordinary downloaded book's passage vs their note named after the question
        manual = {"content": "Bread is made from flour, water and salt, then baked. " * 8,
                  "source": "some_downloaded_book", "domain": "food_preservation"}
        note = obsidian.search_notes("how do I feed a sourdough starter")[0]
        kb._score_and_format("feed sourdough starter", [manual, note], False, 3)
        self.assertEqual(kb.get_last_sources(), ["Obsidian — Sourdough Starter"])

    def test_off_when_unticked(self):
        obsidian.set_vault(str(self.vault), use_notes=False)
        self.assertEqual(obsidian.search_notes("sourdough starter"), [])


if __name__ == "__main__":
    unittest.main()
