"""
Search tab — your books, your notes and Wikipedia in one list
(core/library/search_all.py).

Results come in groups — In your books / Your notes / Wikipedia — and each
says where it's from ("Edible Wild Plants · p. 12 · plants"). Click one:
  book       the passage, the page itself as a picture, "Open the book"
  note       the passage from your note
  Wikipedia  the whole article

Desktop: results on the left, the reader on the right.
Phone:   results, then the reader full-screen with a back button.

Search runs on a background thread, 250 ms after you stop typing or straight
away on Enter. "Ask about this" hands the subject to the chat tab.
"""

import html
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QTextBrowser, QSplitter, QStackedWidget,
    QFrame,
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QUrl
from PySide6.QtGui import QDesktopServices

from core.app.platform_info import PHONE_LAYOUT
from core.library import wiki_lookup


class _SearchWorker(QThread):
    done = Signal(int, dict)      # request number, {"book": [...], "note": [...], "wikipedia": [...]}

    def __init__(self, number: int, query: str, knowledge):
        super().__init__()
        self.number, self.query, self.knowledge = number, query, knowledge

    def run(self):
        from core.library.search_all import search_everything
        try:
            results = search_everything(self.query, self.knowledge)
        except Exception:
            results = {}
        self.done.emit(self.number, results)


GROUPS = [("book", "In your books"), ("note", "Your notes"), ("wikipedia", "Wikipedia")]


class _ResultRow(QWidget):
    """Title, where it's from, then the matching words."""

    def __init__(self, title: str, snippet: str, where: str = ""):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)
        t = QLabel(title)
        t.setObjectName("wikiResultTitle")
        layout.addWidget(t)
        if where:
            w = QLabel(where)
            w.setObjectName("wikiResultWhere")
            layout.addWidget(w)
        s = QLabel(snippet)
        s.setObjectName("wikiResultSnippet")
        s.setWordWrap(True)
        layout.addWidget(s)


class _GroupHeader(QLabel):
    def __init__(self, text: str):
        super().__init__(text)
        self.setObjectName("wikiGroup")


class WikiSearchWidget(QWidget):
    ask_about = Signal(str)       # a subject → ask the chat tab about it
    ask_in = Signal(str, str)     # (book folder, subject) → ask the section that reads that folder

    def __init__(self, knowledge=None, parent=None):
        super().__init__(parent)
        self.setObjectName("wikiPanel")
        self.knowledge = knowledge
        self._request = 0
        self._workers = []
        self._current_title = ""
        self._current_file = ""
        self._current_domain = ""

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 8)
        outer.setSpacing(8)

        # Step 1: search box
        row = QHBoxLayout()
        self._box = QLineEdit()
        self._box.setObjectName("wikiSearch")
        self._box.setPlaceholderText("Search your books, notes and Wikipedia")
        self._box.setClearButtonEnabled(True)
        self._box.returnPressed.connect(self._search_now)
        self._box.textChanged.connect(lambda _: self._debounce.start())
        row.addWidget(self._box, 1)
        self._count = QLabel("")
        self._count.setObjectName("infoLabel")
        row.addWidget(self._count)
        outer.addLayout(row)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(250)
        self._debounce.timeout.connect(self._search_now)

        # Step 2: results list
        self._list = QListWidget()
        self._list.setObjectName("wikiResults")
        self._list.itemClicked.connect(self._open_item)
        self._list.itemActivated.connect(self._open_item)

        # Step 3: reader
        reader = QFrame()
        reader.setObjectName("wikiReader")
        rl = QVBoxLayout(reader)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(6)
        bar = QHBoxLayout()
        if PHONE_LAYOUT:
            back = QPushButton("< Results")
            back.setObjectName("navBtn")
            back.clicked.connect(lambda: self._stack.setCurrentIndex(0))
            bar.addWidget(back)
        bar.addStretch()
        self._open_book = QPushButton("Open the book")
        self._open_book.setObjectName("navBtn")
        self._open_book.hide()
        self._open_book.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self._current_file)))
        bar.addWidget(self._open_book)
        self._ask = QPushButton("Ask about this")
        self._ask.setObjectName("primaryBtn")
        self._ask.setEnabled(False)
        self._ask.clicked.connect(self._on_ask)
        bar.addWidget(self._ask)
        rl.addLayout(bar)
        self._text = QTextBrowser()
        self._text.setObjectName("wikiText")
        self._text.setOpenExternalLinks(False)
        rl.addWidget(self._text, 1)

        if PHONE_LAYOUT:
            self._stack = QStackedWidget()
            self._stack.addWidget(self._list)
            self._stack.addWidget(reader)
            outer.addWidget(self._stack, 1)
        else:
            split = QSplitter(Qt.Horizontal)
            split.addWidget(self._list)
            split.addWidget(reader)
            split.setSizes([340, 760])
            split.setStretchFactor(1, 1)
            outer.addWidget(split, 1)

        self._show_start()

    # ── States ─────────────────────────────────────────────────────────────

    def _show_start(self):
        n = wiki_lookup.article_count()
        self._count.setText(f"{n:,} articles" if n else "")
        intro = ("<p style='color:#a6a6a6'>Type anything above — a plant, a tool, a name. "
                 "Your books, your notes and Wikipedia are all searched; each result says "
                 "where it's from. Click one to read it here.</p>")
        if n and wiki_lookup.full_text_ready():
            self._text.setHtml(intro)
        elif n:
            self._text.setHtml(
                intro + "<p style='color:#a6a6a6'>Wikipedia: titles only for now. To search "
                "inside every article, build its index (a few minutes):</p>"
                "<pre>python tools/ingest.py --wiki-index</pre>")
        else:
            self._text.setHtml(
                intro + "<p><b>Wikipedia isn't set up yet</b> — only your books and notes "
                "are searched.</p>"
                "<p style='color:#a6a6a6'>The smaller Simple English one (about 360 MB):</p>"
                "<pre>python tools/ingest.py --download-wikipedia --extract-only</pre>"
                "<p style='color:#a6a6a6'>Or the 1 million most-linked English articles "
                "(downloads about 24 GB once; the result is about 10 GB):</p>"
                "<pre>python tools/ingest.py --download-wikipedia-full</pre>")

    def focus_search(self):
        self._box.setFocus()

    # ── Search ─────────────────────────────────────────────────────────────

    def _search_now(self):
        self._debounce.stop()
        q = self._box.text().strip()
        if not q:
            self._list.clear()
            self._show_start()
            return
        self._request += 1
        self._count.setText("Searching…")
        w = _SearchWorker(self._request, q, self.knowledge)
        w.done.connect(self._on_results)
        w.finished.connect(lambda w=w: self._workers.remove(w) if w in self._workers else None)
        self._workers.append(w)
        w.start()

    def _on_results(self, number: int, results: dict):
        if number != self._request:
            return                    # an older search finished late — ignore it
        self._list.clear()
        total = 0
        for kind, heading in GROUPS:
            group = results.get(kind) or []
            if not group:
                continue
            # Step 1: a heading row (not clickable)
            head = QListWidgetItem()
            head.setFlags(Qt.NoItemFlags)
            label = _GroupHeader(f"{heading} · {len(group)}")
            head.setSizeHint(label.sizeHint())
            self._list.addItem(head)
            self._list.setItemWidget(head, label)
            # Step 2: its results, each with where it's from
            for r in group:
                item = QListWidgetItem()
                item.setData(Qt.UserRole, r)
                where = r.get("where", "") if kind != "wikipedia" else ""
                row = _ResultRow(r["title"], r.get("snippet", ""), where)
                item.setSizeHint(row.sizeHint())
                self._list.addItem(item)
                self._list.setItemWidget(item, row)
                total += 1
        self._count.setText(f"{total} found" if total else "Nothing found")

    # ── Read ───────────────────────────────────────────────────────────────

    def _open_item(self, item: QListWidgetItem):
        r = item.data(Qt.UserRole)
        if not isinstance(r, dict):
            return                    # a heading
        if PHONE_LAYOUT:              # first, so the page picture fits the real width
            self._stack.setCurrentIndex(1)
        if r.get("kind") == "wikipedia":
            self._show_article(Path(r["path"]))
        else:
            self._show_passage(r)

    def _show_article(self, path: Path):
        text = wiki_lookup.read_article(path)
        lines = text.splitlines()
        title = lines[0][2:].strip() if lines and lines[0].startswith("# ") else path.stem.replace("_", " ")
        body = "\n".join(lines[1:]) if lines and lines[0].startswith("# ") else text
        paras = [p.strip() for p in body.split("\n\n") if p.strip()]
        self._text.setHtml(
            f"<h2>{html.escape(title)}</h2>"
            "<p style='color:#a6a6a6'>From: Wikipedia</p>" +
            "".join(f"<p>{html.escape(' '.join(p.split()))}</p>" for p in paras)
        )
        self._current_title = title
        self._current_file = ""
        self._current_domain = ""
        self._open_book.hide()
        self._ask.setEnabled(True)

    def _on_ask(self):
        if self._current_domain:
            self.ask_in.emit(self._current_domain, self._current_title)
        else:
            self.ask_about.emit(self._current_title)

    def _show_passage(self, r: dict):
        """A book passage (with its page as a picture) or a note."""
        parts = [f"<h2>{html.escape(r['title'])}</h2>",
                 f"<p style='color:#a6a6a6'>From: {html.escape(r.get('source', ''))}</p>"]
        parts += [f"<p>{html.escape(' '.join(p.split()))}</p>"
                  for p in (r.get("content") or "").split("\n\n") if p.strip()]
        if r.get("image"):
            width = max(200, min(620, self._text.viewport().width() - 40))
            parts.append(f"<p style='color:#a6a6a6'>The page:</p>"
                         f"<img src='{QUrl.fromLocalFile(str(Path(r['image']).resolve())).toString()}' "
                         f"width='{width}'>")
        self._text.setHtml("".join(parts))
        self._current_title = self._box.text().strip() or r["title"]
        self._current_file = r.get("path", "")
        self._current_domain = r.get("domain", "") if r.get("kind") == "book" else ""
        self._open_book.setVisible(bool(self._current_file) and not PHONE_LAYOUT)
        self._ask.setEnabled(True)
