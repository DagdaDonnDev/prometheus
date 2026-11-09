"""Only pages with a real picture are shown under answers (core/library/figures.py)."""

import os
import tempfile
import unittest
from pathlib import Path

from core.library import figures

TEXT = ("The joint is cut with a fine saw and pared to the line with a sharp chisel. " * 12).strip()


def _book(path: Path):
    """Six pages: dense text, text + drawing with caption, text, nearly blank, text, sparse page."""
    import fitz
    doc = fitz.open()

    def text_page(body):
        p = doc.new_page()
        p.insert_textbox(fitz.Rect(50, 50, 550, 800), body, fontsize=9)
        return p

    text_page(TEXT)                                         # 1 text
    p = doc.new_page()                                      # 2 drawing + caption
    for i in range(50):
        p.draw_line((60 + i * 8, 100), (60 + i * 8, 400))
    p.insert_text((60, 430), "Fig. 3 — a dovetail joint, seen from above.")
    text_page(TEXT)                                         # 3 text
    doc.new_page().insert_text((200, 300), "THE END")       # 4 nearly blank
    text_page(TEXT)                                         # 5 text
    text_page(" ".join(TEXT.split()[:30]))                  # 6 sparse: a short line under a picture
    doc.save(str(path))
    doc.close()


class TestFigures(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = os.getcwd()
        os.chdir(self.tmp.name)
        kb = Path("knowledge_base")
        (kb / "build" / "_images").mkdir(parents=True)
        _book(kb / "build" / "joinery.pdf")
        for n in range(1, 7):
            (kb / "build" / "_images" / f"joinery_p{n:03d}.jpg").write_bytes(b"jpg")
        self.kb = kb

    def tearDown(self):
        os.chdir(self.old)
        self.tmp.cleanup()

    def test_scan_finds_the_picture_pages(self):
        self.assertEqual(figures.scan_pdf(self.kb / "build" / "joinery.pdf"), {2, 6})

    def test_cover_is_not_a_figure(self):
        import fitz
        path = self.kb / "build" / "manual.pdf"
        doc = fitz.open()
        doc.new_page().insert_textbox(fitz.Rect(50, 50, 550, 800),
                                      " ".join(TEXT.split()[:30]), fontsize=9)   # sparse cover
        for _ in range(4):
            doc.new_page().insert_textbox(fitz.Rect(50, 50, 550, 800), TEXT, fontsize=9)
        doc.save(str(path))
        doc.close()
        self.assertEqual(figures.scan_pdf(path), set())

    def test_build_and_lookup(self):
        self.assertIsNone(figures.figure_pages("build", "joinery"))   # not scanned: old behaviour
        self.assertEqual(figures.build(self.kb, progress=lambda *_: None), 1)
        self.assertEqual(figures.figure_pages("build", "joinery"), [2, 6])

    def test_answers_show_only_figure_pages(self):
        from core.library.rag import KnowledgeBase
        kb = KnowledgeBase()
        img = lambda page, text="joint": kb._resolve_image(
            {"page_num": page, "domain": "build", "source": "joinery", "content": text})
        # before scanning: every page, as before
        self.assertIsNotNone(img(1))
        figures.build(self.kb, progress=lambda *_: None)
        self.assertIsNone(img(1))                                     # just text
        self.assertTrue(str(img(2)).endswith("joinery_p002.jpg"))
        # text that points to a figure on the next page gets that page
        self.assertTrue(str(img(1, "as shown in Fig. 3 below")).endswith("joinery_p002.jpg"))

    def test_picture_requests(self):
        for q in ("do you have a picture of hemlock", "what does water hemlock look like",
                  "show me a diagram of a bow drill", "how do I identify chanterelles",
                  "how would i identify poisounous plants", "do you have a reference image of hemlock"):
            self.assertTrue(figures.wants_picture(q), q)
        for q in ("how do I cut a dovetail", "what is hemlock", "tell me about knots"):
            self.assertFalse(figures.wants_picture(q), q)

    def test_picture_request_puts_passages_with_figures_first(self):
        from core.library.rag import KnowledgeBase
        kb = KnowledgeBase()
        kb.prompt_passages = 1
        plain = {"content": "Hemlock grows by streams and has a smooth stem.", "source": "a",
                 "domain": "survival"}
        pictured = {"content": "Hemlock leaves are finely divided, purple blotches on stem.",
                    "source": "b", "domain": "survival", "image_path": "x.jpg", "page_num": 4}
        kb._score_and_format("what does hemlock look like", [plain, pictured], False, 1)
        self.assertEqual(kb._last_images, ["x.jpg"])
        kb._score_and_format("where does hemlock grow", [plain, pictured], False, 1)
        self.assertEqual(kb._last_images, [])


if __name__ == "__main__":
    unittest.main()
