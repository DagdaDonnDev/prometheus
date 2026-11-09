"""
Facts the model notices about you — proposals for the Review tab.

The fixed patterns in core/you/profile.py catch "my sister Kate" and "I live
in Cork", but not "we moved to Galway last year" or "my brother Tom fixes
cars for a living". After a reply, the librarian reads the person's message
and lists what they said about themselves.

Step 1: only messages that talk about themselves ("I", "my", "we" …) and
        aren't just a question — most messages cost nothing
Step 2: the librarian answers in fixed lines ("location: Galway"), or NONE
Step 3: every value must be made of words they actually wrote — a small
        model can't slip in a guess this way
Step 4: proposals go to Review as "not sure · noticed by the model";
        nothing is used until accepted (core/you/claims)
"""

import re
from typing import List

from core.you.claims import Claim

NOTICE_SYSTEM = (
    "You note facts a person states about THEMSELVES in one message. Reply with one per "
    "line, exactly in this form, or the single word NONE:\n"
    "name: <their name>\n"
    "location: <where they live>\n"
    "work: <their job>\n"
    "person: <Name> (<relation>)   e.g. Kate (sister), Max (dog)\n"
    "like: <something they like>\n"
    "dislike: <something they dislike>\n"
    "skill: <something they can do>\n"
    "Only what they plainly said about themselves. No guesses."
)

_SELF = re.compile(r"\b(i|i'm|im|i've|i'd|i'll|me|my|mine|we|we're|we've|our|us)\b", re.I)
_QUESTION_ONLY = re.compile(r"^\s*(what|why|how|who|when|where|which|can|could|do|does|is|are|"
                            r"should|would|will|tell me|explain)\b.*\?\s*$", re.I | re.S)
_FIELDS = {"name": "name", "location": "location_estimate", "work": "work",
           "person": "mentioned_people", "like": "likes", "dislike": "dislikes", "skill": "known_skills"}
_STOP = {"the", "a", "an", "and", "of", "to", "in", "on", "at", "for", "with", "as", "my", "their",
         "his", "her", "is", "be", "it"}


def worth_asking(text: str) -> bool:
    """Step 1."""
    t = " ".join(text.split())
    return len(t.split()) >= 4 and bool(_SELF.search(t)) and not _QUESTION_ONLY.match(t)


def _grounded(value: str, text: str) -> bool:
    """Step 3: the value's words (ignoring small words) all appear in what they wrote."""
    said = set(re.findall(r"[a-z0-9']+", text.lower()))
    words = [w for w in re.findall(r"[a-z0-9']+", value.lower()) if w not in _STOP]
    if not words:
        return False

    def seen(w):
        return w in said or w.rstrip("s") in said or (w + "s") in said
    return all(seen(w) for w in words)


def _note(field: str, value: str) -> str:
    if field == "mentioned_people":
        m = re.match(r"(.+?)\s*\((.+)\)", value)
        return f"{m.group(1)} is your {m.group(2)}" if m else f"{value} is someone in your life"
    return {"name": "your name is {}", "location_estimate": "you live in {}",
            "work": "you work as {}", "likes": "you like {}", "dislikes": "you don't like {}",
            "known_skills": "you can {}"}[field].format(value)


def parse(raw: str, text: str) -> List[Claim]:
    """Steps 2–3: the librarian's lines → grounded claims."""
    out: List[Claim] = []
    if not raw or raw.strip().upper().startswith("NONE"):
        return out
    for line in raw.splitlines():
        m = re.match(r"\s*[-*]?\s*(name|location|work|person|like|dislike|skill)\s*:\s*(.+)$", line, re.I)
        if not m:
            continue
        field = _FIELDS[m.group(1).lower()]
        value = " ".join(m.group(2).strip(" .\"'").split())
        if not value or value.upper() == "NONE" or len(value.split()) > 7:
            continue
        if field == "mentioned_people":
            pm = re.match(r"([A-Z][\w'-]+)\s*\(([a-z ]{2,20})\)$", value)
            if not pm:
                continue
            # the name must be in the message; the relation word too
            if not _grounded(pm.group(1), text) or not _grounded(pm.group(2), text):
                continue
        elif not _grounded(value, text):
            continue
        if any(c.field == field and c.value.lower() == value.lower() for c in out):
            continue
        out.append(Claim(field=field, value=value, note=_note(field, value), utterance=text.strip(),
                         confidence=0.55, origin="model"))
    return out


def notice(llm, text: str) -> List[Claim]:
    """The whole thing (blocking — run it on a background thread)."""
    if not worth_asking(text):
        return []
    try:
        raw = llm.complete(NOTICE_SYSTEM, text, model=llm.config.librarian_model,
                           temperature=0.0, max_tokens=80, timeout=30)
    except Exception:
        return []
    return parse(raw, text)
