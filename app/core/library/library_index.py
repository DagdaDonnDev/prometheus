"""
Word search over every book passage — the other half of library search.

Meaning search (ChromaDB + all-MiniLM-L6-v2) only ever read the first ~190
words of each 400-word passage (the model's limit), and misses exact names
("lye", "hemlock", "Bow drill"). This index reads all of every passage,
ranked by BM25 (the classic search-engine score). core/library/rag.py merges
the two lists.

Step 1: build — every passage from memory/chunks_fallback.json (written by
        every ingest) goes into a SQLite FTS5 table with English word stems
        ("plants" finds "plant"). Done automatically in the background when
        the chunks file is newer than the index (seconds to a minute), and
        after every ingest.
Step 2: search — the question's subject words, any of them, best first,
        limited to the section's book folders.

Kept in memory/library_search.sqlite. With it, the chunks file doesn't need
to be read into memory at startup any more (faster start, less memory).
"""

import json
import os
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional

INDEX_PATH = Path("memory/library_search.sqlite")
CHUNKS_PATH = Path("memory/chunks_fallback.json")
SKIP = {"wikipedia"}            # has its own search (core/library/wiki_index)

_STOP = {"the", "and", "for", "with", "that", "this", "from", "what", "how", "you", "your",
         "are", "was", "were", "can", "does", "did", "have", "has", "about", "into", "when",
         "where", "which", "who", "why", "will", "would", "should", "could", "there", "their",
         "them", "they", "then", "than", "some", "any", "make", "made", "tell", "show"}


def source_signature(path: Path = CHUNKS_PATH) -> str:
    """Size + modified time of the chunks file — the index is stale when it changes."""
    try:
        st = path.stat()
        return f"{st.st_size}:{int(st.st_mtime)}"
    except OSError:
        return ""


class LibraryIndex:
    def __init__(self, path: Path = INDEX_PATH):
        self.path = Path(path)
        self._lock = threading.Lock()
        self._db: Optional[sqlite3.Connection] = None

    # ── State ──────────────────────────────────────────────────────────────

    def _open(self) -> Optional[sqlite3.Connection]:
        if self._db is None and self.path.exists():
            try:
                self._db = sqlite3.connect(str(self.path), check_same_thread=False)
            except sqlite3.Error:
                self._db = None
        return self._db

    def signature(self) -> str:
        db = self._open()
        if db is None:
            return ""
        try:
            with self._lock:
                row = db.execute("SELECT value FROM meta WHERE key='signature'").fetchone()
            return row[0] if row else ""
        except sqlite3.Error:
            return ""

    def ready(self) -> bool:
        return bool(self.signature())

    def fresh(self, chunks_path: Path = CHUNKS_PATH) -> bool:
        """Built from the chunks file as it is now."""
        sig = source_signature(chunks_path)
        return bool(sig) and self.signature() == sig

    def close(self):
        if self._db is not None:
            try:
                self._db.close()
            except sqlite3.Error:
                pass
            self._db = None

    # ── Step 1 ─────────────────────────────────────────────────────────────

    def build(self, chunks: Iterable[Dict], signature: str = "", progress=None) -> int:
        """
        Write the index to a temporary file, then swap it in (a search
        running meanwhile keeps using the old one). Returns passages indexed.
        """
        tmp = self.path.with_suffix(".building")
        tmp.parent.mkdir(parents=True, exist_ok=True)
        if tmp.exists():
            tmp.unlink()
        db = sqlite3.connect(str(tmp))
        db.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
        db.execute("CREATE VIRTUAL TABLE passages USING fts5("
                   "content, domain UNINDEXED, source UNINDEXED, page UNINDEXED, "
                   "tokenize='porter unicode61')")
        n = 0
        batch = []
        for c in chunks:
            if c.get("domain") in SKIP or not c.get("content"):
                continue
            batch.append((c["content"], c.get("domain", ""), c.get("source", ""),
                          int(c.get("page_num", 0) or 0)))
            if len(batch) >= 2000:
                db.executemany("INSERT INTO passages VALUES (?,?,?,?)", batch)
                n += len(batch)
                batch = []
                if progress:
                    progress(n)
        if batch:
            db.executemany("INSERT INTO passages VALUES (?,?,?,?)", batch)
            n += len(batch)
        db.execute("INSERT INTO passages(passages) VALUES('optimize')")
        db.execute("INSERT INTO meta VALUES ('signature', ?)", (signature or f"built:{int(time.time())}",))
        db.execute("INSERT INTO meta VALUES ('count', ?)", (str(n),))
        db.commit()
        db.close()
        with self._lock:
            self.close()
            os.replace(tmp, self.path)
            self.__dict__.pop("_df", None)
        return n

    def build_from_file(self, chunks_path: Path = CHUNKS_PATH, progress=None) -> int:
        """Step 1 from memory/chunks_fallback.json."""
        chunks = json.loads(Path(chunks_path).read_text(encoding="utf-8", errors="replace"))
        return self.build(chunks, source_signature(chunks_path), progress)

    # ── Step 2 ─────────────────────────────────────────────────────────────

    @staticmethod
    def query_words(text: str) -> List[str]:
        """What to look for: the subject words, or the message's real words if it has none."""
        from core.ai.librarian import subject_words
        words = subject_words(text)
        if not words:
            words = [w for w in re.findall(r"[a-z][a-z'-]+", (text or "").lower())
                     if len(w) >= 3 and w not in _STOP]
        return [w.strip("'-") for w in words if w.strip("'-")][:12]

    def search(self, text: str, domains: Optional[List[str]] = None, n: int = 10) -> List[Dict]:
        """Best-matching passages: [{"content", "source", "domain", "page_num", "bm25"}]."""
        db = self._open()
        words = self.query_words(text)
        if db is None or not words:
            return []
        match = " OR ".join('"' + w.replace('"', "") + '"' for w in words)
        sql = "SELECT content, source, domain, page, bm25(passages) FROM passages WHERE passages MATCH ?"
        args: List = [match]
        if domains:
            sql += f" AND domain IN ({','.join('?' * len(domains))})"
            args += list(domains)
        sql += " ORDER BY bm25(passages) LIMIT ?"
        args.append(int(n))
        try:
            with self._lock:
                rows = db.execute(sql, args).fetchall()
        except sqlite3.Error:
            return []
        return [{"content": c, "source": s, "domain": d, "page_num": int(p or 0), "bm25": float(b)}
                for c, s, d, p, b in rows]

    def weights(self, words: List[str]) -> Dict[str, float]:
        """
        How telling each word is in this library (inverse document frequency):
        rare words ("soap", "hemlock") weigh more than common ones ("wood",
        "make"). A word in no passage at all weighs 0. Cached per word.
        """
        import math
        db = self._open()
        if db is None or not words:
            return {}
        cache = self.__dict__.setdefault("_df", {})
        try:
            with self._lock:
                if "__total__" not in cache:
                    row = db.execute("SELECT value FROM meta WHERE key='count'").fetchone()
                    cache["__total__"] = int(row[0]) if row else 0
                for w in words:
                    if w not in cache:
                        cache[w] = db.execute("SELECT count(*) FROM passages WHERE passages MATCH ?",
                                              ('"' + w.replace('"', "") + '"',)).fetchone()[0]
        except sqlite3.Error:
            return {}
        total = max(1, cache["__total__"])
        return {w: (math.log((total + 1) / (cache[w] + 1)) if cache[w] else 0.0) for w in words}

    def in_domain(self, domain: str, limit: int = 5000) -> List[Dict]:
        """Every passage of one folder (the Training Path's anchors read these)."""
        db = self._open()
        if db is None:
            return []
        try:
            with self._lock:
                rows = db.execute("SELECT content, source, domain, page FROM passages WHERE domain = ? "
                                  "LIMIT ?", (domain, limit)).fetchall()
        except sqlite3.Error:
            return []
        return [{"content": c, "source": s, "domain": d, "page_num": int(p or 0)} for c, s, d, p in rows]


def fuse(*ranked: List[Dict], k: int = 60) -> List[Dict]:
    """
    Reciprocal rank fusion: a passage near the top of either list (meaning or
    words) comes out near the top; one high in both comes first. Each result
    gets "relevance" from 0 to 1 (1 = the best of this search).
    """
    scores: Dict[str, float] = {}
    first: Dict[str, Dict] = {}
    for results in ranked:
        for rank, r in enumerate(results):
            key = r.get("content", "")[:120]
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank + 1)
            first.setdefault(key, r)
    if not scores:
        return []
    top = max(scores.values())
    out = []
    for key in sorted(scores, key=lambda x: -scores[x]):
        r = dict(first[key])
        r["relevance"] = round(scores[key] / top, 3)
        out.append(r)
    return out
