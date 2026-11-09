"""
Two models, two jobs.

    speaker   (Qwen3 1.7B)  — the only voice you hear. Turns your message into
                              a clear library request, then answers you in its
                              persona using ONLY the facts the librarian found.
    librarian (LFM2.5 1.2B) — never talks to you. Reads the library passages
                              and lists the facts in them that answer the
                              request — or NOT FOUND. It never adds anything
                              from its own memory.

A message goes:
  1. brief()   speaker: message (+ the last exchange) → SEARCH words + QUESTION
  2. the library is searched with those words           (core/library/rag, wiki_lookup)
  3. extract() librarian: QUESTION + passages → facts, or NOT FOUND
  4. the speaker answers from those facts               (core/answers/pipeline)

Small talk skips all of this: the speaker just answers. Emergencies skip the
brief (every second counts) and search with the message as written.

Prompts and outputs are kept short — every extra token is read before the
first word comes out.
"""

import difflib
import re
import time
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple

BRIEF_SYSTEM = (
    "You write requests for a librarian. Reply with exactly two lines and nothing else:\n"
    "SEARCH: 3-8 keywords to look up (names, things, the topic)\n"
    "QUESTION: the person's question, written out in full on one line\n"
    "If the message continues the last exchange (\"tell me more\", \"why\", \"their missions\"), "
    "put the subject from the last exchange into both lines."
)

EXTRACT_SYSTEM = (
    "You are a librarian. You never answer from memory, only from the passages.\n"
    "List the facts from the passages that help answer the question, even if they only "
    "answer part of it.\n"
    "- One fact per line, starting with \"- \" and ending with the passage number, e.g. [2].\n"
    "- Copy numbers, amounts, doses, times and steps exactly as written.\n"
    "- At most 8 facts. No opinions, no advice, nothing the passages don't say.\n"
    "- Only if the passages say nothing at all about it, reply with exactly: NOT FOUND"
)

MAX_PASSAGE_WORDS = 380        # all passages together (keeps the librarian's prompt short)


@dataclass
class Brief:
    search: str
    question: str
    ms: int = 0


@dataclass
class Facts:
    text: str                  # "- fact [1]\n- fact [2]" or ""
    found: bool
    ms: int = 0
    failed: bool = False       # the librarian couldn't be asked → use the passages as before
    raw: str = ""              # what it actually wrote (for the log)
    stats: Dict = field(default_factory=dict)   # Ollama's timing for the call

    def cited(self) -> Set[int]:
        """Passage numbers the facts point to ([2] → 2)."""
        return {int(n) for n in re.findall(r"\[(\d+)\]", self.text)}


class Librarian:
    def __init__(self, llm):
        self.llm = llm

    @property
    def config(self):
        return self.llm.config

    def enabled(self) -> bool:
        return bool(getattr(self.config, "two_models", False))

    # ── 1. The speaker's request to the librarian ──────────────────────────

    def brief(self, message: str, last_user: str = "", last_reply: str = "") -> Brief:
        """
        The message as a clear library request. Falls back to the message
        itself if the speaker can't be reached or answers oddly.
        """
        started = time.time()
        context = ""
        if last_user:
            context = (f"Last exchange — they said: {_cut(last_user, 40)}\n"
                       f"You replied: {_cut(last_reply, 40)}\n\n")
        try:
            raw = self.llm.complete(BRIEF_SYSTEM, f"{context}Message: {message}",
                                    model=self.config.speaker_model,
                                    temperature=0.0, max_tokens=60, timeout=30)
        except Exception:
            raw = ""
        search = _field(raw, "SEARCH")
        question = _field(raw, "QUESTION")
        # A small model sometimes copies the instructions back ("SEARCH: 3-8
        # keywords to look up…") — that would be searched for. Use the message.
        if _copied(search) or _copied(question):
            search, question = "", ""
        search = " ".join(search.replace(",", " ").split()[:8])
        return Brief(search=search or message, question=question or message,
                     ms=int((time.time() - started) * 1000))

    # ── 3. The librarian reads the passages ────────────────────────────────

    def extract(self, question: str, passages: List[Tuple[str, str]]) -> Facts:
        """
        passages: [(source label, text)]. Returns the facts that answer the
        question, each tagged with its passage number, or found=False.
        """
        started = time.time()
        if not passages:
            return Facts("", False, 0)
        low = getattr(self.config, "low_power_active", False)
        numbered = _numbered(passages, 220 if low else MAX_PASSAGE_WORDS)
        try:
            raw = self.llm.complete(EXTRACT_SYSTEM, f"QUESTION: {question}\n\nPASSAGES:\n{numbered}",
                                    model=self.config.librarian_model,
                                    temperature=0.0, max_tokens=220, timeout=60)
        except Exception:
            raw = ""
        ms = int((time.time() - started) * 1000)
        stats = dict(getattr(self.llm, "last_complete_stats", {}) or {})
        if not raw.strip():
            # No answer at all (Ollama down, model not downloaded): that's not
            # "the library has nothing" — the caller falls back to the passages
            return Facts("", False, ms, failed=True)
        facts = [ln.strip() for ln in raw.splitlines() if ln.strip().startswith(("-", "•", "*"))]
        facts = ["- " + ln.lstrip("-•* ").strip() for ln in facts][:5 if low else 8]
        if not facts or re.search(r"\bNOT FOUND\b", raw) and len(facts) <= 1:
            return Facts("", False, ms, raw=raw, stats=stats)
        return Facts("\n".join(facts), True, ms, raw=raw, stats=stats)


def _copied(value: str) -> bool:
    """True if the model just repeated a line of its instructions."""
    v = " ".join((value or "").lower().split())
    return len(v) > 12 and (v in BRIEF_SYSTEM.lower() or "keywords to look up" in v
                            or "written out in full" in v)


# Words that say what kind of answer they want, not what it's about
_GENERIC = {
    "what", "which", "who", "whom", "whose", "when", "where", "why", "how", "does", "did",
    "can", "could", "would", "should", "will", "shall", "are", "is", "was", "were", "the",
    "and", "for", "with", "from", "about", "into", "some", "any", "all", "you", "your",
    "this", "that", "these", "those", "there", "their", "they", "them", "make", "made",
    "making", "tell", "know", "need", "want", "like", "get", "use", "used", "using", "give",
    "show", "find", "have", "has", "had", "been", "being", "more", "most", "much", "many",
    "good", "best", "way", "ways", "thing", "things", "information", "info", "details",
    "image", "images", "picture", "pictures", "photo", "photos", "diagram", "game", "games",
    "videogame", "film", "movie", "show", "book", "song", "band", "album", "series", "kind",
    "type", "types", "list", "examples", "example", "help", "please", "also", "just", "really",
    "then", "than", "not", "but", "out", "our", "its", "it's", "i'm", "can't", "don't",
}


def subject_words(text: str) -> List[str]:
    """The words of a message that say what it's about ("poisonous mushrooms ireland")."""
    out = []
    for w in re.findall(r"[a-z][a-z'-]+", (text or "").lower()):
        w = w.strip("'-")
        if len(w) >= 3 and w not in _GENERIC and w not in out:
            out.append(w)
    return out


def relevant(message: str, passage: str) -> bool:
    """
    Does the passage talk about what they asked? At least half the message's
    subject words appear in it — a near spelling counts ("posionous").
    A message with no subject words ("who are you") can't be judged → True.
    """
    want = subject_words(message)
    if not want:
        return True
    have = set(re.findall(r"[a-z][a-z'-]+", (passage or "").lower()))
    stems = {h[:5] for h in have if len(h) >= 5}

    def seen(w):
        return (w in have or (len(w) >= 5 and w[:5] in stems) or w.rstrip("s") in have
                or bool(difflib.get_close_matches(w, have, n=1, cutoff=0.85)))
    hits = sum(1 for w in want if seen(w))
    return hits * 2 >= len(want)


def loose_block(passages: List[Tuple[str, str]], message: str, words: int = 110) -> str:
    """
    The librarian found no clear answer, but these passages are on the
    subject — the speaker reads them itself (as it did before two models).
    """
    from core.answers.confidence import trim_passage
    body = "\n\n".join(f"[{label}] {trim_passage(text, message, words)}" for label, text in passages)
    return ("FROM THE LIBRARY — these may only partly cover it. State facts only from them; "
            "for anything they don't cover, say you don't have that:\n" + body)


def _field(raw: str, name: str) -> str:
    m = re.search(rf"^\s*{name}\s*:\s*(.+)$", raw or "", flags=re.M | re.I)
    return " ".join(m.group(1).split())[:200] if m else ""


def _cut(text: str, words: int) -> str:
    w = (text or "").split()
    return " ".join(w[:words]) + (" …" if len(w) > words else "")


def _numbered(passages: List[Tuple[str, str]], budget: int = MAX_PASSAGE_WORDS) -> str:
    """[1] (source) text … — shared fairly within `budget` words."""
    each = max(50, budget // max(1, len(passages)))
    return "\n\n".join(f"[{i}] ({label}) {_cut(text, each)}"
                       for i, (label, text) in enumerate(passages, 1))


def facts_block(facts: Facts, what: str = "this") -> str:
    """The part of the speaker's prompt that carries the librarian's findings."""
    if facts.found:
        return ("LIBRARY FACTS — the only facts you may state about " + what +
                ". Say them in your own words, in your own voice; never add any:\n" + facts.text)
    return "(Nothing in the library covers this — tell them you don't have it; no guessing.)"
