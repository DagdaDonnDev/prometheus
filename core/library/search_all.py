"""
One search over everything the app knows — the Search tab.

    "plants" →  In your books   Edible Wild Plants, p. 12 — "…"
                Your notes      Obsidian — Garden plan
                Wikipedia       Plant — "A plant is…"

Step 1: books — the library passages that match (by meaning when ChromaDB is
        set up, by words otherwise), kept only if they're on the subject
        (core/ai/librarian.relevant), one per page
Step 2: your own notes (Obsidian), when a vault is set
Step 3: Wikipedia (core/library/wiki_lookup.search)

Every result says where it's from: the book and page, the note, or the
article. No Qt here — the tab (ui/panels/wiki_search.py) runs it on a thread.
"""

from pathlib import Path
from typing import Dict, List, Optional

from core.ai.librarian import relevant
from core.library.titles import source_key

KB = Path("knowledge_base")
_files: Dict[str, Dict[str, Path]] = {}


def book_file(domain: str, source: str, kb: Path = KB) -> Optional[Path]:
    """The file a passage came from (by the name the library uses for it)."""
    if domain not in _files:
        found = {}
        folder = kb / domain
        if folder.is_dir():
            for f in folder.rglob("*"):
                if f.is_file() and "_images" not in f.parts:
                    found.setdefault(source_key(f), f)
        _files[domain] = found
    return _files[domain].get(source)


def page_image(domain: str, source: str, page: int, kb: Path = KB) -> str:
    """The saved picture of that page, if there is one (any page — it's the source itself)."""
    if not page:
        return ""
    p = kb / domain / "_images" / f"{source}_p{int(page):03d}.jpg"
    return str(p) if p.exists() else ""


def _snippet(text: str, query: str, words: int = 40) -> str:
    from core.answers.confidence import trim_passage
    return trim_passage(" ".join((text or "").split()), query, words)


def search_books(query: str, knowledge, n: int = 10) -> List[Dict]:
    """Step 1."""
    if knowledge is None or not hasattr(knowledge, "search_library"):
        return []
    try:
        chunks = knowledge.search_library(query, n * 3)
    except Exception:
        return []
    out, seen = [], set()
    label = getattr(getattr(knowledge, "scorer", None), "_source_label", lambda s, d: s)
    for c in chunks:
        domain, source, page = c.get("domain", ""), c.get("source", ""), int(c.get("page_num", 0) or 0)
        key = (source, page if page else c.get("content", "")[:60])
        if key in seen or not relevant(query, c.get("content", "")):
            continue
        seen.add(key)
        title = label(source, domain)
        f = book_file(domain, source)
        out.append({
            "kind": "book",
            "title": title,
            "where": (f"p. {page} · " if page else "") + domain.replace("_", " "),
            "source": title + (f", p. {page}" if page else ""),
            "snippet": _snippet(c.get("content", ""), query),
            "content": c.get("content", ""),
            "domain": domain,
            "page": page,
            "image": page_image(domain, source, page),
            "path": str(f) if f else "",
        })
        if len(out) >= n:
            break
    return out


def search_notes(query: str, n: int = 4) -> List[Dict]:
    """Step 2."""
    try:
        from core.library.obsidian import search_notes as notes
        found = notes(query, n=n, words=200)
    except Exception:
        return []
    return [{
        "kind": "note",
        "title": r["source"].replace("Obsidian — ", "", 1),
        "where": "your notes",
        "source": r["source"],
        "snippet": _snippet(r["content"], query),
        "content": r["content"],
        "path": "",
    } for r in found]


def search_wikipedia(query: str, knowledge=None, n: int = 30) -> List[Dict]:
    """Step 3."""
    from core.library import wiki_lookup
    try:
        found = wiki_lookup.search(query, limit=n, knowledge=knowledge)
    except Exception:
        return []
    return [{
        "kind": "wikipedia",
        "title": r["title"],
        "where": "Wikipedia",
        "source": f"Wikipedia — {r['title']}",
        "snippet": r.get("snippet", ""),
        "path": str(r["path"]),
    } for r in found]


def search_everything(query: str, knowledge=None) -> Dict[str, List[Dict]]:
    """{"book": [...], "note": [...], "wikipedia": [...]} — each best first."""
    query = (query or "").strip()
    if not query:
        return {"book": [], "note": [], "wikipedia": []}
    return {
        "book": search_books(query, knowledge),
        "note": search_notes(query),
        "wikipedia": search_wikipedia(query, knowledge),
    }
