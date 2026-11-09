"""The full English Wikipedia build, on a small dump made the same way as the real one."""

import bz2
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core.library import wiki_full, wiki_index, wiki_lookup


def _page(pid, title, text, ns=0, redirect=""):
    red = f'<redirect title="{redirect}" />' if redirect else ""
    return (f"<page><title>{title}</title><ns>{ns}</ns><id>{pid}</id>{red}"
            f"<revision><text bytes=\"1\" xml:space=\"preserve\">{text}</text></revision></page>")


def make_dump(folder: Path, pages, per_stream=4):
    """A multistream dump: header stream, page streams, footer stream + its index."""
    dump, index = folder / "enwiki-test-pages-articles-multistream.xml.bz2", []
    with open(dump, "wb") as f:
        f.write(bz2.compress(b"<mediawiki><siteinfo><sitename>Wikipedia</sitename></siteinfo>"))
        for i in range(0, len(pages), per_stream):
            off = f.tell()
            chunk = pages[i:i + per_stream]
            f.write(bz2.compress("".join(p for _, _, p in chunk).encode()))
            index += [f"{off}:{pid}:{title}" for pid, title, _ in chunk]
        f.write(bz2.compress(b"</mediawiki>"))
    idx = folder / "enwiki-test-pages-articles-multistream-index.txt.bz2"
    idx.write_bytes(bz2.compress("\n".join(index).encode()))
    return dump, idx


BODY = " ".join(["Words about the subject."] * 20)


def sample_pages():
    pages = []
    pid = 1

    def add(title, text, **kw):
        nonlocal pid
        pages.append((pid, title, _page(pid, title, text, **kw)))
        pid += 1

    add("Titanfall 2", "'''Titanfall 2''' is a 2016 game. {{Infobox video game|x={{nested|y}}}} "
        "The pilot bonds with [[BT-7274]], a Titan. " + BODY +
        "\n== Plot ==\nCooper and BT fight the IMC. " + BODY +
        "\n== References ==\n{{reflist}} Lots of citations that shouldn't be kept.")
    add("BT-7274", "", redirect="Titanfall 2")
    add("Water", "Water is a liquid. [[Titanfall 2]] " + BODY)
    add("Mercury", "{{disambiguation}} Mercury may refer to: [[Mercury (planet)]]")
    add("Obscure village council", "A small council. " + BODY)
    add("Another stub", "A stub. " + BODY)
    add("Talk:Water", "talk page [[Water]] [[Water]] [[Water]]", ns=1)
    # Many pages link to Water, Mercury (disambig) and BT-7274 (→ Titanfall 2)
    for n in range(12):
        add(f"Linker {n}", f"See [[Water]], [[water|H2O]], [[Mercury]], [[BT-7274]] and "
            f"[[File:x.jpg|thumb]] and [[Category:Stuff]]. " + BODY)
    return pages


class TestFullBuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        cls.dump, cls.index = make_dump(root, sample_pages())
        cls.db = root / "kb" / "wikipedia_full.sqlite"
        cls.db.parent.mkdir()
        with mock.patch.object(wiki_full, "STREAMS_PER_JOB", 2), \
                mock.patch.object(wiki_full, "SKETCH_BITS", 16):
            cls.log = []
            cls.count = wiki_full.build(cls.dump, cls.index, cls.db, top=2, workers=1,
                                        progress=cls.log.append)

    @classmethod
    def tearDownClass(cls):
        wiki_lookup._cache.pop("db", None)
        cls.tmp.cleanup()

    def rows(self, sql, *a):
        import sqlite3
        db = sqlite3.connect(self.db)
        try:
            return db.execute(sql, a).fetchall()
        finally:
            db.close()

    def test_keeps_the_most_linked_to(self):
        keys = {k for (k,) in self.rows("SELECT key FROM pages")}
        self.assertIn("titanfall_2", keys)          # linked via its redirect BT-7274
        self.assertIn("water", keys)
        self.assertNotIn("mercury", keys)           # disambiguation pages are left out
        self.assertNotIn("obscure_village_council", keys)
        self.assertNotIn("talkwater", keys)         # not an article
        self.assertEqual(self.count, 2)

    def test_redirects_become_aliases(self):
        self.assertEqual(self.rows("SELECT target FROM aliases WHERE key='bt-7274'"), [("titanfall_2",)])

    def test_text_is_clean_and_reference_sections_dropped(self):
        [(body,)] = self.rows("SELECT body FROM pages WHERE key='titanfall_2'")
        self.assertIn("Cooper and BT fight the IMC", body)
        self.assertNotIn("{{", body)
        self.assertNotIn("Infobox", body)
        self.assertNotIn("citations", body)
        self.assertNotIn("'''", body)

    def test_full_text_search(self):
        hits = wiki_index.search("cooper imc", index_path=self.db)
        self.assertEqual(hits[0]["stem"], "titanfall_2")

    def test_chat_lookup_reads_the_database(self):
        with mock.patch.object(wiki_lookup, "FULL_DB", self.db):
            self._close_cached()
            found = wiki_lookup.find_articles("have you played Titanfall 2?")
            self.assertEqual(found[0][0], "Titanfall 2")
            via_redirect = wiki_lookup.find_articles("tell me about BT-7274")
            self.assertEqual(via_redirect[0][0], "Titanfall 2")
            self.assertIn("2016 game", wiki_lookup.lead(found[0][1], 30))
            self.assertEqual(wiki_lookup.article_count(), 2)
            res = wiki_lookup.search("titanfall")
            self.assertEqual(res[0]["title"], "Titanfall 2")
            text = wiki_lookup.read_article(Path(str(res[0]["path"])))
            self.assertTrue(text.startswith("# Titanfall 2"))
            self._close_cached()

    @staticmethod
    def _close_cached():
        db = wiki_lookup._cache.pop("db", None)
        if db is not None:
            db._db.close()

    def test_finished_file_replaces_the_building_one(self):
        self.assertTrue(self.db.exists())
        self.assertFalse(self.db.with_suffix(".building").exists())
        self.assertFalse(self.db.with_suffix(".chosen.npy").exists())


class TestParallelAndResume(unittest.TestCase):
    def test_parallel_build_matches_and_resume_skips_done_pieces(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            dump, index = make_dump(root, sample_pages())
            db = root / "w.sqlite"
            with mock.patch.object(wiki_full, "STREAMS_PER_JOB", 2), \
                    mock.patch.object(wiki_full, "SKETCH_BITS", 16):
                n = wiki_full.build(dump, index, db, top=3, workers=2, progress=lambda m: None)
                self.assertEqual(n, 3)
                # An interrupted run: pass 1 saved, some pieces stored → a rerun carries on
                os.replace(db, db.with_suffix(".building"))
                import numpy as np, sqlite3
                np.save(db.with_suffix(".chosen.npy"),
                        np.array(sorted(wiki_full._h64(k) for k in ("titanfall_2", "water", "another_stub")),
                                 dtype=np.uint64))
                log = []
                wiki_full.build(dump, index, db, top=3, workers=1, progress=log.append)
                self.assertTrue(any("Pass 1 already done" in m for m in log))
                self.assertTrue(any("Carrying on" in m for m in log))


if __name__ == "__main__":
    unittest.main()
