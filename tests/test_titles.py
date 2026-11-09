"""Readable book names instead of archive codes under answers."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core.library import titles


def _pdf(path: Path, title: str = ""):
    import fitz
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "Some text about joinery.")
    if title:
        doc.set_metadata({"title": title})
    doc.save(str(path))
    doc.close()


class TestTitles(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        kb = Path(self.tmp.name) / "knowledge_base"
        (kb / "build").mkdir(parents=True)
        (kb / "companion").mkdir()
        _pdf(kb / "build" / "practicalcarpen01radfgoog.pdf",
             "Practical carpentry; being a guide to the correct working and laying out of all kinds of work")
        _pdf(kb / "build" / "b32172321.pdf")                       # no title inside, code name
        (kb / "companion" / "psychology_and_meaning.md").write_text("# Psychology and Meaning\n\nText.")
        (kb / "build" / "Building with Straw Bales, A Practical Guide for the UK the Ireland "
                        "by Barbara Jones.txt").write_text("text")
        (kb / "build" / "README.md").write_text("# Folder placeholder")
        self.kb = kb
        self.out = kb / "titles.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_titles_from_inside_the_files(self):
        titles.build(self.kb, progress=lambda m: None)
        got = json.loads(self.out.read_text())
        self.assertEqual(got["practicalcarpen01radfgoog"], "Practical carpentry")
        self.assertEqual(got["psychology_and_meaning"], "Psychology and Meaning")
        self.assertEqual(got["building_with_straw_bales,_a_practical_guide_for_the_uk_the_ireland_by_barbara_jones"],
                         "Building with Straw Bales, A Practical Guide for the UK the Ireland")
        self.assertNotIn("b32172321", got)                         # a code, not a title
        self.assertNotIn("readme", got)

    def test_your_edits_are_kept(self):
        self.out.write_text(json.dumps({"practicalcarpen01radfgoog": "Radford's Carpentry"}))
        titles.build(self.kb, progress=lambda m: None)
        self.assertEqual(json.loads(self.out.read_text())["practicalcarpen01radfgoog"], "Radford's Carpentry")

    def test_answers_credit_the_title(self):
        from core.answers.confidence import ConfidenceScorer
        titles.build(self.kb, progress=lambda m: None)
        with mock.patch.object(titles, "TITLES_PATH", self.out):
            titles._cache["mtime"] = None
            label = ConfidenceScorer()._source_label("practicalcarpen01radfgoog", "build")
        self.assertEqual(label, "Practical carpentry")
        titles._cache["mtime"] = None


if __name__ == "__main__":
    unittest.main()
