"""tools/bench.py — the real-model question run (tested here with stand-in models)."""

import os
import unittest
from pathlib import Path
from unittest import mock


class TestBench(unittest.TestCase):
    def test_checks(self):
        from tools import bench
        ok = {"reply": "Boil it for a full minute.", "pictures": []}
        self.assertEqual(bench.check(ok, ["boil"], [], False, "Prometheus", ""), [])
        bad = {"reply": "Source: fm_3-05.70 says [1] see https://example.com", "pictures": []}
        problems = bench.check(bad, ["boil"], [], True, "Prometheus", "")
        self.assertTrue(any("mentions none of" in p for p in problems))
        self.assertTrue(any('"source:"' in p for p in problems))
        self.assertTrue(any("no picture" in p for p in problems))
        name = {"reply": "I'm Confuscious, an offline companion.", "pictures": []}
        self.assertEqual(bench.check(name, ["{name}"], [], False, "Confuscious", ""), [])

    def test_fresh_tabs_never_touch_your_chats(self):
        from tools import bench
        from core.you.tabs import DEFAULT_TABS
        tab = bench.fresh_tab("survival")
        tab.add_message("user", "hi")
        self.assertNotIn({"role": "user", "content": "hi"},
                         [m for t in DEFAULT_TABS if t.id == "survival" for m in t.history])
        self.assertTrue(bench.fresh_tab("entertainment").custom)

    def test_quick_run_writes_a_report(self):
        import core.ai.llm as L
        from core.ai import ollama_local
        from tools import bench

        def stream(self, messages, system_prompt, on_token, on_done, on_error, **k):
            on_token("Boil water for one minute.")
            on_done("Boil water for one minute.")
        before = set(Path("logs").glob("bench_*.md")) if Path("logs").exists() else set()
        with mock.patch.object(ollama_local, "start", lambda wait=0: False), \
                mock.patch.object(ollama_local, "stop", lambda: None), \
                mock.patch.multiple(L.LLMEngine, is_available=lambda self: True,
                                    missing_models=lambda self: [], warm_up=lambda self, *a, **k: True,
                                    complete=lambda self, *a, **k: "NOT FOUND", stream=stream), \
                mock.patch("builtins.print"):
            self.assertEqual(bench.main(["--quick"]), 0)
        new = set(Path("logs").glob("bench_*.md")) - before
        self.assertEqual(len(new), 1)
        text = new.pop().read_text(encoding="utf-8")
        self.addCleanup(lambda: [p.unlink() for p in set(Path("logs").glob("bench_*.md")) - before])
        self.assertIn("replies passed", text)
        self.assertIn("how do I purify water", text)


if __name__ == "__main__":
    unittest.main()
