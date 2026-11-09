"""
English Wikipedia — the most linked-to N articles (default 1,000,000), in one
SQLite file with full-text search. Built once, offline afterwards.

    python ingest.py --download-wikipedia-full                 # download + build, 1M articles
    python ingest.py --download-wikipedia-full --top 500000    # a smaller one
    python ingest.py --wikipedia-full <dump.xml.bz2>           # a dump you already have

Uses the "multistream" dump (about 24 GB): it's split into thousands of small
bz2 pieces, and its index says where each starts, so every CPU core can read a
different part at once. The dump can be deleted afterwards.

How the N articles are chosen:
  Pass 1  every article's links are counted — how many other articles link
          to each one (links to a redirect count for its target). That's a
          good measure of how widely known a thing is: Titanfall 2 is in,
          a stub about one village's 1950s council isn't.
          Counting ~500 million links in Python would need gigabytes of
          memory, so counts go into two fixed tables of 67M slots by hash
          (a count-min sketch, 512 MB) — a slot collision can only raise a
          count, and taking the smaller of the two keeps that rare.
  Pass 2  the top N are cleaned to plain text (reference sections dropped,
          capped at 5,000 words) and stored. Disambiguation pages are left out.

The database (knowledge_base/wikipedia_full.sqlite):
  pages(key, stem, title, body, links)   key = lower-case title key (core/wikitext.title_key)
  aliases(key → target)                  every title and every redirect to a kept article
  articles                               FTS5 over title + body (same shape core/wiki_index reads)

Resumable: the build goes to <name>.building; finished pieces are recorded,
so running the same command again carries on where it stopped.
"""

import bz2
import hashlib
import html
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

DB_NAME = "wikipedia_full.sqlite"
BASE_URL = "https://dumps.wikimedia.org/enwiki/latest/"
DUMP_NAME = "enwiki-latest-pages-articles-multistream.xml.bz2"
INDEX_NAME = "enwiki-latest-pages-articles-multistream-index.txt.bz2"
SUMS_NAME = "enwiki-latest-sha1sums.txt"

SKETCH_BITS = 26                     # 2^26 slots × 2 tables × 4 bytes = 512 MB
STREAMS_PER_JOB = 50                 # ~5,000 pages per piece of work
MAX_WORDS = 5000

_PAGE = re.compile(r"<page>(.*?)</page>", re.S)
_TITLE = re.compile(r"<title>(.*?)</title>", re.S)
_NS = re.compile(r"<ns>(\d+)</ns>")
_REDIRECT = re.compile(r'<redirect title="([^"]*)"')
_TEXT = re.compile(r"<text[^>]*>(.*?)</text>", re.S)
_LINK = re.compile(r"\[\[([^\[\]|#<>{}\n]{1,250})(?:[|#][^\]]*)?\]\]")
_DISAMBIG = re.compile(r"\{\{\s*(disambig|dab|hndis|geodis|set index|surname|given name)[^}]*\}\}", re.I)
# Link prefixes that aren't articles ([[File:…]], [[Category:…]], [[fr:…]] …)
_NOT_ARTICLE = {"file", "image", "category", "wikipedia", "wp", "template", "help", "portal",
                "user", "talk", "special", "media", "wikt", "wiktionary", "commons", "draft",
                "module", "mos", "w", "meta", "m", "b", "n", "q", "s", "v", "voy", "species",
                "d", "mw", "phab", "user talk", "template talk", "wikisource", "wikiquote"}


def _h64(key: str) -> int:
    return int.from_bytes(hashlib.blake2b(key.encode("utf-8", "replace"), digest_size=8).digest(), "little")


def _link_key(target: str) -> Optional[str]:
    from core.wikitext import title_key
    t = target.strip()
    if ":" in t:
        prefix = t.split(":", 1)[0].strip().lower()
        if prefix in _NOT_ARTICLE or (len(prefix) <= 3 and prefix.isalpha()):
            return None
    k = title_key(t)
    return k or None


def _pages(data: str) -> Iterator[Tuple[str, int, str, str]]:
    """(title, namespace, redirect target or "", raw wikitext) for each page in a piece."""
    for m in _PAGE.finditer(data):
        page = m.group(1)
        t = _TITLE.search(page)
        n = _NS.search(page)
        if not t or not n:
            continue
        r = _REDIRECT.search(page)
        x = _TEXT.search(page)
        yield (html.unescape(t.group(1)), int(n.group(1)),
               html.unescape(r.group(1)) if r else "", html.unescape(x.group(1)) if x else "")


def _read_piece(dump: str, start: int, end: int) -> str:
    with open(dump, "rb") as f:
        f.seek(start)
        raw = f.read(end - start)
    try:
        return bz2.decompress(raw).decode("utf-8", "replace")
    except (OSError, ValueError):
        return ""


# ── Pass 1: count links (runs in worker processes) ──────────────────────────

def _scan(job):
    """
    One piece of the dump → (article hashes, link slot counts for both
    tables, redirect (from, to) hashes). Plain lists/arrays only, so it
    pickles cheaply back to the main process.
    """
    import numpy as np
    from core.wikitext import title_key
    dump, start, end = job
    mask = (1 << SKETCH_BITS) - 1
    arts, links, red_src, red_tgt = [], [], [], []
    for title, ns, redirect, text in _pages(_read_piece(dump, start, end)):
        if ns != 0:
            continue
        key = title_key(title)
        if not key:
            continue
        if redirect:
            tk = _link_key(redirect)
            if tk:
                red_src.append(_h64(key))
                red_tgt.append(_h64(tk))
            continue
        if _DISAMBIG.search(text[:3000]) or _DISAMBIG.search(text[-3000:]):
            continue
        arts.append(_h64(key))
        for lm in _LINK.finditer(text):
            lk = _link_key(lm.group(1))
            if lk and lk != key:
                links.append(_h64(lk))
    h = np.array(links, dtype=np.uint64)
    u1, c1 = np.unique((h & np.uint64(mask)).astype(np.int64), return_counts=True)
    u2, c2 = np.unique(((h >> np.uint64(32)) & np.uint64(mask)).astype(np.int64), return_counts=True)
    return (np.array(arts, dtype=np.uint64), u1, c1, u2, c2,
            np.array(red_src, dtype=np.uint64), np.array(red_tgt, dtype=np.uint64))


# ── Pass 2: extract the chosen articles (runs in worker processes) ──────────

_SELECTED = None


def _init_extract(selected):
    global _SELECTED
    _SELECTED = selected


def _extract(job):
    """One piece → (its start, [(key, title, body)] for chosen articles, [(redirect key, target key)])."""
    import numpy as np
    from core.wikitext import clean_wikitext, title_key
    dump, start, end = job
    kept, redirects = [], []
    for title, ns, redirect, text in _pages(_read_piece(dump, start, end)):
        if ns != 0:
            continue
        key = title_key(title)
        if not key:
            continue
        if redirect:
            tk = _link_key(redirect)
            if tk:
                redirects.append((key, tk))
            continue
        h = np.uint64(_h64(key))
        i = int(np.searchsorted(_SELECTED, h))
        if i < len(_SELECTED) and _SELECTED[i] == h:
            body = clean_wikitext(text, cut_tail=True, max_words=MAX_WORDS)
            if len(body.split()) >= 30:
                kept.append((key, title, body))
    return start, kept, redirects


# ── The build ───────────────────────────────────────────────────────────────

def read_index(index_path: Path, dump_size: int) -> List[Tuple[int, int]]:
    """Byte ranges of the dump's pieces, STREAMS_PER_JOB streams each."""
    offsets, last = [], -1
    opener = bz2.open if str(index_path).endswith(".bz2") else open
    with opener(index_path, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            head = line.split(":", 1)[0]
            if head.isdigit():
                off = int(head)
                if off != last:
                    offsets.append(off)
                    last = off
    offsets.append(dump_size)
    jobs = []
    for i in range(0, len(offsets) - 1, STREAMS_PER_JOB):
        jobs.append((offsets[i], offsets[min(i + STREAMS_PER_JOB, len(offsets) - 1)]))
    return jobs


def _run(fn, jobs, workers: int, init=None, initargs=()):
    """Map fn over jobs on `workers` processes (1 = here, for tests)."""
    if workers <= 1:
        if init:
            init(*initargs)
        for j in jobs:
            yield fn(j)
        return
    import multiprocessing as mp
    with mp.get_context("spawn" if os.name == "nt" else "fork").Pool(
            workers, initializer=init, initargs=initargs) as pool:
        for r in pool.imap_unordered(fn, jobs, chunksize=1):
            yield r


def _say_progress(progress, label, done, total, started):
    elapsed = time.time() - started
    eta = elapsed / done * (total - done) if done else 0
    progress(f"  {label}: {done:,} / {total:,} pieces · {elapsed / 60:.0f} min so far, "
             f"about {eta / 60:.0f} min to go")


def build(dump: Path, index: Path, db_path: Path, top: int = 1_000_000,
          workers: int = 0, progress=print) -> int:
    """
    Step 1: split the dump into pieces from its index
    Step 2: pass 1 — count links; choose the top N (saved, so a rerun skips this)
    Step 3: pass 2 — extract and store the chosen articles (resumable per piece)
    Step 4: aliases (titles + redirects) and the full-text index
    Step 5: swap the finished file in
    Returns the number of articles stored.
    """
    import numpy as np
    workers = workers or max(1, (os.cpu_count() or 2) - 1)
    building = db_path.with_suffix(".building")
    chosen_file = db_path.with_suffix(".chosen.npy")

    # Step 1
    jobs = [(str(dump), a, b) for a, b in read_index(index, dump.stat().st_size)]
    progress(f"  {len(jobs):,} pieces, {workers} worker process(es)")

    # Step 2
    if chosen_file.exists():
        selected = np.load(chosen_file)
        progress(f"  Pass 1 already done: {len(selected):,} articles chosen")
    else:
        mask = (1 << SKETCH_BITS) - 1
        s1 = np.zeros(1 << SKETCH_BITS, dtype=np.uint32)
        s2 = np.zeros(1 << SKETCH_BITS, dtype=np.uint32)
        arts, rsrc, rtgt = [], [], []
        started = time.time()
        for n, (a, u1, c1, u2, c2, rs, rt) in enumerate(_run(_scan, jobs, workers), 1):
            s1[u1] += c1.astype(np.uint32)
            s2[u2] += c2.astype(np.uint32)
            arts.append(a)
            rsrc.append(rs)
            rtgt.append(rt)
            if n % 100 == 0 or n == len(jobs):
                _say_progress(progress, "Pass 1 (counting links)", n, len(jobs), started)
        arts = np.concatenate(arts) if arts else np.zeros(0, np.uint64)
        rsrc = np.concatenate(rsrc) if rsrc else np.zeros(0, np.uint64)
        rtgt = np.concatenate(rtgt) if rtgt else np.zeros(0, np.uint64)

        def est(h):
            m = np.uint64(mask)
            return np.minimum(s1[(h & m).astype(np.int64)], s2[((h >> np.uint64(32)) & m).astype(np.int64)])

        score = est(arts).astype(np.int64)
        # Links to a redirect ("BT-7274") count for its target ("Titanfall 2")
        if len(rsrc):
            tgt_u, inv = np.unique(rtgt, return_inverse=True)
            extra = np.bincount(inv, weights=est(rsrc).astype(np.float64))
            pos = np.searchsorted(tgt_u, arts)
            pos[pos >= len(tgt_u)] = 0
            hit = tgt_u[pos] == arts
            score[hit] += extra[pos[hit]].astype(np.int64)
        if len(arts) > top:
            idx = np.argpartition(-score, top - 1)[:top]
            selected = np.sort(arts[idx])
        else:
            selected = np.sort(arts)
        del s1, s2
        np.save(chosen_file, selected)
        progress(f"  Pass 1 done: {len(arts):,} articles, keeping the {len(selected):,} most linked-to")

    # Step 3
    db = sqlite3.connect(str(building))
    db.execute("PRAGMA journal_mode=OFF")
    db.execute("PRAGMA synchronous=OFF")
    db.execute("CREATE TABLE IF NOT EXISTS pages (key TEXT PRIMARY KEY, stem TEXT, title TEXT, body TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS redirects (src TEXT, tgt TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS done_jobs (start INTEGER PRIMARY KEY)")
    done = {r[0] for r in db.execute("SELECT start FROM done_jobs")}
    todo = [j for j in jobs if j[1] not in done]
    if done:
        progress(f"  Carrying on: {len(done):,} pieces already stored")
    started = time.time()
    for n, (start, kept, redirects) in enumerate(_run(_extract, todo, workers, _init_extract, (selected,)), 1):
        db.executemany("INSERT OR REPLACE INTO pages (key, stem, title, body) VALUES (?, ?, ?, ?)",
                       [(k, k, t, b) for k, t, b in kept])
        db.executemany("INSERT INTO redirects VALUES (?, ?)", redirects)
        db.execute("INSERT OR IGNORE INTO done_jobs VALUES (?)", (start,))   # this piece is stored
        if n % 50 == 0 or n == len(todo):
            db.commit()
            _say_progress(progress, "Pass 2 (extracting articles)", n + len(done), len(jobs), started)
    db.commit()

    # Step 4
    progress("  Building the title list and the full-text search (this takes a while)…")
    db.execute("CREATE TABLE IF NOT EXISTS aliases (key TEXT PRIMARY KEY, target TEXT)")
    db.execute("INSERT OR IGNORE INTO aliases SELECT key, key FROM pages")
    db.execute("INSERT OR IGNORE INTO aliases SELECT r.src, r.tgt FROM redirects r "
               "JOIN pages p ON p.key = r.tgt")
    db.execute("DROP TABLE redirects")
    db.execute("DROP TABLE IF EXISTS articles")
    db.execute("CREATE VIRTUAL TABLE articles USING fts5(stem UNINDEXED, title, body, "
               "content='pages', content_rowid='rowid', tokenize='porter unicode61')")
    db.execute("INSERT INTO articles(articles) VALUES ('rebuild')")
    db.execute("INSERT INTO articles(articles) VALUES ('optimize')")
    count = db.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
    db.execute("CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT)")
    db.execute("INSERT OR REPLACE INTO meta VALUES ('articles', ?)", (str(count),))
    db.execute("INSERT OR REPLACE INTO meta VALUES ('built', ?)", (time.strftime("%Y-%m-%d"),))
    db.commit()
    db.close()

    # Step 5
    os.replace(building, db_path)
    chosen_file.unlink(missing_ok=True)
    size = db_path.stat().st_size / 1e9
    progress(f"✓ {count:,} articles in {db_path} ({size:.1f} GB)")
    return count
