"""Requests start the same as last time, so Ollama only reads what's new."""

import unittest
from unittest import mock

from core.answers.pipeline import QueryPipeline, with_turn_context
from core.ai.context_manager import ContextManager, MAX_MESSAGES
from core.ai.llm import LLMEngine
from core.app.config import Config
from core.library.rag import KnowledgeBase
from core.you.memory import Memory
from core.you.tabs import Tab


def _flat(system, messages):
    """Roughly what the model reads, in order."""
    return "\n".join([system] + [f"{m['role']}: {m['content']}" for m in messages])


def _shared(a, b):
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


class TestPromptCache(unittest.TestCase):
    def setUp(self):
        llm = LLMEngine(Config())
        llm.config.two_models = False
        self.pipe = QueryPipeline(Memory(), KnowledgeBase(), llm)
        self.cm = ContextManager(llm)
        self.tab = Tab(id="prometheus", name="Chat", icon="", domains=[], system_prompt="")

    def request(self, text):
        self.tab.add_message("user", text)
        with mock.patch("core.library.wiki_lookup.find_articles", return_value=[]):
            out = self.pipe.prepare_knowledge(self.tab, text, self.pipe.route(text, "prometheus"))
        msgs = with_turn_context(self.cm.messages_for(self.tab), out.turn_context)
        self.tab.add_message("assistant", f"reply to {text}")
        return _flat(out.system_prompt, msgs), out

    def test_next_request_starts_like_the_last_one(self):
        # A long chat, then two more messages with different moods
        for i in range(6):
            self.request(f"tell me about thing number {i}")
        first, _ = self.request("ugh that's wrong, stop")         # annoyed
        second, out = self.request("thanks, that's lovely!!")    # excited
        shared = _shared(first, second)
        # Everything up to the previous message is reused; only the end is new
        self.assertIn("tell me about thing number 5", second[:shared])
        self.assertGreater(shared / len(second), 0.6)
        # The fixed instructions don't carry the tone; the newest message does
        self.assertNotIn("Right now:", out.system_prompt)
        self.assertIn("Right now:", second.splitlines()[-1] + second[-400:])

    def test_saved_history_keeps_only_what_they_typed(self):
        self.request("hello there")
        self.assertEqual(self.tab.history[0]["content"], "hello there")

    def test_turn_context_goes_on_the_newest_message_only(self):
        msgs = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"},
                {"role": "user", "content": "c"}]
        out = with_turn_context(msgs, "FACTS")
        self.assertEqual(out[:2], msgs[:2])
        self.assertTrue(out[2]["content"].startswith("[For this reply"))
        self.assertTrue(out[2]["content"].endswith("[Their message]\nc"))
        self.assertEqual(msgs[2]["content"], "c")                    # original untouched


class TestSummaryOffTheWindowThread(unittest.TestCase):
    def setUp(self):
        self.cm = ContextManager(LLMEngine(Config()))
        self.tab = Tab(id="t", name="T", icon="", domains=[], system_prompt="")
        for i in range(MAX_MESSAGES + 4):
            self.tab.add_message("user" if i % 2 == 0 else "assistant", f"m{i}")

    def test_long_chat_sends_the_newest_without_waiting(self):
        with mock.patch.object(self.cm.llm, "summarize", side_effect=AssertionError("blocked")):
            msgs = self.cm.messages_for(self.tab)
        self.assertEqual(len(msgs), MAX_MESSAGES)
        self.assertEqual(msgs[-1]["content"], f"m{MAX_MESSAGES + 3}")

    def test_summary_applied_only_if_the_chat_still_starts_the_same(self):
        old, text = self.cm.summarise_job(self.tab)
        self.assertIn("m0", text)
        self.assertTrue(self.cm.apply_summary(self.tab, old, "earlier: m0…m9"))
        self.assertEqual(self.tab.summary, "earlier: m0…m9")
        self.assertEqual(self.tab.history[0]["content"], "m10")
        # The chat was cleared meanwhile → nothing applied
        old2, _ = self.cm.summarise_job(self.tab)
        self.tab.history = []
        self.assertFalse(self.cm.apply_summary(self.tab, old2, "x"))


class TestHistoryFitsTheWindow(unittest.TestCase):
    """Owner: "memory is a huge issue" — a full window cut the start of the chat."""

    def test_newest_kept_within_the_window(self):
        from core.ai.context_manager import ContextManager
        from core.ai.llm import LLMEngine
        from core.app.config import Config
        from core.you.tabs import Tab
        cm = ContextManager(LLMEngine(Config()))
        tab = Tab(id="t", name="t", icon="", domains=[], system_prompt="")
        for i in range(10):
            tab.history += [{"role": "user", "content": f"question {i} " + "x" * 50},
                            {"role": "assistant", "content": f"answer {i} " + "y" * 1200}]
        msgs = cm.messages_for(tab, reserve_chars=4000)
        total = sum(len(m["content"]) for m in msgs) + 4000
        self.assertLessEqual(total, (4096 - 300 - 200) * 3.5)
        self.assertTrue(msgs[-1]["content"].startswith("answer 9"))            # newest kept
        self.assertTrue(cm.should_summarize(tab))                              # older ones get summarised


if __name__ == "__main__":
    unittest.main()
