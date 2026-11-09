"""Separate chats per tab: new chat isolation, switching, search, saving."""

import unittest

from core.you.tabs import Tab, TabManager


def _tab():
    return Tab(id="prometheus", name="Chat", icon="", domains=[], system_prompt="")


class TestChats(unittest.TestCase):
    def test_new_chat_starts_empty(self):
        # Step 1: talk in one chat; Step 2: start a new one — nothing carries over
        t = _tab()
        t.add_message("user", "Tell me about Inception")
        t.add_message("assistant", "A film about dreams.")
        first = t.chat_id
        t.new_chat()
        self.assertEqual(t.history, [])
        self.assertEqual(t.get_ollama_messages(), [])
        self.assertEqual(len(t.chats), 1)
        self.assertEqual(t.chats[0]["id"], first)
        self.assertEqual(t.chats[0]["title"], "Tell me about Inception")

    def test_empty_chat_is_not_saved(self):
        t = _tab()
        t.new_chat()
        t.new_chat()
        self.assertEqual(t.chats, [])

    def test_open_switches_and_keeps_both(self):
        t = _tab()
        t.add_message("user", "first chat")
        a = t.chat_id
        t.new_chat()
        t.add_message("user", "second chat")
        b = t.chat_id
        self.assertTrue(t.open_chat(a))
        self.assertEqual(t.history[0]["content"], "first chat")
        self.assertEqual([c["id"] for c in t.chats], [b])
        self.assertFalse(t.open_chat("missing"))
        ids = {c["id"] for c in t.all_chats()}
        self.assertEqual(ids, {a, b})
        self.assertEqual([c["id"] for c in t.all_chats() if c["current"]], [a])

    def test_delete_and_rename(self):
        t = _tab()
        t.add_message("user", "keep me")
        a = t.chat_id
        t.new_chat()
        t.add_message("user", "delete me")
        t.rename_chat(a, "  Kept  ")
        self.assertEqual(t.chats[0]["title"], "Kept")
        t.delete_chat(t.chat_id)                 # the current one
        self.assertEqual(t.history, [])
        self.assertEqual([c["id"] for c in t.all_chats()], [a])
        t.delete_chat(a)
        self.assertEqual(t.all_chats(), [])

    def test_search_matches_words_in_messages(self):
        t = _tab()
        t.add_message("user", "how do I purify water")
        t.new_chat()
        t.add_message("user", "favourite films")
        t.add_message("assistant", "Inception is a good one")
        self.assertEqual(len(t.all_chats("inception")), 1)
        self.assertEqual(len(t.all_chats("purify WATER")), 1)
        self.assertEqual(t.all_chats("purify films"), [])
        self.assertEqual(len(t.all_chats("")), 2)

    def test_round_trip(self):
        t = _tab()
        t.add_message("user", "one")
        t.new_chat()
        t.add_message("user", "two")
        back = Tab.from_dict(t.to_dict())
        self.assertEqual(back.chat_id, t.chat_id)
        self.assertEqual(back.chat_title, "two")
        self.assertEqual(back.chats, t.chats)

    def test_clear_tab(self):
        m = TabManager.__new__(TabManager)
        t = _tab()
        m.tabs = [t]
        m.save = lambda: None
        t.add_message("user", "old")
        t.new_chat()
        t.add_message("user", "current")
        m.clear_tab("prometheus")
        self.assertEqual(t.history, [])
        self.assertEqual(t.chat_title, "")
        self.assertEqual(len(t.chats), 1)
        m.clear_tab("prometheus", every_chat=True)
        self.assertEqual(t.chats, [])


if __name__ == "__main__":
    unittest.main()
