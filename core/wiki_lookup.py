"""
Wikipedia title lookup — "have you seen Inception?" → the Inception article.

The chat tab doesn't run a library search (that's what made it slow), so on
its own the model only knows what a 1–3B model remembers about films, shows,
bands, books and people: very little. This finds the Wikipedia article a
message is about by TITLE, and reads its opening straight from the extracted
file in knowledge_base/wikipedia/. No search index or model call is needed, so
it costs a few milliseconds.

How a match is chosen:
  Step 1: list the article titles once (file names; refreshed if the folder changes)
  Step 2: try every 1–6 word run of the message as a title, plus "(film)",
          "(TV series)", "(band)"… variants when the message hints at one
  Step 3: keep the longest matches. A single word only counts if it was
          written with a capital (or in quotes), so "I watched a movie
          yesterday" doesn't pull in the article "Yesterday".
"""

import re
from pathlib import Path
from typing import Dict, List, Tuple

WIKI_DIR = Path("knowledge_base") / "wikipedia"

# Words that hint at what kind of thing is meant → the title suffix to try first
MEDIA_HINTS = {
    "film": "_film", "movie": "_film", "movies": "_film", "films": "_film",
    "show": "_tv_series", "series": "_tv_series", "tv": "_tv_series", "episode": "_tv_series",
    "band": "_band", "album": "_album", "song": "_song", "track": "_song",
    "book": "_novel", "novel": "_novel", "game": "_video_game", "anime": "_tv_series",
}
ALL_SUFFIXES = ["_film", "_tv_series", "_band", "_album", "_song", "_novel",
                "_video_game", "_film_series", "_musician", "_actor"]

_STOP = {
    "a", "an", "the", "of", "and", "or", "to", "in", "on", "at", "for", "with",
    "is", "are", "was", "were", "be", "been", "it", "its", "this", "that", "i",
    "you", "me", "my", "we", "they", "he", "she", "do", "did", "have", "has",
    "seen", "watch", "watched", "about", "what", "who", "how", "why", "like",
    "just", "so", "really", "think", "know", "heard", "ever", "any", "some",
}

# A lower-case single word counts after one of these ("have you seen inception")
LEAD_IN = {"seen", "watched", "watch", "watching", "heard", "about", "read", "reading",
           "listen", "listening", "played", "playing", "love", "loved", "like", "liked",
           "hate", "hated", "finished", "started", "recommend", "of"}

LEAD_IN_PAIRS = {("what", "is"), ("what", "was"), ("who", "is"), ("who", "was"),
                 ("what", "are"), ("who", "are")}

_cache: Dict[str, object] = {"mtime": None, "titles": {}}


def _is_disambiguation(path: Path) -> bool:
    """'X may refer to: …' pages list meanings — the real article is a variant."""
    try:
        with path.open(encoding="utf-8", errors="replace") as f:
            head = f.read(400).lower()
    except OSError:
        return False
    return "may refer to" in head or "can refer to" in head or "may mean" in head


def _titles() -> Dict[str, Path]:
    """{lower-case file stem: path} for every extracted article (cached)."""
    if not WIKI_DIR.is_dir():
        return {}
    mtime = WIKI_DIR.stat().st_mtime
    if _cache["mtime"] != mtime:
        _cache["titles"] = {p.stem.lower(): p for p in WIKI_DIR.glob("*.txt")}
        _cache["mtime"] = mtime
    return _cache["titles"]


def find_articles(text: str, max_articles: int = 2) -> List[Tuple[str, Path]]:
    """Articles the message is about: [(title, path)], best first."""
    titles = _titles()
    if not titles:
        return []

    raw = re.findall(r"[\w'-]+", text)
    words = [re.sub(r"[^\w-]", "", w).lower() for w in raw]
    quoted = {q.strip().lower() for q in re.findall(r"[\"“']([^\"”']{2,60})[\"”']", text)}
    hint_suffixes = [MEDIA_HINTS[w] for w in words if w in MEDIA_HINTS]

    found: List[Tuple[int, str, Path]] = []
    for n in range(min(6, len(words)), 0, -1):
        for i in range(len(words) - n + 1):
            gram = words[i:i + n]
            if not gram or all(g in _STOP for g in gram) or gram[-1] in _STOP:
                continue
            if n == 1:
                original = raw[i]
                capitalised = original[:1].isupper() and i > 0
                after_lead_in = (i > 0 and words[i - 1] in LEAD_IN) or \
                    (i > 1 and (words[i - 2], words[i - 1]) in LEAD_IN_PAIRS)
                generic = gram[0] in MEDIA_HINTS
                if generic or not (capitalised or gram[0] in quoted or after_lead_in):
                    continue
            key = "_".join(gram)
            # Hinted kind first ("inception" + "movie" → inception_film), then the plain title
            # If the plain title is a "may refer to" page, prefer a variant
            plain_first = [key] + [key + s for s in ALL_SUFFIXES]
            if key in titles and _is_disambiguation(titles[key]):
                plain_first = [key + s for s in ALL_SUFFIXES] + [key]
            for cand in [key + s for s in hint_suffixes] + plain_first:
                if cand in titles:
                    found.append((n, cand, titles[cand]))
                    break

    # Longest first; skip matches contained in a longer one already chosen
    found.sort(key=lambda f: -f[0])
    chosen: List[Tuple[str, Path]] = []
    used = []
    for n, key, path in found:
        if any(key in u for u in used):
            continue
        used.append(key)
        chosen.append((_title_of(path), path))
        if len(chosen) >= max_articles:
            break
    return chosen


def _title_of(path: Path) -> str:
    try:
        with path.open(encoding="utf-8", errors="replace") as f:
            first = f.readline()
        if first.startswith("# "):
            return first[2:].strip()
    except OSError:
        pass
    return path.stem.replace("_", " ")


def lead(path: Path, words: int = 120) -> str:
    """The article's opening ~words, without its title line."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    lines = text.splitlines()
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
    body = " ".join(" ".join(lines).split())
    out = body.split()[:words]
    return " ".join(out) + (" …" if len(body.split()) > words else "")


# ── Search (the Wikipedia tab) ──────────────────────────────────────────────

def article_count() -> int:
    return len(_titles())


def search(query: str, limit: int = 30, knowledge=None) -> List[Dict]:
    """
    Find anything — returns [{"title", "path", "snippet"}], best first.

    Step 1: score every title against the words typed
              exact title          100
              title starts with it  80 (shorter titles first)
              every word in title   60
              some words in title   up to 40
    Step 2: full-text search inside every article (core/wiki_index, SQLite
            FTS5) — exact/starts-with titles stay on top, then the best
            text matches with the matching words as the snippet
    Step 3: if the articles are also indexed by meaning (ChromaDB), add
            those matches, so "film about dreams" can find Inception
    Step 4: openings for title-only results
    """
    titles = _titles()
    words = [w for w in re.findall(r"[\w-]+", query.lower()) if w]
    if not titles or not words:
        return []
    key = "_".join(words)
    want = set(w for w in words if w not in _STOP) or set(words)

    # Step 1
    scored = []
    for stem, path in titles.items():
        if stem == key:
            s = 100
        elif stem.startswith(key):
            s = 80 - min(20, len(stem) - len(key)) / 2
        else:
            parts = set(stem.split("_"))
            hit = len(want & parts)
            if not hit:
                continue
            s = 60 - len(parts) / 2 if hit == len(want) else 40 * hit / len(want) - len(parts) / 4
        scored.append((s, stem, path))
    scored.sort(key=lambda x: (-x[0], len(x[1])))

    # Step 2
    from core import wiki_index
    index_path = WIKI_DIR.parent / "wikipedia_search.sqlite"
    text_hits = wiki_index.search(query, limit=limit, index_path=index_path)
    snippets: Dict[str, str] = {}
    if text_hits:
        top_titles = [(s, stem, path) for s, stem, path in scored if s >= 80][:3]
        results, seen = [], set()
        for s, stem, path in top_titles:
            results.append((s, path)); seen.add(stem)
        for hit in text_hits:
            stem = hit["stem"].lower()
            if stem in seen or stem not in titles:
                continue
            seen.add(stem)
            snippets[stem] = hit["snippet"]
            results.append((70, titles[stem]))
        results = results[:limit]
    else:
        seen = {stem for _, stem, _ in scored[:limit]}
        results = [(s, path) for s, _, path in scored[:limit]]

    # Step 3
    vector = getattr(knowledge, "_vector_search", None)
    if vector and getattr(knowledge, "ready", False) and getattr(knowledge, "collection", None) is not None:
        try:
            for chunk in vector(query, ["wikipedia"], 10):
                stem = chunk.get("source", "")
                if stem and stem not in seen and stem in titles:
                    seen.add(stem)
                    results.append((50, titles[stem]))
        except Exception:
            pass
        results.sort(key=lambda x: -x[0])
        results = results[:limit]

    # Step 4
    return [{"title": _title_of(p), "path": p,
             "snippet": snippets.get(p.stem.lower()) or lead(p, 28)} for _, p in results]


def full_text_ready() -> bool:
    """True once the inside-the-articles search index has been built."""
    p = WIKI_DIR.parent / "wikipedia_search.sqlite"
    return p.exists() and p.stat().st_size > 0


def read_article(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


# ── "Is this something specific I don't have?" ──────────────────────────────

_MEDIA_WORDS = r"(?:movie|film|show|series|tv show|book|novel|song|album|band|game|video game|anime|podcast)"
_ASK_PATTERNS = [
    # verbs that only make sense for a specific thing: lower case is fine after these
    (r"\b(?:have you|did you|ever|you)\s+(?:seen|watched|read|heard of|heard|played|listened to)\s+(.+)", False),
    (r"\bheard of\s+(.+)", False),
    (r"\b(?:the|that|this)\s+" + _MEDIA_WORDS + r"\s+(?:called|named)?\s*(.+)", False),
    # vaguer lead-ins: only if what follows is Capitalised or "quoted"
    (r"\b(?:what do you think (?:of|about)|thoughts on|tell me about|do you know|"
     r"what(?:'s| is| was)|who(?:'s| is| was))\s+(.+)", True),
]
_NOT_A_THING = {"you", "your", "yours", "yourself", "my", "me", "mine", "it", "its", "this", "that",
                "them", "they", "him", "her", "us", "we", "i", "what", "how", "why", "when",
                "where", "who", "up", "going", "anything", "something", "everything", "life"}


def asked_about(text: str) -> str:
    """
    The specific thing a message asks about ("the juror", "Green Book"), or "".
    Used to make the model say plainly when it's not in the library, instead
    of inventing a plot. Errs on the side of "" — a missed case is better
    than "I don't have your day in my database".
    """
    for pattern, needs_capital in _ASK_PATTERNS:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if not m:
            continue
        thing = m.group(1)
        thing = re.split(r"[?.!,;]| (?:and|but|lol|haha|though|at all|yet|before|recently|"
                         r"about|was|is|were|are|has|had|looks|seems|sounds)\b", thing, flags=re.I)[0]
        thing = re.sub(r"^(?:the\s+)?" + _MEDIA_WORDS + r"\s+(?:called\s+|named\s+)?", "", thing.strip(), flags=re.I)
        thing = thing.strip(" \"'“”")
        words = thing.split()
        if not words or len(words) > 6 or words[0].lower() in _NOT_A_THING:
            continue
        if needs_capital:
            quoted = re.search(r"[\"“']" + re.escape(thing) + r"[\"”']", text)
            if not (thing[:1].isupper() or quoted):
                continue
        return thing
    return ""
