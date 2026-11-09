"""
Readable names for the books in the library.

The library knows each book by its file name — archive.org scans come out as
"practicalcarpen01radfgoog" — and that's what answers credited ("From:
Practicalcarpen01Radfgoog"). This keeps a list of proper titles in
knowledge_base/titles.json:

    {"practicalcarpen01radfgoog": "Practical Carpentry", …}

Step 1: PDFs — the title stored inside the file, tidied ("Practical carpentry;
        being a guide to the correct working…" → "Practical carpentry")
Step 2: Markdown — the first "# " heading
Step 3: text files and anything else — the file name, cleaned ("…by Barbara
        Jones" dropped, underscores to spaces) unless it looks like a code
Step 4: entries already in the file are never changed — edit it to fix any

    python tools/ingest.py --titles     fill it in (seconds; also done after every ingest)
"""

import json
import re
from pathlib import Path
from typing import Dict, Optional

TITLES_PATH = Path("knowledge_base") / "titles.json"
_cache: Dict[str, object] = {"mtime": None, "titles": {}}


def source_key(path: Path) -> str:
    """The name the library uses for a file (the same rule as tools/ingest.py)."""
    return path.stem.replace(" ", "_").lower()


def _tidy(title: str, limit: int = 70) -> str:
    t = " ".join((title or "").replace("_", " ").split())
    t = re.sub(r"^(microsoft word|untitled)\s*-\s*", "", t, flags=re.I)
    t = re.sub(r"\.(docx?|pdf|txt)$", "", t, flags=re.I)
    t = re.split(r"\s*[;:]\s+|\s+/\s+|\s+—\s+", t)[0]               # main title, not the subtitle
    t = re.split(r",?\s+by\s+[A-Z]", t)[0]                          # "…by Barbara Jones"
    if len(t) > limit:
        t = t[:limit].rsplit(" ", 1)[0] + "…"
    return t.strip(" ,.-")


def _looks_like_a_code(title: str) -> bool:
    """'practicalcarpen01radfgoog', 'b32172321', 'FM5-10' — not a readable title."""
    t = title.strip()
    if not t or t.lower() in ("untitled", "title", "document", "book"):
        return True
    return " " not in t and (bool(re.search(r"\d", t)) or len(t) > 18)


def title_from_file(path: Path) -> Optional[str]:
    # Step 1
    if path.suffix.lower() == ".pdf":
        try:
            import fitz
            with fitz.open(str(path)) as doc:
                meta = (doc.metadata or {}).get("title", "")
            t = _tidy(meta)
            if t and not _looks_like_a_code(t):
                return t
        except Exception:
            pass
    # Step 2
    if path.suffix.lower() == ".md":
        try:
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("# "):
                    return _tidy(line[2:])
        except OSError:
            pass
    # Step 3
    t = _tidy(path.stem)
    return t if t and not _looks_like_a_code(t) else None


def build(kb: Path = Path("knowledge_base"), out: Path = None, progress=print) -> int:
    """Add titles for books not yet listed (Step 4: never overwrite). Returns how many added."""
    out = out or (kb / "titles.json")
    try:
        titles = json.loads(out.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        titles = {}
    added = 0
    for folder in sorted(p for p in kb.iterdir() if p.is_dir()) if kb.is_dir() else []:
        if folder.name in ("wikipedia",) or folder.name.startswith(("_", ".")):
            continue
        for f in sorted(folder.rglob("*")):
            if not f.is_file() or f.suffix.lower() not in (".pdf", ".txt", ".md", ".html", ".htm") \
                    or f.name.lower() == "readme.md" or "_images" in f.parts:
                continue
            key = source_key(f)
            if key in titles:
                continue
            t = title_from_file(f)
            if t:
                titles[key] = t
                added += 1
    if added or not out.exists():
        out.write_text(json.dumps(dict(sorted(titles.items())), indent=1, ensure_ascii=False),
                       encoding="utf-8")
    progress(f"  Book titles: {added} added, {len(titles)} in {out}")
    return added


def title_for(source: str) -> Optional[str]:
    """A book's readable title, if known (re-read when the file is edited)."""
    try:
        mtime = TITLES_PATH.stat().st_mtime
    except OSError:
        return None
    if _cache["mtime"] != mtime:
        try:
            _cache["titles"] = json.loads(TITLES_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _cache["titles"] = {}
        _cache["mtime"] = mtime
    return _cache["titles"].get(source)
