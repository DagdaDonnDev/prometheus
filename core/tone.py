"""
Tone of the person's message — read in code, handed to the model explicitly.

A 1–3B model can't reliably pick up mood from a long instruction, so it slides
into one cheerful, actor-ish voice for everything. Instead, each message gets
one short line telling it how to sound right now, placed last in the prompt
(small models attend most to what's last).

Signals: wording, "!!"/"?!", CAPITALS, emoji, very short replies, and whether
the previous message was already annoyed or low (moods carry over a bit).
"""

import re
from typing import List, Tuple

TONES = {
    "annoyed": ("They sound annoyed or frustrated with you. Be short and direct. "
                "No cheer, no exclamation marks, no apologising over and over. "
                "If you got something wrong, say so in a few words and fix it."),
    "low":     ("They sound low or tired. Keep it short, quiet and steady. "
                "No cheer, no pep talk, no advice unless they ask."),
    "excited": ("They sound happy or excited. Be into it: react, ask about it. "
                "Match their energy — but stay yourself, not a cheerleader."),
    "curious": ("They're asking something. Answer it plainly and well, then stop."),
    "neutral": ("Plain and relaxed, like texting a mate. No exclamation marks, "
                "no gushing, no 'Oh!' openers."),
}

_ANNOYED = [
    r"\bno+\b[, ]*(stop|wrong|that'?s not|it is ?n'?t|not)", r"\bstop\b", r"\bwrong\b",
    r"\bthat'?s not\b", r"\bis ?n'?t (about|what|it)\b", r"\bnot (listening|hearing)\b",
    r"\byou'?re not\b", r"\bugh+\b", r"\bwtf\b", r"\bseriously\b", r"\bannoying\b",
    r"\bshut up\b", r"\bwhatever\b", r"\bi (just )?said\b", r"\bnever ?mind\b", r"\bidiot\b",
    r"\bdumb\b", r"\buseless\b", r"\bwhy (would|did) you\b",
]
_LOW = [
    r"\bsad\b", r"\btired\b", r"\bexhausted\b", r"\blonely\b", r"\balone\b", r"\bmiss (him|her|them|you|my)\b",
    r"\brough (day|week|night)\b", r"\bbad day\b", r"\bcrap(py)? day\b", r"\bdown\b", r"\bdepress",
    r"\bcan'?t sleep\b", r"\bhurts?\b", r"\bcry", r"\bupset\b", r"\bstressed\b", r"\bworried\b",
    r"\boverwhelm", r"\bfed up\b", r"\bgive up\b", r"\bpointless\b", r"\bempty\b",
]
_EXCITED = [
    r"\bso excited\b", r"\bexcited\b", r"\bamazing\b", r"\bawesome\b", r"\bincredible\b",
    r"\bgreat news\b", r"\bfinally\b", r"\bcan'?t wait\b", r"\byay+\b", r"\bwoo+\b", r"\blet'?s go\b",
    r"\bi got (the|a|my)\b", r"\bi did it\b", r"\bguess what\b", r"\bbest (day|thing)\b",
]
_HAPPY_EMOJI = "😀😃😄😁😆😊🥳🎉❤️😍🤩👍🔥"
_SAD_EMOJI = "😢😭😞😔☹️🙁💔😩😫"
_ANGRY_EMOJI = "😠😡🤬🙄😤"


def _score(text: str, patterns: List[str]) -> int:
    t = text.lower()
    return sum(1 for p in patterns if re.search(p, t))


def detect_tone(text: str, previous: str = "") -> Tuple[str, str]:
    """
    (tone, one-line instruction). Tones: annoyed, low, excited, curious, neutral.

    Step 1: score the message on each mood (wording, emoji, !!, CAPITALS)
    Step 2: a mood from the previous message counts a little, so "no" after
            an annoyed message stays annoyed
    Step 3: strongest mood wins; a plain question is "curious"; else neutral
    """
    t = text.strip()
    letters = [c for c in t if c.isalpha()]
    caps = len(letters) >= 6 and sum(c.isupper() for c in letters) / len(letters) > 0.7

    # Step 1
    annoyed = _score(t, _ANNOYED) * 2 + sum(c in t for c in _ANGRY_EMOJI) * 2
    low = _score(t, _LOW) * 2 + sum(c in t for c in _SAD_EMOJI) * 2
    excited = _score(t, _EXCITED) * 2 + sum(c in t for c in _HAPPY_EMOJI) * 2
    # CAPITALS and "!!" make whatever the words say louder ("I GOT THE JOB!!"
    # is excited, "NO STOP" is annoyed); on their own they lean annoyed
    loud = (2 if caps else 0) + (1 if re.search(r"[!?]{2,}|!\s*$", t) else 0)
    if loud:
        if excited >= annoyed and excited:
            excited += loud
        elif annoyed:
            annoyed += loud
        elif caps:
            annoyed += loud

    # Step 2
    if previous:
        prev, _ = detect_tone(previous)
        short_reply = len(t.split()) <= 4
        if prev == "annoyed" and (short_reply or annoyed):
            annoyed += 1
        if prev == "low" and short_reply and not excited:
            low += 2          # "yeah" after "rough day" is still low

    # Step 3
    best = max(("annoyed", annoyed), ("low", low), ("excited", excited), key=lambda x: x[1])
    if best[1] >= 2 or (best[0] == "annoyed" and best[1] >= 1 and previous):
        tone = best[0]
    elif "?" in t or re.match(r"(?i)(what|why|how|who|when|where|which|can|could|do|does|is|are|tell me|explain)\b", t):
        tone = "curious"
    else:
        tone = "neutral"
    return tone, TONES[tone]
