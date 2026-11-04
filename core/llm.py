"""
LLM Engine - Llama 3.2 3B via Ollama with token streaming.
Fully offline. Unlimited. No API keys.
"""

import requests
import json
from typing import Generator, List, Dict, Optional, Callable


# Temperature by intent — deterministic for safety-critical,
# warmer for conversation and reflection
INTENT_TEMPERATURE = {
    "emergency":  0.15,   # As deterministic as possible — follow the source
    "procedure":  0.25,   # Consistent steps
    "diagnose":   0.30,   # Some flexibility but grounded
    "identify":   0.25,   # Consistent identification
    "locate":     0.40,
    "explain":    0.55,
    "assess":     0.55,
    "plan":       0.60,
    "discuss":    0.80,   # Conversational, varied
    "reflect":    0.85,   # Warm, personal, never robotic
}

DEFAULT_TEMPERATURE = 0.65


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
        intent: str = "",
    ):
        """
        Stream tokens from the model.
        Uses companion_model for the prometheus tab,
        fast_model for everything else.
        Temperature varies by intent — lower for safety-critical,
        higher for conversation and reflection.
        """
        model = self.config.model_for_tab(tab_id) if tab_id else self.config.llm_model
        temperature = INTENT_TEMPERATURE.get(intent, DEFAULT_TEMPERATURE)

        try:
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt}
                ] + messages,
                "stream": True,
                "options": {
                    "num_predict": self.config.max_tokens,
                    "temperature": temperature,
                    "top_p":       0.9,
                    "repeat_penalty": 1.1,  # Reduce repetitive phrasing
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
        Low temperature — factual compression, not creative.
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
                    "temperature": 0.2,   # Very low — factual summary
                    "repeat_penalty": 1.1,
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
        """
        Build the full system prompt with all governance layers.

        Order matters for 3B models — most important context goes last,
        closest to where the model actually generates from.
        """
        parts = [tab_system]

        # Behavioural constraints next — anchors everything that follows
        if llm_bounds:
            parts.append(f"\n\nBEHAVIOURAL CONSTRAINTS:\n{llm_bounds}")

        # Retrieved knowledge — the primary content to work from
        if knowledge_context:
            parts.append(
                f"\n\nRetrieved knowledge — use as primary source:\n"
                f"{knowledge_context}"
            )

        # Source confidence guidance
        if confidence_note:
            parts.append(f"\n\nSource guidance:\n{confidence_note}")

        # User situation — injected close to generation point
        if user_context and user_context != "No user context yet.":
            parts.append(f"\n\nUser situation:\n{user_context}")

        # Response governance — last thing model reads before generating
        if decision_addendum:
            parts.append(f"\n\nRESPONSE GUIDANCE:\n{decision_addendum}")

        if not decision_addendum and not llm_bounds:
            parts.append(
                "\n\nBe concise. Match length to what's needed. "
                "Speak naturally. When uncertain, say so."
            )

        return "\n".join(parts)
