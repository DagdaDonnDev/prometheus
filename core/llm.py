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
        """
        Check Ollama is answering.

        On Windows "localhost" can resolve to the IPv6 address first while
        Ollama only listens on 127.0.0.1 — if localhost fails, try 127.0.0.1
        and switch to it when it works.
        """
        self.last_error = ""
        for url in self._candidate_urls():
            try:
                r = requests.get(f"{url}/api/tags", timeout=3)
                if r.status_code == 200:
                    self.base_url = url
                    return True
                self.last_error = f"HTTP {r.status_code}"
            except requests.exceptions.ConnectionError:
                self.last_error = "nothing is listening there"
            except requests.exceptions.Timeout:
                self.last_error = "no answer within 3 seconds"
            except Exception as e:
                self.last_error = str(e)
        return False

    def _candidate_urls(self) -> List[str]:
        url = (self.config.ollama_url or "http://localhost:11434").rstrip("/")
        urls = [url]
        if "://localhost" in url:
            urls.append(url.replace("://localhost", "://127.0.0.1"))
        return urls

    def list_models(self) -> List[str]:
        """Names of the models pulled into Ollama (empty if unreachable)."""
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=3)
            if r.status_code == 200:
                return sorted(m["name"] for m in r.json().get("models", []))
        except Exception:
            pass
        return []

    @staticmethod
    def _has_model(installed: List[str], wanted: str) -> bool:
        """'llama3.2' matches 'llama3.2:latest'; 'llama3.2:3b' must match exactly."""
        if not wanted:
            return False
        if ":" in wanted:
            return wanted in installed
        return any(m.split(":")[0] == wanted for m in installed)

    def missing_models(self) -> List[str]:
        """Models the settings ask for that aren't pulled yet."""
        installed = self.list_models()
        wanted = {self.config.fast_model, self.config.companion_model}
        return sorted(m for m in wanted if m and not self._has_model(installed, m))

    def model_available(self) -> bool:
        """True if every model the settings use is pulled."""
        return not self.missing_models()

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
        model = self.config.model_for_tab(tab_id) if tab_id else self.config.fast_model
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

    def complete(
        self,
        system_prompt: str,
        prompt: str,
        tab_id: str = "",
        temperature: float = 0.2,
        max_tokens: int = 700,
        timeout: int = 90,
    ) -> str:
        """
        Blocking, non-streamed completion.
        Used by the Training Path, which needs the whole derivation
        before it can check it. Raises on connection or HTTP errors
        so the caller can fall back to the Knowledge Path.
        """
        model = self.config.model_for_tab(tab_id) if tab_id else self.config.fast_model
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": prompt},
            ],
            "stream": False,
            "options": {
                "num_predict":    max_tokens,
                "temperature":    temperature,
                "top_p":          0.9,
                "repeat_penalty": 1.1,
            },
        }
        r = requests.post(f"{self.base_url}/api/chat", json=payload, timeout=timeout)
        r.raise_for_status()
        return r.json().get("message", {}).get("content", "")

    def summarize(self, conversation_text: str) -> str:
        """
        Generate a summary of conversation history.
        Used for rolling context management.
        Blocking call (not streamed).
        Low temperature — factual compression, not creative.
        """
        try:
            payload = {
                "model": self.config.fast_model,
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
