"""
Obsidian (https://obsidian.md) — a mind map of you, and your notes as a source.

Everything is plain Markdown files in a vault folder; no Obsidian plugin or
network is needed. Prometheus writes only inside <vault>/Prometheus/:

  Me.md                      who you are — the properties at the top are
                             what Prometheus believes about you. Edit them in
                             Obsidian and the change comes back into the app.
  <Tab>.md                   one mind map per tab: links to that tab's chats
                             and the topics talked about
  Chats/<Tab> - <date> - <title>.md   each chat, linked to its tab and topics
  Topics/<topic>.md          a topic, linked from every chat that mentioned it

Obsidian's graph view draws the map from those links: Me → tabs → chats →
topics. The rest of the vault (your own notes) is read as a library source
for the knowledge tabs, and a note named in a chat message is given to the
chat tab — never the other way round: your notes are never changed.

No Qt here — core/ stays testable. The window calls sync() on close and on
Settings → Obsidian → Update now.
"""

import json
import os
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

FOLDER = "Prometheus"
STATE_PATH = Path("memory") / "obsidian_state.json"

# What Me.md holds: property name → (memory "user" key, is a list)
ME_FIELDS = [
    ("name",     "name",              False),
    ("location", "location_estimate", False),
    ("work",     "work",              False),
    ("day",      "day_count",         False),
    ("people",   "mentioned_people",  True),
    ("likes",    "likes",             True),
    ("dislikes", "dislikes",          True),
    ("skills",   "known_skills",      True),
    ("notes",    "notes",             True),
]

# Topics recognised in chats (phrase in a message → topic note), on top of
# Wikipedia titles and Training Path concepts
TOPIC_PHRASES = {
    "Water purification": ["purify water", "purifying water", "clean water", "boil water",
                           "filter water", "water filter", "drinking water"],
    "Fire": ["start a fire", "make fire", "fire starting", "firewood", "tinder", "kindling"],
    "Shelter": ["shelter", "lean-to", "tarp"],
    "First aid": ["first aid", "bleeding", "wound", "bandage", "tourniquet", "cpr", "burn"],
    "Food preservation": ["preserve food", "food preservation", "smoking meat", "salting",
                          "pickling", "canning", "dehydrat"],
    "Foraging": ["forage", "foraging", "wild plants", "edible plants", "mushroom"],
    "Hunting and trapping": ["hunting", "trap", "snare", "fishing"],
    "Navigation": ["navigate", "compass", "north star", "find north", "map reading"],
    "Farming": ["grow food", "crops", "seeds", "soil", "compost", "garden", "livestock"],
    "Electricity": ["circuit", "battery", "solar panel", "voltage", "generator", "wiring"],
    "Radio": ["radio", "antenna", "ham radio"],
    "Soap making": ["soap"],
    "Metalwork": ["forge", "smelt", "blacksmith", "welding"],
    "Woodwork": ["carpentry", "woodwork", "timber", "build a"],
    "Sleep": ["can't sleep", "sleep", "insomnia", "tired"],
    "Loneliness": ["lonely", "alone", "isolated", "miss my", "miss them"],
    "Stress": ["stressed", "anxious", "anxiety", "overwhelmed", "worried"],
    "Grief": ["grief", "grieving", "passed away", "died", "funeral"],
    "Work": ["my job", "at work", "my boss", "work today"],
    "Films and TV": ["film", "movie", "tv show", "series", "watched"],
    "Books": ["book", "novel", "reading"],
    "Music": ["song", "album", "band", "music"],
}

_BAD_NAME = re.compile(r'[\\/:*?"<>|#^\[\]]')
_lock = threading.RLock()
_vault: Dict[str, object] = {"path": "", "use_notes": True}


# ── Settings ────────────────────────────────────────────────────────────────

def set_vault(path: str, use_notes: bool = True):
    """Called at startup and when Settings change."""
    with _lock:
        _vault["path"] = (path or "").strip()
        _vault["use_notes"] = use_notes
        _notes_cache["checked"] = 0.0


def vault_path() -> Optional[Path]:
    p = str(_vault.get("path") or "")
    return Path(p) if p and Path(p).is_dir() else None


# ── A small YAML subset (Obsidian properties) ───────────────────────────────

def _quote(v: str) -> str:
    """Quote a value only when YAML would misread it."""
    s = str(v)
    if s == "" or re.search(r'[:#\[\]{},&*!|>\'"%@`]', s) or s.strip() != s or \
            s.lower() in ("yes", "no", "true", "false", "null", "~"):
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return s


def _unquote(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] == '"':
        return s[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    if len(s) >= 2 and s[0] == s[-1] == "'":
        return s[1:-1].replace("''", "'")
    return s


def dump_frontmatter(props: Dict[str, object]) -> str:
    lines = ["---"]
    for key, value in props.items():
        if isinstance(value, list):
            if not value:
                lines.append(f"{key}: []")
            else:
                lines.append(f"{key}:")
                lines.extend(f"  - {_quote(v)}" for v in value)
        elif value is None or value == "":
            lines.append(f"{key}:")
        else:
            lines.append(f"{key}: {_quote(value)}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def parse_frontmatter(text: str) -> Tuple[Dict[str, object], str]:
    """
    (properties, body). Understands what Obsidian writes:
      key: value      key: "quoted"      key: [a, b]      key:  +  "  - item" lines
    """
    if not text.startswith("---"):
        return {}, text
    end = re.search(r"^---\s*$", text[3:], re.M)
    if not end:
        return {}, text
    block = text[3:3 + end.start()]
    body = text[3 + end.end():].lstrip("\n")
    props: Dict[str, object] = {}
    key = None
    for raw in block.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        item = re.match(r"^\s*-\s*(.*)$", raw)
        if item and key is not None:
            if not isinstance(props.get(key), list):
                props[key] = []
            v = _unquote(item.group(1))
            if v:
                props[key].append(v)
            continue
        kv = re.match(r"^([\w -]+?)\s*:\s*(.*)$", raw)
        if not kv:
            continue
        key, value = kv.group(1).strip(), kv.group(2).strip()
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            props[key] = [_unquote(x) for x in re.findall(r'"[^"]*"|\'[^\']*\'|[^,]+', inner)
                          if _unquote(x)] if inner else []
        elif value == "":
            props[key] = None          # either empty or a list that follows
        else:
            props[key] = _unquote(value)
    return props, body


# ── State: what we wrote last time ──────────────────────────────────────────

def _load_state() -> Dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_state(state: Dict):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=1), encoding="utf-8")


def _write_if_changed(path: Path, text: str) -> bool:
    try:
        if path.read_text(encoding="utf-8") == text:
            return False
    except OSError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


def link(rel: str, label: str = "") -> str:
    """[[Prometheus/Chats/x|x]] — a full path, so your own notes called "Me"
    or "Survival" are never mixed up with these."""
    target = f"{FOLDER}/{rel[:-3] if rel.endswith('.md') else rel}"
    return f"[[{target}|{label}]]" if label else f"[[{target}]]"


def safe_name(text: str, limit: int = 60) -> str:
    """A file name Obsidian and Windows both accept."""
    t = _BAD_NAME.sub("", " ".join(str(text).split())).strip(" .")
    return (t[:limit].rstrip(" .") or "Untitled")


# ── Me.md: what it believes about you ───────────────────────────────────────

def _me_props(memory) -> Dict[str, object]:
    u = memory.data.get("user", {}) or {}
    props = {}
    for prop, key, is_list in ME_FIELDS:
        v = u.get(key)
        props[prop] = [str(x) for x in (v or []) if isinstance(x, (str, int, float))] if is_list \
            else ("" if v is None else v)
    return props


def read_back_me(memory, state: Dict) -> List[str]:
    """
    Bring edits made to Me.md in Obsidian back into memory.

    Step 1: nothing to do unless Me.md changed since we last wrote it
    Step 2: single values — what's in the file now wins
    Step 3: lists — merge: items you removed in Obsidian are removed, items you
            added are added, and anything learned in the app meanwhile stays
    Returns plain notes of what changed.
    """
    vault = vault_path()
    if not vault:
        return []
    me = vault / FOLDER / "Me.md"
    try:
        text = me.read_text(encoding="utf-8")
    except OSError:
        return []
    # Step 1
    if text == state.get("me_text"):
        return []
    props, _ = parse_frontmatter(text)
    before = state.get("me_props") or {}
    u = memory.data.setdefault("user", {})
    changed = []
    for prop, key, is_list in ME_FIELDS:
        if prop not in props:
            continue
        now = props[prop]
        if is_list:
            # Step 3
            now = [str(x) for x in (now or [])] if isinstance(now, list) else \
                ([str(now)] if now else [])
            was = before.get(prop, [])
            current = list(u.get(key) or [])
            removed = {x.lower() for x in was} - {x.lower() for x in now}
            merged = [x for x in current if str(x).lower() not in removed]
            for x in now:
                if x.lower() not in {str(m).lower() for m in merged}:
                    merged.append(x)
            if merged != current:
                u[key] = merged
                changed.append(prop)
        else:
            # Step 2
            value = "" if now is None else str(now).strip()
            if key == "day_count":
                try:
                    value = max(1, int(value))
                except ValueError:
                    continue
            elif not value:
                value = None
            if value != u.get(key):
                u[key] = value
                changed.append(prop)
    if changed:
        memory.save()
    return changed


def _me_note(memory, tab_names: List[str], assistant: str) -> str:
    props = _me_props(memory)
    name = props.get("name") or "Me"
    body = [
        f"# {name}",
        "",
        f"What {assistant} knows about you. **Edit the properties above** to fix",
        f"anything that's wrong — {assistant} reads them back when it next syncs.",
        "",
        "## Tabs",
        *[f"- {link(t, t)}" for t in tab_names],
    ]
    return dump_frontmatter(props) + "\n" + "\n".join(body) + "\n"


# ── Topics in a chat ────────────────────────────────────────────────────────

def topics_in(messages: List[Dict], limit: int = 8) -> List[str]:
    """
    Topics a chat touched (from its user messages):
      Step 1: phrases from TOPIC_PHRASES
      Step 2: Training Path concepts by their keywords
      Step 3: Wikipedia article titles the messages name
    """
    said = [m.get("content", "") for m in messages if m.get("role") == "user"]
    text = " ".join(said).lower()
    found: List[str] = []

    def add(t):
        t = safe_name(t)
        if t and t not in found:
            found.append(t)

    # Step 1
    for topic, phrases in TOPIC_PHRASES.items():
        if any(re.search(r"\b" + re.escape(p), text) for p in phrases):
            add(topic)
    # Step 2
    try:
        from core.training.axiom_seeds import CONCEPTS
        for c in CONCEPTS:
            if any(k in text for k in c.get("keywords", [])):
                add(c["name"])
    except Exception:
        pass
    # Step 3
    try:
        from core.wiki_lookup import find_articles
        for line in said:
            for title, _ in find_articles(line, max_articles=2):
                add(title)
    except Exception:
        pass
    return found[:limit]


# ── Export ──────────────────────────────────────────────────────────────────

def _chat_records(tab) -> List[Dict]:
    """Every chat in a tab, the open one included, oldest first."""
    chats = [c for c in tab.all_chats() if c.get("history")]
    return sorted(chats, key=lambda c: c.get("created", ""))


def _chat_note_name(tab, chat: Dict) -> str:
    date = (chat.get("created") or chat.get("updated") or "")[:10] or "undated"
    return safe_name(f"{tab.name} - {date} - {chat.get('title') or 'Chat'}", 90)


def own_notes_in(messages: List[Dict], limit: int = 5) -> List[str]:
    """Vault paths (no .md) of their own notes the chat's messages name."""
    vault = vault_path()
    if not vault:
        return []
    by_title = {}
    for path, (_, title, _) in _own_notes().items():
        by_title.setdefault(title, path)
    out: List[str] = []
    for m in messages:
        if m.get("role") != "user":
            continue
        for title, _ in notes_named_in(m.get("content", ""), max_notes=2, words=0):
            p = by_title.get(title)
            if p:
                rel = Path(p).relative_to(vault).with_suffix("").as_posix()
                if rel not in out:
                    out.append(rel)
    return out[:limit]


def _chat_note(tab, chat: Dict, topics: List[str], assistant: str) -> str:
    props = {"tab": tab.name, "created": (chat.get("created") or "")[:16],
             "updated": (chat.get("updated") or "")[:16], "topics": topics,
             "prometheus_chat": chat.get("id", "")}
    lines = [f"# {chat.get('title') or 'Chat'}", "",
             f"Tab: {link(safe_name(tab.name), tab.name)}" +
             ("  ·  Topics: " + ", ".join(link(f"Topics/{t}", t) for t in topics) if topics else ""),
             ""]
    mine = own_notes_in(chat.get("history", []))
    if mine:
        lines += ["Your notes: " + ", ".join(f"[[{p}|{Path(p).name}]]" for p in mine), ""]
    if chat.get("summary"):
        lines += [f"> Earlier in this chat: {chat['summary']}", ""]
    for m in chat.get("history", []):
        who = "**You:**" if m.get("role") == "user" else f"**{assistant}:**"
        lines += [f"{who} {m.get('content', '').strip()}", ""]
    return dump_frontmatter(props) + "\n" + "\n".join(lines)


def _label(note_name: str, tab_name: str) -> str:
    """'Survival - 2026-11-06 - Boiling water' → '6 Nov · Boiling water'."""
    rest = note_name[len(safe_name(tab_name)) + 3:] if note_name.startswith(safe_name(tab_name) + " - ") else note_name
    m = re.match(r"(\d{4})-(\d{2})-(\d{2}) - (.*)", rest)
    if not m:
        return rest
    try:
        d = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return f"{d.day} {d:%b} · {m.group(4)}"
    except ValueError:
        return rest


def _hub_note(tab, chat_names: List[str], topic_counts: Dict[str, int]) -> str:
    topics = sorted(topic_counts, key=lambda t: (-topic_counts[t], t))
    lines = [f"# {tab.name}", "", f"Part of {link('Me', 'Me')}.", ""]
    lines += ["## Topics", *([f"- {link('Topics/' + t, t)} ({topic_counts[t]})" for t in topics]
                             or ["- none yet"]), ""]
    lines += ["## Chats", *([f"- {link('Chats/' + n, _label(n, tab.name))}" for n in reversed(chat_names)]
                            or ["- none yet"]), ""]
    return dump_frontmatter({"tab": tab.name, "chats": len(chat_names)}) + "\n" + "\n".join(lines)


def _topic_note(topic: str, uses: List[Tuple[str, str]]) -> str:
    lines = [f"# {topic}", "", "Talked about in:"]
    lines += [f"- {link('Chats/' + chat, _label(chat, tab))} ({tab})" for tab, chat in uses]
    return "\n".join(lines) + "\n"


def sync(memory, tab_manager, assistant: str = "Prometheus") -> str:
    """
    Read back edits, then write the mind map. Returns a short plain status.

    Step 1: read Me.md edits back into memory (so they're never overwritten)
    Step 2: build every note in memory: Me, one hub per tab, chats, topics
    Step 3: write only the files whose text changed
    Step 4: remove chat/topic notes we wrote earlier that no longer exist —
            only if they're still exactly as we wrote them
    """
    vault = vault_path()
    if not vault:
        return "Choose your Obsidian vault folder first."
    with _lock:
        state = _load_state()
        root = vault / FOLDER

        # Step 1
        changed = read_back_me(memory, state)

        # Step 2
        tabs = [t for t in tab_manager.tabs if t.id not in ("wikipedia", "review") and hasattr(t, "all_chats")]
        files: Dict[str, str] = {}
        topic_uses: Dict[str, List[Tuple[str, str]]] = {}
        for tab in tabs:
            names, counts = [], {}
            for chat in _chat_records(tab):
                name = base = _chat_note_name(tab, chat)
                k = 2
                while f"Chats/{name}.md" in files:          # same day, same title
                    name, k = f"{base} ({k})", k + 1
                topics = topics_in(chat.get("history", []))
                files[f"Chats/{name}.md"] = _chat_note(tab, chat, topics, assistant)
                names.append(name)
                for t in topics:
                    counts[t] = counts.get(t, 0) + 1
                    topic_uses.setdefault(t, []).append((tab.name, name))
            files[f"{safe_name(tab.name)}.md"] = _hub_note(tab, names, counts)
        for topic, uses in topic_uses.items():
            files[f"Topics/{topic}.md"] = _topic_note(topic, uses)
        me_text = _me_note(memory, [safe_name(t.name) for t in tabs], assistant)
        files["Me.md"] = me_text

        # Step 3
        written = sum(_write_if_changed(root / rel, text) for rel, text in files.items())

        # Step 4
        removed = 0
        for rel, text in (state.get("written") or {}).items():
            if rel in files:
                continue
            p = root / rel
            try:
                if p.read_text(encoding="utf-8") == text:
                    p.unlink()
                    removed += 1
            except OSError:
                pass

        state.update(me_text=me_text, me_props=_me_props(memory), written=files,
                     synced=datetime.now().isoformat(timespec="seconds"))
        _save_state(state)

    parts = [f"{written} note{'s' if written != 1 else ''} updated" if written else "Up to date"]
    if removed:
        parts.append(f"{removed} removed")
    if changed:
        parts.append("your edits to Me read back (" + ", ".join(changed) + ")")
    return ", ".join(parts) + "."


def read_back_only(memory) -> List[str]:
    """At startup: take Me.md edits made while the app was closed."""
    if not vault_path():
        return []
    with _lock:
        state = _load_state()
        changed = read_back_me(memory, state)
        if changed:
            state["me_props"] = _me_props(memory)
            _save_state(state)
        return changed


# ── Your own notes as a source ──────────────────────────────────────────────

_notes_cache: Dict[str, object] = {"checked": 0.0, "root": "", "notes": {}}
_REFRESH_SECONDS = 30


def _own_notes() -> Dict[str, Tuple[float, str, str]]:
    """
    {path: (mtime, title, text)} for the vault's notes, outside Prometheus/
    and hidden folders (.obsidian, .trash). Re-listed at most every 30 s;
    only changed files are re-read.
    """
    vault = vault_path()
    if not vault or not _vault.get("use_notes"):
        return {}
    with _lock:
        if str(vault) != _notes_cache["root"]:
            _notes_cache.update(root=str(vault), notes={}, checked=0.0)
        if time.time() - _notes_cache["checked"] < _REFRESH_SECONDS:
            return _notes_cache["notes"]
        old = _notes_cache["notes"]
        notes = {}
        for dirpath, dirnames, filenames in os.walk(vault):
            rel = Path(dirpath).relative_to(vault)
            dirnames[:] = [d for d in dirnames if not d.startswith(".")
                           and not (rel == Path(".") and d == FOLDER)]
            for f in filenames:
                if not f.lower().endswith(".md"):
                    continue
                p = os.path.join(dirpath, f)
                try:
                    mtime = os.path.getmtime(p)
                except OSError:
                    continue
                if p in old and old[p][0] == mtime:
                    notes[p] = old[p]
                    continue
                try:
                    raw = Path(p).read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                _, body = parse_frontmatter(raw)
                notes[p] = (mtime, Path(p).stem, body)
        _notes_cache.update(notes=notes, checked=time.time())
        return notes


def note_count() -> int:
    return len(_own_notes())


_WORD = re.compile(r"[a-z0-9']{3,}")


def search_notes(query: str, n: int = 2, words: int = 150) -> List[Dict]:
    """
    Your notes that match a question, as library passages.
      score = shared words (title words count 3×), at least 3;
      best passage around them
    """
    notes = _own_notes()
    want = set(_WORD.findall(query.lower())) - {"the", "and", "how", "what", "you", "for", "with",
                                                "can", "does", "are", "was", "about", "this", "that"}
    if not notes or not want:
        return []
    scored = []
    for path, (_, title, text) in notes.items():
        t_words = set(_WORD.findall(title.lower()))
        body = set(_WORD.findall(text.lower()))
        title_hit = len(want & t_words)
        score = 3 * title_hit + len(want & body)
        if score >= 3:
            scored.append((score, title_hit, title, text))
    scored.sort(key=lambda x: -x[0])
    out = []
    for score, title_hit, title, text in scored[:n]:
        out.append({
            "content": _passage(text, want, words),
            "source": f"Obsidian — {title}",
            "domain": "personal",
            "confidence": {"level": "MEDIUM", "score": 70, "source": "personal_doc"},
            # its title names what was asked → ranked with the best sources
            "title_hit": title_hit > 0,
        })
    return out


def _passage(text: str, want: set, words: int) -> str:
    """The ~words-long stretch of a note with the most matching words."""
    tokens = text.split()
    if len(tokens) <= words:
        return " ".join(tokens)
    best, best_i = -1, 0
    step = max(1, words // 3)
    for i in range(0, len(tokens) - words + 1, step):
        hits = sum(1 for tok in tokens[i:i + words] if tok.lower().strip(".,;:!?()[]*#") in want)
        if hits > best:
            best, best_i = hits, i
    return " ".join(tokens[best_i:best_i + words]) + " …"


def notes_named_in(text: str, max_notes: int = 1, words: int = 80) -> List[Tuple[str, str]]:
    """
    For the chat tab (no search there): a note whose title the message names —
    'what did I write about Sourdough Starter'. Titles of two+ words match in
    any case; one-word titles only when Capitalised in the message.
    """
    notes = _own_notes()
    if not notes:
        return []
    low = text.lower()
    hits = []
    for _, (_, title, body) in notes.items():
        t = title.strip()
        if len(t) < 4:
            continue
        if " " in t:
            ok = re.search(r"\b" + re.escape(t.lower()) + r"\b", low)
        else:
            ok = re.search(r"\b" + re.escape(t) + r"\b", text) and t[:1].isupper()
        if ok:
            hits.append((len(t), t, " ".join(body.split()[:words])))
    hits.sort(key=lambda h: -h[0])
    return [(t, b) for _, t, b in hits[:max_notes]]
