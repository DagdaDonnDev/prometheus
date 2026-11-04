"""
Context management - rolling summaries to defeat context window limits.
Effectively makes conversation memory unlimited.
"""

from typing import List, Dict
from core.tabs import Tab


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

    def should_summarize(self, tab: Tab) -> bool:
        return len(tab.history) > MAX_MESSAGES
