"""Library search: word index + meaning search, ranked by how well a passage matches."""

import json
import os
import tempfile
import unittest
from pathlib import Path

FILLER = ("The field manual covers many topics for people living outdoors in hard times. " * 6).strip()

CHUNKS = [
    # A well-graded manual that only mentions ash in passing
    {"content": FILLER + " Keep the fire's ash pit clean and dry.", "source": "fm_survival",
     "domain": "survival", "page_num": 40},
    # The passage that actually answers "how do I make lye from wood ash"
    {"content": "Step 1 Making Lye from Wood Ash. Fill a barrel with hardwood ash, pour rainwater "
                "over it slowly and collect the brown liquid that drips out: that is lye. " + FILLER,
     "source": "soap_guide", "domain": "soap_making", "page_num": 0},
    {"content": "Water hemlock has purple blotches on a hollow stem and grows by streams. " + FILLER,
     "source": "plants_book", "domain": "plants_temperate", "page_num": 12},
    {"content": "Wikipedia text that must never be in the book index.", "source": "w",
     "domain": "wikipedia", "page_num": 0},
]


class TestLibraryIndex(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = os.getcwd()
        os.chdir(self.tmp.name)
        Path("memory").mkdir()
        Path("memory/chunks_fallback.json").write_text(json.dumps(CHUNKS))

    def tearDown(self):
        os.chdir(self.old)
        self.tmp.cleanup()

    def test_build_and_search(self):
        from core.library.library_index import LibraryIndex
        idx = LibraryIndex()
        self.assertFalse(idx.fresh())
        self.assertEqual(idx.build_from_file(), 3)                     # Wikipedia left out
        self.assertTrue(idx.fresh())
        hits = idx.search("How do I make lye from wood ash?")
        self.assertEqual(hits[0]["source"], "soap_guide")
        self.assertEqual(idx.search("hemlocks")[0]["source"], "plants_book")   # word stems
        self.assertEqual(idx.search("lye", domains=["survival"]), [])
        self.assertEqual(len(idx.in_domain("soap_making")), 1)

    def test_stale_after_the_library_changes(self):
        import time
        from core.library.library_index import LibraryIndex
        idx = LibraryIndex()
        idx.build_from_file()
        time.sleep(1.1)
        Path("memory/chunks_fallback.json").write_text(json.dumps(CHUNKS[:2]))
        self.assertFalse(idx.fresh())

    def test_fuse(self):
        from core.library.library_index import fuse
        a = [{"content": "one"}, {"content": "two"}, {"content": "three"}]
        b = [{"content": "three"}, {"content": "four"}]
        out = fuse(a, b)
        self.assertEqual(out[0]["content"], "three")                   # high in both
        self.assertEqual(out[0]["relevance"], 1.0)
        self.assertEqual({r["content"] for r in out}, {"one", "two", "three", "four"})

    def test_knowledge_base_uses_the_index(self):
        from core.library.rag import KnowledgeBase
        kb = KnowledgeBase()
        self.assertTrue(kb._fallback_chunks)            # no index yet: chunks read into memory
        self.assertTrue(kb.ensure_index())
        self.assertEqual(kb._fallback_chunks, [])       # …and let go once the index is built
        kb2 = KnowledgeBase()
        self.assertEqual(kb2._fallback_chunks, [])      # fresh index: never read at all
        self.assertEqual(kb2.chunks_in_domain("plants_temperate")[0]["source"], "plants_book")
        found = kb2._search_domains("how do I make lye from wood ash", ["survival", "soap_making"], 2)
        self.assertEqual(found[0]["source"], "soap_guide")

    def test_best_match_beats_best_graded_book(self):
        # The survival manual is graded higher than the soap guide, but only
        # the soap guide answers the question — it must be the one used
        from core.library.rag import KnowledgeBase
        KnowledgeBase().ensure_index()
        kb = KnowledgeBase()
        raw = [{**CHUNKS[0], "relevance": 1.0}, {**CHUNKS[1], "relevance": 0.9}]
        kb._score_and_format("how do I make lye from wood ash", raw, False, 2)
        self.assertEqual(kb._last_used_chunks[0]["source"], "soap_guide")


class TestSpeed(unittest.TestCase):
    """A library the size of the owner's (~25k passages): searches stay quick."""

    def test_search_time(self):
        import random
        import time
        from core.library.library_index import LibraryIndex
        rnd = random.Random(1)
        vocab = [f"word{i}" for i in range(4000)] + ["lye", "ash", "hemlock", "shelter", "water"]
        with tempfile.TemporaryDirectory() as d:
            idx = LibraryIndex(Path(d) / "lib.sqlite")
            chunks = ({"content": " ".join(rnd.choice(vocab) for _ in range(400)),
                       "source": f"b{i % 60}", "domain": f"d{i % 20}", "page_num": i}
                      for i in range(25000))
            started = time.time()
            idx.build(chunks, "test")
            build_s = time.time() - started
            started = time.time()
            for q in ("how do I make lye from wood ash", "water hemlock", "shelter"):
                self.assertTrue(idx.search(q, [f"d{i}" for i in range(10)], 12))
            per_search = (time.time() - started) / 3
        print(f"\n  25k passages: built in {build_s:.1f} s, {per_search * 1000:.0f} ms per search")
        self.assertLess(per_search, 0.5)


if __name__ == "__main__":
    unittest.main()
