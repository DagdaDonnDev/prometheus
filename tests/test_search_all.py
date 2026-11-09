"""The Search tab: books, notes and Wikipedia in one search, each with its source."""

import json
import os
import tempfile
import unittest
from pathlib import Path


class TestSearchEverything(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = os.getcwd()
        os.chdir(self.tmp.name)
        kb = Path("knowledge_base")
        (kb / "plants" / "_images").mkdir(parents=True)
        (kb / "wikipedia").mkdir()
        (kb / "plants" / "ediblewildplants031709mbp.pdf").write_bytes(b"%PDF")
        (kb / "plants" / "_images" / "ediblewildplants031709mbp_p012.jpg").write_bytes(b"jpg")
        (kb / "titles.json").write_text(json.dumps({"ediblewildplants031709mbp": "Edible Wild Plants"}))
        (kb / "wikipedia" / "Plant.txt").write_text("# Plant\n\nPlants make food from sunlight.")
        Path("memory").mkdir()
        Path("memory/chunks_fallback.json").write_text(json.dumps([
            {"content": "Poisonous plants: water hemlock has purple blotches.", "source":
             "ediblewildplants031709mbp", "domain": "plants", "page_num": 12},
            {"content": "Poisonous plants: water hemlock has purple blotches.", "source":
             "ediblewildplants031709mbp", "domain": "plants", "page_num": 12},      # same page twice
            {"content": "Boil water for one minute.", "source": "guide", "domain": "water", "page_num": 0},
        ]))
        from core.library import search_all, wiki_lookup
        search_all._files.clear()
        self.wl_old = (wiki_lookup.WIKI_DIR, wiki_lookup.FULL_DB)
        wiki_lookup.WIKI_DIR = kb / "wikipedia"
        wiki_lookup.FULL_DB = kb / "none.sqlite"
        wiki_lookup._cache.update({"mtime": None, "titles": {}})

    def tearDown(self):
        from core.library import wiki_lookup
        wiki_lookup.WIKI_DIR, wiki_lookup.FULL_DB = self.wl_old
        wiki_lookup._cache.update({"mtime": None, "titles": {}})
        os.chdir(self.old)
        self.tmp.cleanup()

    def test_books_and_wikipedia_with_sources(self):
        from core.library.rag import KnowledgeBase
        from core.library.search_all import search_everything
        found = search_everything("poisonous plants", KnowledgeBase())
        books = found["book"]
        self.assertEqual(len(books), 1)                         # one per page
        b = books[0]
        self.assertEqual(b["source"], "Edible Wild Plants, p. 12")
        self.assertTrue(b["image"].endswith("ediblewildplants031709mbp_p012.jpg"))
        self.assertTrue(b["path"].endswith("ediblewildplants031709mbp.pdf"))
        self.assertEqual([w["title"] for w in found["wikipedia"]][:1], ["Plant"])   # plural → Plant
        self.assertEqual(found["wikipedia"][0]["source"], "Wikipedia — Plant")

    def test_off_subject_passages_are_left_out(self):
        from core.library.rag import KnowledgeBase
        from core.library.search_all import search_books
        self.assertEqual(search_books("crysis", KnowledgeBase()), [])

    def test_empty(self):
        from core.library.search_all import search_everything
        self.assertEqual(search_everything("  "), {"book": [], "note": [], "wikipedia": []})


if __name__ == "__main__":
    unittest.main()
