"""The debug log shows what both models said, not just how long they took."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from core.answers import tracer as tr
from core.answers.pipeline import _facts_note
from core.ai.librarian import Facts


class TestTracerText(unittest.TestCase):
    def test_log_shows_each_models_words(self):
        t = tr.QueryTrace(query_preview="what about hemlock", tab_id="survival", timestamp=0,
                          brief_text="SEARCH hemlock identification | QUESTION how to tell hemlock",
                          librarian_text="- purple blotches on the stem [1]",
                          response_text=tr.short("Hemlock has purple blotches.\n" * 60, 600),
                          images=["herbs_p012.jpg"])
        self.assertLessEqual(len(t.response_text), 602)
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "traces.jsonl"
            log.write_text(json.dumps(t.to_dict()) + "\n", encoding="utf-8")
            out = io.StringIO()
            with mock.patch.object(tr, "TRACE_LOG_PATH", log), redirect_stdout(out):
                tr.print_recent(5)
        text = out.getvalue()
        self.assertIn("speaker asked the librarian: SEARCH hemlock", text)
        self.assertIn("librarian found: - purple blotches", text)
        self.assertIn("reply: Hemlock has purple blotches.", text)
        self.assertIn("pictures: herbs_p012.jpg", text)

    def test_librarian_note(self):
        self.assertEqual(_facts_note(Facts("", False)), "NOT FOUND")
        self.assertEqual(_facts_note(Facts("", False, failed=True)), "(couldn't be asked)")
        self.assertEqual(_facts_note(Facts("- a [1]\n- b [2]", True)), "- a [1] - b [2]")


if __name__ == "__main__":
    unittest.main()
