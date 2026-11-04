"""
LLM Engine - Llama 3.2 3B via Ollama with token streaming.
Fully offline. Unlimited. No API keys.
"""

import requests
import json
from typing import Generator, List, Dict, Optional, Callable


class LLMEngine:
    def __init__(self, config):
        self.config = config
        self.base_url = config.ollama_url

    def is_available(self) -> bool:
        """Check if Ollama is running."""
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=3)
            return r.status_code == 200
        except Exception:
            return False

    def model_available(self) -> bool:
        """Check if the configured model is pulled."""
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=3)
            if r.status_code == 200:
                models = [m["name"] for m in r.json().get("models", [])]
                model_base = self.config.llm_model.split(":")[0]
                return any(model_base in m for m in models)
        except Exception:
            pass
        return False

    def stream(
        self,
        messages: List[Dict],
        system_prompt: str,
        on_token: Callable[[str], None],
        on_done: Callable[[str], None],
        on_error: Callable[[str], None],
        tab_id: str = "",
    ):
        """
        Stream tokens from the model.
        Uses companion_model for the prometheus tab,
        fast_model for everything else.
        """
        model = self.config.model_for_tab(tab_id) if tab_id else self.config.llm_model

        try:
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt}
                ] + messages,
                "stream": True,
                "options": {
                    "num_predict": self.config.max_tokens,
                    "temperature": 0.7,
                    "top_p": 0.9,
                }
            }

            full_response = ""

            with requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                stream=True,
                timeout=120
            ) as response:

                if response.status_code != 200:
                    on_error(f"Ollama error: {response.status_code}")
                    return

                for line in response.iter_lines():
                    if line:
                        try:
                            data = json.loads(line)
                            token = data.get("message", {}).get("content", "")
                            if token:
                                full_response += token
                                on_token(token)

                            if data.get("done"):
                                on_done(full_response)
                                return

                        except json.JSONDecodeError:
                            continue

        except requests.exceptions.ConnectionError:
            on_error(
                "Cannot connect to Ollama. "
                "Please ensure Ollama is running: 'ollama serve'"
            )
        except Exception as e:
            on_error(f"Error: {str(e)}")

    def summarize(self, conversation_text: str) -> str:
        """
        Generate a summary of conversation history.
        Used for rolling context management.
        Blocking call (not streamed).
        """
        try:
            payload = {
                "model": self.config.llm_model,
                "messages": [{
                    "role": "user",
                    "content": (
                        "Summarize this conversation in 4-6 sentences. "
                        "Preserve all important facts, decisions made, "
                        "current situation and any critical information. "
                        "Be concise but complete:\n\n"
                        + conversation_text
                    )
                }],
                "stream": False,
                "options": {
                    "num_predict": 200,
                    "temperature": 0.3
                }
            }

            r = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=60
            )

            if r.status_code == 200:
                return r.json()["message"]["content"]

        except Exception:
            pass

        return ""

    def build_system_prompt(
        self,
        tab_system: str,
        user_context: str,
        knowledge_context: str,
        confidence_note: str = "",
        decision_addendum: str = "",
        llm_bounds: str = "",
    ) -> str:
        """Build the full system prompt with all governance layers."""

        parts = [tab_system]

        if user_context and user_context != "No user context yet.":
            parts.append(f"\n\nCurrent user situation:\n{user_context}")

        if knowledge_context:
            parts.append(
                f"\n\nRetrieved knowledge (use this as your primary source):\n"
                f"{knowledge_context}"
            )

        if confidence_note:
            parts.append(f"\n\nSource guidance:\n{confidence_note}")

        if decision_addendum:
            parts.append(f"\n\nRESPONSE GOVERNANCE:\n{decision_addendum}")

        if llm_bounds:
            parts.append(f"\n\nBEHAVIOURAL CONSTRAINTS:\n{llm_bounds}")

        if not decision_addendum and not llm_bounds:
            parts.append(
                "\n\nBe concise. 2-3 sentences for simple questions. "
                "Expand only when the situation genuinely requires detail. "
                "Speak naturally and warmly. "
                "When uncertain, say so clearly."
            )

        return "\n".join(parts)
