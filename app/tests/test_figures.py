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


class TestRightPicture(unittest.TestCase):
    """Owner: "if I ask for a picture of a plant or process it doesn't give the right one"."""

    def setUp(self):
        import fitz
        self.tmp = tempfile.TemporaryDirectory()
        self.old = os.getcwd()
        os.chdir(self.tmp.name)
        kb = Path("knowledge_base")
        (kb / "plants_temperate" / "_images").mkdir(parents=True)
        doc = fitz.open()

        def text_page(body):
            doc.new_page().insert_textbox(fitz.Rect(50, 50, 550, 800), body, fontsize=9)

        def figure(caption):
            pg = doc.new_page()
            for i in range(50):
                pg.draw_line((60 + i * 8, 100), (60 + i * 8, 400))
            pg.insert_text((60, 430), caption)

        text_page(TEXT)                                                       # 1
        text_page(TEXT)                                                       # 2
        text_page("Water hemlock is the most poisonous plant in North America. " * 12)  # 3 text only
        figure("Fig. 9-5. Water hemlock, showing the purple-blotched stem.")  # 4
        figure("Fig. 9-6. Hemlock tree (Tsuga canadensis).")                   # 5
        figure("Figure 7. Bow drill: bow, spindle, socket and fireboard.")     # 6
        text_page(TEXT)                                                       # 7
        doc.save(str(kb / "plants_temperate" / "fieldguide.pdf"))
        for i in range(1, 8):
            (kb / "plants_temperate" / "_images" / f"fieldguide_p{i:03d}.jpg").write_bytes(b"jpg")
        doc.close()
        figures.build(kb, progress=lambda *_: None)

    def tearDown(self):
        os.chdir(self.old)
        self.tmp.cleanup()

    def test_the_page_that_shows_it(self):
        found = figures.find_pictures("can you show me a picture of water hemlock for reference")
        self.assertEqual(found[0]["page"], 4)                  # the drawing, not the text page (3)
        self.assertIn("Water hemlock", found[0]["shows"])
        self.assertEqual(figures.find_pictures("show me a diagram of a bow drill")[0]["page"], 6)
        self.assertEqual(figures.find_pictures("picture of a crysis")[:1], [])

    def test_answer_shows_it_and_the_speaker_knows(self):
        from core.ai.llm import LLMEngine
        from core.app.config import Config
        from core.answers.pipeline import QueryPipeline
        from core.library.rag import KnowledgeBase
        from core.you.memory import Memory
        from core.you.tabs import TabManager

        class Fake(LLMEngine):
            def complete(self, *a, **k):
                return "NOT FOUND"
        pipe = QueryPipeline(Memory(), KnowledgeBase(), Fake(Config()))
        tabs = TabManager()
        for tab, q in (("survival", "can you show me a picture of water hemlock"),
                       ("prometheus", "show me a picture of water hemlock")):
            out = pipe.prepare_knowledge(tabs.get_tab(tab), q, pipe.route(q, tab))
            self.assertTrue(out.images and out.images[0].endswith("fieldguide_p004.jpg"), tab)
            self.assertIn("PICTURE shown under your reply", out.full_prompt)
            self.assertIn("Water hemlock", out.full_prompt)
        # Owner: instructions and plants should show their pictures without asking
        for q, page in (("how do I make a bow drill", "p006"), ("what is water hemlock", "p004")):
            out = pipe.prepare_knowledge(tabs.get_tab("survival"), q, pipe.route(q, "survival"))
            self.assertTrue(any(i.endswith(f"fieldguide_{page}.jpg") for i in out.images), q)
            self.assertIn("PICTURE shown under your reply", out.full_prompt)
        out = pipe.prepare_knowledge(tabs.get_tab("survival"), "how do I purify water",
                                     pipe.route("how do I purify water", "survival"))
        self.assertEqual(out.images, [])                                     # nothing captioned so
        out = pipe.prepare_knowledge(tabs.get_tab("survival"), "show me a picture of a crysis",
                                     pipe.route("show me a picture of a crysis", "survival"))
        self.assertEqual(out.images, [])
        self.assertIn("no picture of this", out.full_prompt)


if __name__ == "__main__":
    unittest.main()
