"""
Full-text search over the extracted Wikipedia — find anything, not just titles.

Uses SQLite's built-in FTS5 (comes with Python, nothing to install). Building
the index reads every extracted article once — a few minutes for Simple
English Wikipedia — and searches then take milliseconds. Unlike the optional
meaning-based index (hours on a CPU), this needs no AI model.

    python ingest.py --wiki-index      # build / rebuild it on its own
    (it's also built automatically after every Wikipedia extraction)

Ranking: words in the title count 10× words in the body; the last word typed
also matches as a prefix ("incep" finds Inception).
"""

import re
import sqlite3
import time
from pathlib import Path
from typing import Dict, List, Optional

WIKI_DIR   = Path("knowledge_base") / "wikipedia"
INDEX_PATH = Path("knowledge_base") / "wikipedia_search.sqlite"


def index_exists() -> bool:
    return INDEX_PATH.exists() and INDEX_PATH.stat().st_size > 0


def build_index(wiki_dir: Path = WIKI_DIR, index_path: Path = INDEX_PATH,
                progress=print) -> int:
    """
    Step 1: build into a temporary file (the old index keeps working meanwhile)
    Step 2: one row per article: file stem, title, body
    Step 3: optimise, then swap it in
    Returns the number of articles indexed.
    """
    files = sorted(wiki_dir.glob("*.txt")) if wiki_dir.is_dir() else []
    if not files:
        progress("No extracted Wikipedia articles found — extract a dump first.")
        return 0

    tmp = index_path.with_suffix(".building")
    if tmp.exists():
        tmp.unlink()
    db = sqlite3.connect(str(tmp))
    db.execute("PRAGMA journal_mode=OFF")
    db.execute("PRAGMA synchronous=OFF")
    db.execute(
        "CREATE VIRTUAL TABLE articles USING fts5("
        "stem UNINDEXED, title, body, tokenize='porter unicode61')"
    )

    # Step 2
    started, batch, count = time.time(), [], 0
    for i, path in enumerate(files, 1):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines = text.split("\n", 1)
        if lines[0].startswith("# "):
            title, body = lines[0][2:].strip(), (lines[1] if len(lines) > 1 else "")
        else:
            title, body = path.stem.replace("_", " "), text
        batch.append((path.stem, title, body))
        if len(batch) >= 2000:
            db.executemany("INSERT INTO articles VALUES (?, ?, ?)", batch)
            count += len(batch)
            batch.clear()
            progress(f"  Indexed {i:,} / {len(files):,} articles…")
    if batch:
        db.executemany("INSERT INTO articles VALUES (?, ?, ?)", batch)
        count += len(batch)

    # Step 3
    db.execute("INSERT INTO articles(articles) VALUES ('optimize')")
    db.commit()
    db.close()
    tmp.replace(index_path)
    progress(f"✓ Search index: {count:,} articles in {time.time() - started:.0f} s → {index_path}")
    return count


def _fts_query(query: str, any_word: bool = False) -> Optional[str]:
    """Typed words → a safe FTS5 query (every word, or any word)."""
    words = re.findall(r"\w+", query.lower())
    if not words:
        return None
    parts = [f'"{w}"' for w in words[:-1]]
    last = words[-1]
    parts.append(f'"{last}"*' if len(last) >= 3 else f'"{last}"')
    return (" OR " if any_word else " ").join(parts)


def search(query: str, limit: int = 40, index_path: Path = INDEX_PATH) -> List[Dict]:
    """
    [{"stem", "title", "snippet"}], best first.
    Every word must match; if nothing does, falls back to any word.
    """
    if not index_path.exists():
        return []
    db = sqlite3.connect(f"file:{index_path}?mode=ro", uri=True)
    try:
        for any_word in (False, True):
            q = _fts_query(query, any_word)
            if not q:
                return []
            try:
                rows = db.execute(
                    "SELECT stem, title, snippet(articles, 2, '', '', ' … ', 18) "
                    "FROM articles WHERE articles MATCH ? "
                    "ORDER BY bm25(articles, 0.0, 10.0, 1.0) LIMIT ?",
                    (q, limit),
                ).fetchall()
            except sqlite3.OperationalError:
                rows = []
            if rows:
                return [{"stem": s, "title": t, "snippet": " ".join(snip.split())}
                        for s, t, snip in rows]
        return []
    finally:
        db.close()
