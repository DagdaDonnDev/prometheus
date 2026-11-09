"""
What the person says about themselves — checked by them before it's used.

Lifecycle of a fact (memory/claims.sqlite):

  Stage 1  Capture   core/profile.extract() finds "my sister Kate" in a message.
                     It goes into `pending` with the exact words it came from,
                     the time and how sure the pattern is. Nothing pending is
                     ever shown to a model.
  Stage 2  Review    the Review tab lists pending claims: what was understood,
                     the original words, and Accept / Edit / Reject.
  Stage 3  Promote   Accept (or Edit then accept) writes it to the person's
                     profile (memory/user_memory.json → "user") and records it
                     in `verified` with verified_by_user = 1 and the original
                     words, so where it came from is never lost.
  Stage 4  Discard   Reject moves it to `rejected`. It's never promoted, and
                     the same claim isn't raised again.

Settings → You and Obsidian's Me note are the person's own edits, so they
go straight into the profile (they are the verification).
"""

import os
import sqlite3
import time
from dataclasses import dataclass
from typing import List, Optional

DB_PATH = os.path.join("memory", "claims.sqlite")

# Profile fields a claim can fill: field → (plain label, is a list)
FIELDS = {
    "name":              ("Your name", False),
    "location_estimate": ("Where you live", False),
    "work":              ("Your work", False),
    "mentioned_people":  ("Someone in your life", True),
    "likes":             ("Something you like", True),
    "dislikes":          ("Something you don't like", True),
    "known_skills":      ("Something you can do", True),
}


@dataclass
class Claim:
    field: str
    value: str
    note: str                 # how it reads: "Kate is your sister"
    utterance: str = ""       # the exact message it came from
    confidence: float = 0.7
    id: int = 0
    created: str = ""
    origin: str = "pattern"   # "pattern" (fixed wording) or "model" (noticed by the librarian)


def _db():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    for table, extra in (("pending", ""),
                         ("verified", ", verified_at TEXT, verified_by_user INTEGER DEFAULT 1"),
                         ("rejected", ", rejected_at TEXT")):
        db.execute(f"CREATE TABLE IF NOT EXISTS {table} ("
                   "id INTEGER PRIMARY KEY AUTOINCREMENT, field TEXT, value TEXT, note TEXT, "
                   f"utterance TEXT, confidence REAL, created TEXT{extra})")
        try:                                   # added later — older files lack it
            db.execute(f"ALTER TABLE {table} ADD COLUMN origin TEXT DEFAULT 'pattern'")
        except sqlite3.OperationalError:
            pass
    return db


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _known(db, field: str, value: str) -> bool:
    """Already waiting, accepted or rejected — don't raise it again."""
    for table in ("pending", "verified", "rejected"):
        if db.execute(f"SELECT 1 FROM {table} WHERE field=? AND lower(value)=lower(?)",
                      (field, value)).fetchone():
            return True
    return False


# ── Stage 1 ─────────────────────────────────────────────────────────────────

def stage(claims: List[Claim], memory=None) -> List[Claim]:
    """Add new claims to the review list. Returns the ones actually added."""
    if not claims:
        return []
    u = (getattr(memory, "data", {}) or {}).get("user", {}) if memory else {}
    added = []
    with _db() as db:
        for c in claims:
            # Already in the profile (set in Settings, or accepted before)
            have = u.get(c.field)
            if (isinstance(have, list) and any(str(x).lower() == c.value.lower() for x in have)) or \
                    (isinstance(have, str) and have.lower() == c.value.lower()):
                continue
            if _known(db, c.field, c.value):
                continue
            c.created = _now()
            cur = db.execute("INSERT INTO pending (field, value, note, utterance, confidence, created, origin) "
                             "VALUES (?,?,?,?,?,?,?)",
                             (c.field, c.value, c.note, c.utterance, c.confidence, c.created, c.origin))
            c.id = cur.lastrowid
            added.append(c)
    return added


# ── Stage 2 ─────────────────────────────────────────────────────────────────

def pending() -> List[Claim]:
    """Waiting for review, oldest first."""
    if not os.path.exists(DB_PATH):
        return []
    with _db() as db:
        rows = db.execute("SELECT id, field, value, note, utterance, confidence, created, origin "
                          "FROM pending ORDER BY id").fetchall()
    return [Claim(field=f, value=v, note=n, utterance=u, confidence=c, id=i, created=t,
                  origin=o or "pattern")
            for i, f, v, n, u, c, t, o in rows]


def pending_count() -> int:
    if not os.path.exists(DB_PATH):
        return 0
    with _db() as db:
        return db.execute("SELECT COUNT(*) FROM pending").fetchone()[0]


def _take(db, claim_id: int) -> Optional[Claim]:
    row = db.execute("SELECT id, field, value, note, utterance, confidence, created, origin "
                     "FROM pending WHERE id=?", (claim_id,)).fetchone()
    if not row:
        return None
    db.execute("DELETE FROM pending WHERE id=?", (claim_id,))
    i, f, v, n, u, c, t, o = row
    return Claim(field=f, value=v, note=n, utterance=u, confidence=c, id=i, created=t,
                 origin=o or "pattern")


# ── Stage 3 ─────────────────────────────────────────────────────────────────

def accept(claim_id: int, memory, edited_value: str = "") -> Optional[Claim]:
    """
    Promote a claim into the profile (optionally as edited). Records it as
    verified by the person, keeping the words it came from.
    """
    with _db() as db:
        c = _take(db, claim_id)
        if c is None:
            return None
        if edited_value.strip():
            c.value = " ".join(edited_value.split())
        db.execute("INSERT INTO verified (field, value, note, utterance, confidence, created, "
                   "verified_at, verified_by_user, origin) VALUES (?,?,?,?,?,?,?,1,?)",
                   (c.field, c.value, c.note, c.utterance, c.confidence, c.created, _now(), c.origin))
    u = memory.data.setdefault("user", {})
    _, is_list = FIELDS.get(c.field, ("", True))
    if is_list:
        items = u.setdefault(c.field, [])
        if not any(str(x).lower() == c.value.lower() for x in items):
            items.append(c.value)
    else:
        u[c.field] = c.value
    memory.save()
    return c


# ── Stage 4 ─────────────────────────────────────────────────────────────────

def reject(claim_id: int) -> Optional[Claim]:
    """Never promoted; kept so the same claim isn't raised again."""
    with _db() as db:
        c = _take(db, claim_id)
        if c is None:
            return None
        db.execute("INSERT INTO rejected (field, value, note, utterance, confidence, created, "
                   "rejected_at, origin) VALUES (?,?,?,?,?,?,?,?)",
                   (c.field, c.value, c.note, c.utterance, c.confidence, c.created, _now(), c.origin))
    return c


def provenance(field: str, value: str) -> str:
    """The words a verified fact came from ('' if it was typed in Settings)."""
    if not os.path.exists(DB_PATH):
        return ""
    with _db() as db:
        row = db.execute("SELECT utterance FROM verified WHERE field=? AND lower(value)=lower(?) "
                         "ORDER BY id DESC", (field, value)).fetchone()
    return row[0] if row else ""
