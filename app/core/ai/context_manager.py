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

    def messages_for(self, tab: Tab, reserve_chars: int = 0) -> List[Dict]:
        """
        The messages to send now, never waiting on a summary.

        Step 1: the newest MAX_MESSAGES (half on low power), plus the summary
        Step 2: and no more than fits the model's window. 20 messages plus
                this question's library passages could pass 4096 tokens, and
                Ollama then quietly drops the START of the chat — the owner:
                "it doesn't remember the context". reserve_chars = what else
                goes in (instructions, passages); the reply's room is kept too.
        """
        cfg = self.llm.config
        limit = MAX_MESSAGES // 2 if getattr(cfg, "low_power_active", False) else MAX_MESSAGES
        msgs = tab.get_ollama_messages()
        head = [m for m in msgs[:1] if m["role"] == "system"]
        body = [{"role": m["role"], "content": m["content"]} for m in tab.history[-limit:]]
        # ~3.5 characters per token; keep the reply's tokens and a margin free
        budget = int((getattr(cfg, "context_window", 4096) - getattr(cfg, "max_tokens", 300) - 200) * 3.5)
        budget -= reserve_chars + sum(len(m["content"]) for m in head)
        kept, used = [], 0
        for m in reversed(body):                    # newest first
            if kept and used + len(m["content"]) > budget:
                break
            kept.append(m)
            used += len(m["content"])
        return head + list(reversed(kept))

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
        """Too many messages, or long ones filling half the model's window —
        the oldest get summarised so they aren't simply cut off."""
        chars = sum(len(m.get("content", "")) for m in tab.history)
        half_window = getattr(self.llm.config, "context_window", 4096) * 3.5 / 2
        return len(tab.history) > MAX_MESSAGES or (len(tab.history) > SUMMARIZE_OLDEST and chars > half_window)
