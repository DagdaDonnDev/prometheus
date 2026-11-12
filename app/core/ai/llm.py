"""
LLM Engine — any Ollama model (default LFM2.5 1.2B Instruct), token streaming.
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
    "crisis":     0.40,   # Calm and steady — not robotic, not loose
    # Chat tab, by the tone read from their message (core/ai/tone.py)
    "chat_annoyed": 0.35,  # stick to the point, no flourishes
    "chat_low":     0.50,
    "chat_curious": 0.55,
    "chat_neutral": 0.65,
    "chat_excited": 0.80,
}

DEFAULT_TEMPERATURE = 0.65

# Step-by-step and explaining answers need room: 300 tokens cut instructions
# off mid-step. Chat stays short (and quick).
LONG_INTENTS = {"procedure", "plan", "explain", "diagnose", "assess", "identify", "emergency"}
THINK_TOKENS = 1200          # room for the reasoning before the answer
CUT_SHORT_NOTE = "\n\n*(That's where I had to stop — say \"go on\" for the rest.)*"


def _repeat_point(text: str, seen: set, checked: list) -> Optional[int]:
    """
    Where a repeated line starts in `text` (None if no line repeats). Lines
    are compared without their numbering ("4. Use the sun…" = "5. Use the
    sun…"); only lines of 30+ characters count, so "- Wear gloves." twice
    is fine.
    """
    import re
    start = checked[0]
    end = text.rfind("\n")
    pos = start
    for line in text[start:end].split("\n"):
        key = re.sub(r"^[\W\d]*(?:step\s*\d+\W*)?", "", line.lower())
        key = " ".join(key.split()).rstrip(" .:;,")
        if len(key) >= 30:
            if key in seen:
                return pos
            seen.add(key)
        pos += len(line) + 1
    return None


def fast_local_url(url: str) -> str:
    """
    "localhost" → "127.0.0.1".

    On Windows, Python tries localhost's IPv6 address (::1) first, but
    Ollama only listens on IPv4 — Windows then waits about 2 seconds
    before falling back. That was added to EVERY request (the ~2.4 s
    wait before each reply, and the slow Settings window).
    """
    return (url or "http://localhost:11434").rstrip("/").replace("://localhost", "://127.0.0.1")


def _thinking_off(model: str) -> dict:
    """
    Qwen3 and other "thinking" models write a hidden <think> essay before
    answering unless told not to — wasted time here. Only those models get
    the switch (Ollama rejects it for models that can't think).
    """
    m = (model or "").lower()
    return {"think": False} if any(k in m for k in ("qwen3", "deepseek-r1", "qwq", "magistral")) else {}


def strip_thinking(text: str) -> str:
    """Remove a <think>…</think> block if a model wrote one anyway."""
    import re
    return re.sub(r"<think>.*?</think>\s*", "", text, flags=re.S).lstrip()


class LLMEngine:
    def __init__(self, config):
        self.config = config
        self.base_url = config.ollama_url
        self.last_stats: Dict = {}     # Ollama's timing for the last streamed reply
        self.last_complete_stats: Dict = {}   # …and for the last complete() call

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

    @property
    def base_url(self) -> str:
        return self._base_url

    @base_url.setter
    def base_url(self, url: str):
        self._base_url = fast_local_url(url)

    def _candidate_urls(self) -> List[str]:
        """
        Prometheus's own Ollama first (models in prometheus/models), then
        127.0.0.1 (fast on Windows), then the address exactly as typed.
        """
        from core.ai import ollama_local
        own = ollama_local.active_url()
        typed = (self.config.ollama_url or "http://localhost:11434").rstrip("/")
        fast = fast_local_url(typed)
        urls = [fast] if fast == typed else [fast, typed]
        return ([own] if own else []) + [u for u in urls if u != own]

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
        wanted = wanted.lower()
        installed = [m.lower() for m in installed]
        if ":" in wanted:
            return wanted in installed
        return any(m.split(":")[0] == wanted for m in installed)

    def missing_models(self) -> List[str]:
        """Models the settings ask for that aren't pulled yet."""
        installed = self.list_models()
        wanted = {self.config.speaker_model}
        if self.config.two_models:
            wanted.add(self.config.librarian_model)
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
        model: str = "",
        on_thinking: Optional[Callable[[], None]] = None,
    ):
        """
        Stream tokens from the speaker (the model that talks to you).
        Temperature varies by intent — lower for safety-critical,
        higher for conversation and reflection.
        """
        model = model or self.config.model_for_tab(tab_id)
        temperature = INTENT_TEMPERATURE.get(intent, DEFAULT_TEMPERATURE)
        in_think = False      # inside a <think> block a model wrote anyway
        think = self.thinks(model, intent)
        told_thinking = False
        seen_lines: set = set()      # finished lines so far (loop guard)
        checked = [0]                # how far full_response has been checked

        try:
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt}
                ] + messages,
                "stream": True,
                "keep_alive": self.config.keep_alive,
                **({"think": True} if think else _thinking_off(model)),
                "options": {
                    "num_ctx":     self.config.context_window,
                    # thinking uses up reply tokens too — give it room
                    "num_predict": self.reply_tokens(intent) + (THINK_TOKENS if think else 0),
                    "temperature": temperature,
                    "top_p":       0.9,
                    "repeat_penalty": 1.1,  # Reduce repetitive phrasing
                    "repeat_last_n": 256,   # …over whole steps, not just the last 64 tokens
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
                            if not told_thinking and data.get("message", {}).get("thinking"):
                                told_thinking = True       # say it's thinking, once
                                if on_thinking:
                                    on_thinking()
                            token = data.get("message", {}).get("content", "")
                            # Hide a <think>…</think> block if one comes through anyway
                            if token and (in_think or ("<think>" in token and not full_response.strip())):
                                in_think = "</think>" not in token
                                token = token.split("</think>", 1)[1].lstrip() if "</think>" in token else ""
                            if token:
                                full_response += token
                                on_token(token)
                                # Stuck in a loop? The bench caught the same step
                                # three times over ("Use the position of the sun…").
                                # A finished line said before → stop there.
                                if "\n" in token:
                                    cut = _repeat_point(full_response, seen_lines, checked)
                                    checked[0] = full_response.rfind("\n") + 1
                                    if cut is not None:
                                        full_response = full_response[:cut].rstrip()
                                        on_done(full_response)
                                        return

                            if data.get("done"):
                                # Hit the length limit mid-reply: say so, so it
                                # doesn't just stop mid-step ("go on" continues)
                                if data.get("done_reason") == "length" and full_response.strip():
                                    note = CUT_SHORT_NOTE
                                    full_response += note
                                    on_token(note)
                                # Ollama reports where the time went (nanoseconds)
                                ns = lambda k: int(data.get(k, 0) or 0) // 1_000_000
                                self.last_stats = {
                                    "load_ms":        ns("load_duration"),
                                    "prompt_tokens":  int(data.get("prompt_eval_count", 0) or 0),
                                    "prompt_eval_ms": ns("prompt_eval_duration"),
                                    "gen_tokens":     int(data.get("eval_count", 0) or 0),
                                    "gen_ms":         ns("eval_duration"),
                                }
                                self._note_load(model, self.last_stats["load_ms"])
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

    def warm_up(self, system_prompt: str = "", tab_id: str = "prometheus", model: str = ""):
        """
        Load the model and read the companion prompt once, at startup, so the
        first real message doesn't pay for it. Ollama keeps the prompt it just
        read, so a message that starts with the same text skips re-reading it.
        Blocking — run it on a background thread.
        """
        model = model or self.config.model_for_tab(tab_id)
        try:
            requests.post(f"{self.base_url}/api/chat", json={
                "model": model,
                **_thinking_off(model),
                "messages": ([{"role": "system", "content": system_prompt}] if system_prompt else [])
                            + [{"role": "user", "content": "hi"}],
                "stream": False,
                "keep_alive": self.config.keep_alive,
                "options": {"num_ctx": self.config.context_window, "num_predict": 1},
            }, timeout=120)
            return True
        except Exception:
            return False

    def complete(
        self,
        system_prompt: str,
        prompt: str,
        tab_id: str = "",
        temperature: float = 0.2,
        max_tokens: int = 700,
        timeout: int = 90,
        model: str = "",
    ) -> str:
        """
        Blocking, non-streamed completion.
        Used by the Training Path, which needs the whole derivation
        before it can check it. Raises on connection or HTTP errors
        so the caller can fall back to the Knowledge Path.
        """
        model = model or self.config.model_for_tab(tab_id)
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": prompt},
            ],
            "stream": False,
            "keep_alive": self.config.keep_alive,
            **_thinking_off(model),
            "options": {
                "num_ctx":        self.config.context_window,
                "num_predict":    max_tokens,
                "temperature":    temperature,
                "top_p":          0.9,
                "repeat_penalty": 1.1,
            },
        }
        r = requests.post(f"{self.base_url}/api/chat", json=payload, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        # Where the time went, for the log (the librarian's calls are timed this way)
        ns = lambda k: int(data.get(k, 0) or 0) // 1_000_000
        self.last_complete_stats = {
            "load_ms": ns("load_duration"),
            "prompt_tokens": int(data.get("prompt_eval_count", 0) or 0),
            "prompt_eval_ms": ns("prompt_eval_duration"),
            "gen_tokens": int(data.get("eval_count", 0) or 0),
            "gen_ms": ns("eval_duration"),
        }
        self._note_load(model, self.last_complete_stats["load_ms"])
        return strip_thinking(data.get("message", {}).get("content", ""))

    # Swap watch. The owner's card had 1.1 GB free of 8 GB (other programs);
    # the two models need ~2.7 GB together, so Ollama unloaded one to load the
    # other on EVERY step — 1.5–3 s each, most layers on the processor.
    # A model that was already loaded once and needs loading again (>0.7 s)
    # is a swap; two swaps → `thrashing`: one model for the rest of the run.
    SWAP_MS = 700

    def thinks(self, model: str, intent: str) -> bool:
        """Think it through first? Setting on, a hard question, a model that can,
        full power, and the graphics card not already swapping models."""
        return (bool(getattr(self.config, "think_hard", False)) and intent in LONG_INTENTS
                and intent != "emergency" and bool(_thinking_off(model))
                and not getattr(self.config, "low_power_active", False)
                and not getattr(self, "thrashing", False))

    def reply_tokens(self, intent: str = "") -> int:
        """How long a reply may be: longer for steps and explanations,
        shorter in low-power mode (each word costs more on a processor)."""
        base = int(getattr(self.config, "max_tokens", 300) or 300)
        low = getattr(self.config, "low_power_active", False)
        if intent in LONG_INTENTS:
            return min(max(base, 650), 450) if low else max(base, 650)
        return min(base, 220) if low else base

    def _note_load(self, model: str, load_ms: int):
        seen = self.__dict__.setdefault("_loaded_once", set())
        if model in seen and load_ms > self.SWAP_MS:
            self.swaps = getattr(self, "swaps", 0) + 1
            if self.swaps >= 2:
                self.thrashing = True
        seen.add(model)

    def summarize(self, conversation_text: str) -> str:
        """
        Generate a summary of conversation history.
        Used for rolling context management.
        Blocking call (not streamed).
        Low temperature — factual compression, not creative.
        """
        try:
            # The librarian, unless the card can't hold both models (then the
            # speaker, already loaded — no swap just for a summary)
            model = (self.config.speaker_model if getattr(self, "thrashing", False)
                     else self.config.librarian_model or self.config.fast_model)
            payload = {
                "model": model,
                **_thinking_off(model),
                "messages": [{
                    "role": "user",
                    "content": (
                        "Summarise this conversation as notes for yourself, so you can carry on "
                        "with it later. Keep every name, number and place; what they said about "
                        "themselves and their situation; what was answered or decided; and what "
                        "they were asking about last. 4-6 short lines of plain facts, no comments:"
                        "\n\n" + conversation_text
                    )
                }],
                "stream": False,
                "keep_alive": self.config.keep_alive,
                "options": {
                    "num_ctx":     self.config.context_window,
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
                return strip_thinking(r.json()["message"]["content"])

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
        # Order: the rules, then how to answer, then about them, then the
        # library LAST — right before their message, where a small model
        # pays most attention. Plain headings: ALL-CAPS ones were repeated
        # back in replies.
        parts = [tab_system] if tab_system else []

        if llm_bounds:
            parts.append(llm_bounds.strip())

        if decision_addendum:
            parts.append("How to answer:\n" + decision_addendum.strip())

        if user_context and user_context.strip() not in ("No user context yet.", "Day: 1"):
            parts.append("About them:\n" + user_context.strip())

        if confidence_note:
            parts.append(confidence_note.strip())

        if knowledge_context:
            parts.append("From the library (answer from this):\n" + knowledge_context.strip())

        if not decision_addendum and not llm_bounds:
            parts.append("Be concise. Match length to what's needed. "
                         "Speak naturally. When uncertain, say so.")

        return "\n\n".join(parts)
