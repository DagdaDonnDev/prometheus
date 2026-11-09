"""
Context management - rolling summaries to defeat context window limits.
Effectively makes conversation memory unlimited.
"""

from typing import List, Dict
from core.you.tabs import Tab


MAX_MESSAGES = 20
SUMMARIZE_OLDEST = 10


class ContextManager:
    def __init__(self, llm_engine):
        self.llm = llm_engine

    def prepare_messages(self, tab: Tab) -> List[Dict]:
        """
        Returns messages ready for LLM, managing context window.
        Summarizes old messages when history grows too long.
        """
        if len(tab.history) <= MAX_MESSAGES:
            return tab.get_ollama_messages()

        # Need to summarize oldest messages
        to_summarize = tab.history[:SUMMARIZE_OLDEST]
        keep = tab.history[SUMMARIZE_OLDEST:]

        # Format conversation for summarization
        conv_text = "\n".join([
            f"{m['role'].upper()}: {m['content']}"
            for m in to_summarize
        ])

        # Combine with existing summary
        if tab.summary:
            conv_text = f"Previous summary: {tab.summary}\n\nContinuation:\n{conv_text}"

        # Generate new summary
        new_summary = self.llm.summarize(conv_text)

        if new_summary:
            tab.summary = new_summary
            tab.history = keep
            # Save is handled by caller

        return tab.get_ollama_messages()

    # ── Non-blocking versions (the window uses these) ──────────────────────
    # prepare_messages() above calls the model to summarise — seconds, or
    # many seconds on a slow computer — and the window used to call it on
    # its own thread, freezing until it finished.

    def messages_for(self, tab: Tab) -> List[Dict]:
        """The messages to send now, never waiting on a summary: if the chat
        is long and its summary isn't ready yet, just the newest MAX_MESSAGES."""
        # Low power: half the history (less to read on a processor)
        limit = MAX_MESSAGES // 2 if getattr(self.llm.config, "low_power_active", False) else MAX_MESSAGES
        msgs = tab.get_ollama_messages()
        if len(tab.history) <= limit:
            return msgs
        head = [m for m in msgs[:1] if m["role"] == "system"]
        return head + [{"role": m["role"], "content": m["content"]} for m in tab.history[-limit:]]

    def summarise_job(self, tab: Tab):
        """
        Step 1 (window thread): what to summarise — (the oldest messages, text).
        Step 2 (background thread): llm.summarize(text).
        Step 3 (window thread): apply_summary().
        """
        old = tab.history[:SUMMARIZE_OLDEST]
        text = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in old)
        if tab.summary:
            text = f"Previous summary: {tab.summary}\n\nContinuation:\n{text}"
        return old, text

    @staticmethod
    def apply_summary(tab: Tab, summarised: List[Dict], new_summary: str) -> bool:
        """Swap the summarised messages for the summary — only if they're
        still at the start of this chat (it may have changed meanwhile)."""
        n = len(summarised)
        if not new_summary or n == 0 or len(tab.history) < n or \
                any(a is not b for a, b in zip(tab.history[:n], summarised)):
            return False
        tab.summary = new_summary
        tab.history = tab.history[n:]
        return True

    def should_summarize(self, tab: Tab) -> bool:
        return len(tab.history) > MAX_MESSAGES
