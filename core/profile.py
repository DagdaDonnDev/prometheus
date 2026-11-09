"""
What Prometheus knows about the person — proposed from what they say,
confirmed by them in the Review tab (core/claims), then kept in memory
(memory/user_memory.json → "user"), editable by them.

Learning is plain pattern matching on their own messages, never the model's
guess: "my sister Kate", "I live in Cork", "I work as a nurse", "I love
hiking". It errs towards learning nothing — a wrong fact is worse than a
missing one. Everything learned can be seen and changed (Obsidian Me.md).

The companion gets a short "what you know about them" line, plus the titles
of a few earlier chats in this tab (topics only — not their messages, so a
new chat still starts fresh).
"""

import re
from typing import Dict, List

# Who someone is to them
RELATIONS = (
    "sister|brother|mum|mom|mother|dad|father|wife|husband|partner|son|daughter|"
    "friend|best friend|girlfriend|boyfriend|nan|nana|gran|grandma|grandmother|"
    "grandad|grandpa|grandfather|aunt|auntie|uncle|cousin|niece|nephew|boss|"
    "flatmate|roommate|neighbour|neighbor|fiance|fiancee|kid|baby"
)
PETS = "dog|cat|puppy|kitten|horse|rabbit|bunny|hamster|parrot|bird|snake|lizard|fish"

# Words that end a phrase ("I love hiking but it's cold" → "hiking")
_CUT = (r"[.!?,;:()]|\s(?:but|and then|because|cos|cause|though|although|so|which|"
        r"when|if|lol|haha|tbh|honestly|anyway|right now|these days|at the moment)\b")
# Things after "I love/like/hate" that aren't a taste
_NOT_A_TASTE = {"you", "it", "that", "this", "them", "him", "her", "how", "when", "what",
                "to", "the way", "being", "having", "your", "my", "a", "an", "it when"}

_NAME = r"([A-Z][a-z'’-]+(?:\s[A-Z][a-z'’-]+)?)"
_PLACE = r"([A-Z][\w'’-]+(?:[\s,]+[A-Z][\w'’-]+){0,2})"


def _phrase(text: str, max_words: int = 5) -> str:
    """The short phrase at the start of text, or '' if it runs on too long."""
    p = re.split(_CUT, text, maxsplit=1, flags=re.I)[0].strip(" '\"“”")
    p = re.sub(r"^(?:really|so much|a lot of|loads of|all|most)\s+", "", p, flags=re.I)
    words = p.split()
    if not words or len(words) > max_words:
        return ""
    return p


def _add(lst: List[str], value: str, cap: int = 30) -> bool:
    """Add to a list without duplicates (case-insensitive). True if new."""
    if not value or any(v.lower() == value.lower() for v in lst):
        return False
    lst.append(value)
    del lst[:-cap]
    return True


def extract(text: str) -> List["Claim"]:
    """
    Claims about themselves in one message — proposals only, nothing is
    saved here (core/claims stages them for review).

    Step 1: name, place, work
    Step 2: people and pets ("my sister Kate", "my dog is called Max")
    Step 3: likes and dislikes, favourites, skills
    Confidence: how reliably that pattern means what it seems to.
    """
    from core.claims import Claim
    t = " ".join(text.split())
    out: List[Claim] = []

    def add(field, value, note, confidence):
        if value and not any(c.field == field and c.value.lower() == value.lower() for c in out):
            out.append(Claim(field=field, value=value, note=note, utterance=text.strip(),
                             confidence=confidence))

    # Step 1
    m = re.search(r"\b(?:my name is|my name's|call me|i'?m called)\s+" + _NAME + r"\b", t, re.I)
    if m and m.group(1)[:1].isupper() and m.group(1).lower() not in _NOT_A_TASTE:
        add("name", m.group(1), f"your name is {m.group(1)}", 0.9)

    # the lead-in in any case, the place itself Capitalised
    m = re.search(r"(?i:\b(?:i live in|i'?m from|i'?m based in|i grew up in|we live in))\s+" + _PLACE, t)
    if m:
        place = m.group(1).strip(" ,")
        grew = "grew up" in m.group(0).lower()
        add("location_estimate", place, f"you grew up in {place}" if grew else f"you live in {place}",
            0.6 if grew else 0.85)

    m = re.search(r"\b(?:i work as|i'?m working as|my job is|i'?m employed as)\s+(?:an?\s+)?(.+)", t, re.I)
    at = re.search(r"\bi work (at|for)\s+(.+)", t, re.I)
    if m or at:
        work = _phrase(m.group(1) if m else at.group(2), 5)
        if work and not m:
            work = f"{at.group(1).lower()} {work}"          # "at the hospital"
        if work and work.lower() not in _NOT_A_TASTE:
            add("work", work, f"you work {'as ' if m else ''}{work}", 0.75)

    # Step 2
    for m in re.finditer(r"\bmy\s+(" + RELATIONS + r")(?:'s name is|\s+is called|\s+called|\s+named|,)?\s+"
                         + _NAME + r"\b", t, re.I):
        rel, who = m.group(1).lower(), m.group(2)
        if not who[:1].isupper() or who.split()[0].lower() in ("is", "was", "and", "has", "just", "i"):
            continue
        who = who.split()[0] if len(who.split()) > 1 and who.split()[1][:1].islower() else who
        add("mentioned_people", f"{who} ({rel})", f"{who} is your {rel}", 0.85)
    for m in re.finditer(r"\bmy\s+(" + PETS + r")(?:'s name is|\s+is called|\s+called|\s+named|,)?\s+"
                         + _NAME + r"\b", t, re.I):
        pet, who = m.group(1).lower(), m.group(2).split()[0]
        if not who[:1].isupper() or who.lower() in ("is", "was", "and", "has", "just", "i"):
            continue
        add("mentioned_people", f"{who} ({pet})", f"{who} is your {pet}", 0.85)

    # Step 3
    for m in re.finditer(r"\bi\s+(?:really\s+|absolutely\s+|just\s+)?(love|like|enjoy|adore|am into|'m into)\s+(.+)", t, re.I):
        if re.search(r"\b(?:would|'d|don'?t|do not|didn'?t)\s*$", t[:m.start()].lower()):
            continue
        thing = _phrase(m.group(2))
        if thing and thing.lower() not in _NOT_A_TASTE and thing.split()[0].lower() not in _NOT_A_TASTE:
            add("likes", thing, f"you like {thing}", 0.7)
    for m in re.finditer(r"\bi\s+(?:really\s+)?(hate|can'?t stand|don'?t like|do not like|dislike|detest)\s+(.+)", t, re.I):
        thing = _phrase(m.group(2))
        if thing and thing.lower() not in _NOT_A_TASTE and thing.split()[0].lower() not in _NOT_A_TASTE:
            add("dislikes", thing, f"you don't like {thing}", 0.7)
    for m in re.finditer(r"\bmy\s+fav(?:ou?rite)?\s+([a-z ]{2,20}?)\s+(?:is|are|has to be)\s+(.+)", t, re.I):
        thing = _phrase(m.group(2))
        if thing and thing.split()[0].lower() not in _NOT_A_TASTE:
            kind = m.group(1).strip().lower()
            add("likes", f"{thing} (favourite {kind})", f"your favourite {kind} is {thing}", 0.85)
    for m in re.finditer(r"\bi(?:'m| am)\s+(?:really\s+|pretty\s+)?good at\s+(.+)|\bi know how to\s+(.+)|"
                         r"\bi(?:'m| am)\s+(?:a\s+)?trained\s+(.+)", t, re.I):
        skill = _phrase(next(g for g in m.groups() if g), 5)
        if skill and skill.split()[0].lower() not in _NOT_A_TASTE:
            add("known_skills", skill, f"you can {skill}" if m.group(2) else f"you're good at {skill}", 0.6)
    return out


def learn(text: str, memory) -> List[str]:
    """
    Stage 1 of a fact's life: claims in this message go to the review list
    (core/claims) — NOT into the profile. Returns plain notes of what was
    added for review ("Kate is your sister"); empty if nothing new.
    """
    from core import claims
    return [c.note for c in claims.stage(extract(text), memory)]


def about_line(memory, max_words: int = 55) -> str:
    """'What you know about them: …' for the companion prompt, or ''."""
    u = (memory.data.get("user") or {})
    bits = []
    if u.get("location_estimate"):
        bits.append(f"lives in {u['location_estimate']}")
    if u.get("work"):
        w = u["work"]
        bits.append(f"works {w}" if w.split()[0].lower() in ("at", "for", "in") else f"works as {w}")
    if u.get("mentioned_people"):
        bits.append("people in their life: " + ", ".join(u["mentioned_people"][-5:]))
    if u.get("likes"):
        bits.append("likes " + ", ".join(u["likes"][-5:]))
    if u.get("dislikes"):
        bits.append("doesn't like " + ", ".join(u["dislikes"][-3:]))
    if u.get("known_skills"):
        bits.append("skills: " + ", ".join(u["known_skills"][-3:]))
    for n in (u.get("notes") or [])[-2:]:
        if isinstance(n, str):
            bits.append(n)
    if not bits:
        return ""
    words = "; ".join(bits).split()
    text = " ".join(words[:max_words]) + ("…" if len(words) > max_words else "")
    return ("What you know about them (use it naturally, don't list it back): " + text + ".")


def earlier_topics(tab, limit: int = 3) -> str:
    """Titles of their last few other chats in this tab — topics only."""
    if tab is None:
        return ""
    others = [c for c in getattr(tab, "chats", []) if c.get("id") != tab.chat_id and c.get("title")]
    others.sort(key=lambda c: c.get("updated", ""), reverse=True)
    titles = [c["title"] for c in others[:limit]]
    if not titles:
        return ""
    return ("Earlier chats with them were about: " + "; ".join(titles) +
            ". Only bring these up if they do.")
