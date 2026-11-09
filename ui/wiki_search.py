"""
Wikipedia tab — search and read the offline Wikipedia, nothing else.

Desktop: results on the left, the article on the right.
Phone:   results, then the article full-screen with a back button.

Search runs on a background thread (listing ~100k titles takes a moment the
first time), 250 ms after you stop typing or straight away on Enter.
"Ask about this" hands the article to the chat tab.
"""

import html

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QTextBrowser, QSplitter, QStackedWidget,
    QFrame,
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer

from core.platform_info import PHONE_LAYOUT
from core import wiki_lookup


class _SearchWorker(QThread):
    done = Signal(int, list)      # request number, results

    def __init__(self, number: int, query: str, knowledge):
        super().__init__()
        self.number, self.query, self.knowledge = number, query, knowledge

    def run(self):
        try:
            results = wiki_lookup.search(self.query, limit=40, knowledge=self.knowledge)
        except Exception:
            results = []
        self.done.emit(self.number, results)


class _ResultRow(QWidget):
    """Title on one line, the article's opening under it."""

    def __init__(self, title: str, snippet: str):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)
        t = QLabel(title)
        t.setObjectName("wikiResultTitle")
        s = QLabel(snippet)
        s.setObjectName("wikiResultSnippet")
        s.setWordWrap(True)
        layout.addWidget(t)
        layout.addWidget(s)


class WikiSearchWidget(QWidget):
    ask_about = Signal(str)       # article title → ask the chat tab about it

    def __init__(self, knowledge=None, parent=None):
        super().__init__(parent)
        self.setObjectName("wikiPanel")
        self.knowledge = knowledge
        self._request = 0
        self._workers = []
        self._current_title = ""

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 8)
        outer.setSpacing(8)

        # Step 1: search box
        row = QHBoxLayout()
        self._box = QLineEdit()
        self._box.setObjectName("wikiSearch")
        self._box.setPlaceholderText("Search Wikipedia — a film, a person, a place, anything")
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
        self._ask = QPushButton("Ask about this")
        self._ask.setObjectName("primaryBtn")
        self._ask.setEnabled(False)
        self._ask.clicked.connect(lambda: self.ask_about.emit(self._current_title))
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
        if n and wiki_lookup.full_text_ready():
            self._count.setText(f"{n:,} articles")
            self._text.setHtml(
                "<p style='color:#a6a6a6'>Type anything above — a title, a name, a "
                "phrase. Every article is searched. Click a result to read it here.</p>")
        elif n:
            self._count.setText(f"{n:,} articles")
            self._text.setHtml(
                "<p style='color:#a6a6a6'>Searching titles only for now. To search inside "
                "every article, build the search index (a few minutes):</p>"
                "<pre>python ingest.py --wiki-index</pre>")
        else:
            self._count.setText("")
            self._text.setHtml(
                "<p><b>Wikipedia isn't set up yet.</b></p>"
                "<p style='color:#a6a6a6'>The 1 million most-linked English articles "
                "(downloads about 24 GB once; the result is about 10 GB):</p>"
                "<pre>python ingest.py --download-wikipedia-full</pre>"
                "<p style='color:#a6a6a6'>Or the smaller Simple English one (about 360 MB):</p>"
                "<pre>python ingest.py --download-wikipedia --extract-only</pre>")

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

    def _on_results(self, number: int, results: list):
        if number != self._request:
            return                    # an older search finished late — ignore it
        self._list.clear()
        for r in results:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, str(r["path"]))
            row = _ResultRow(r["title"], r["snippet"])
            item.setSizeHint(row.sizeHint())
            self._list.addItem(item)
            self._list.setItemWidget(item, row)
        self._count.setText(f"{len(results)} found" if results else "Nothing found")
        if not results and wiki_lookup.article_count() == 0:
            self._show_start()

    # ── Read ───────────────────────────────────────────────────────────────

    def _open_item(self, item: QListWidgetItem):
        from pathlib import Path
        path = Path(item.data(Qt.UserRole))
        text = wiki_lookup.read_article(path)
        lines = text.splitlines()
        title = lines[0][2:].strip() if lines and lines[0].startswith("# ") else path.stem.replace("_", " ")
        body = "\n".join(lines[1:]) if lines and lines[0].startswith("# ") else text
        paras = [p.strip() for p in body.split("\n\n") if p.strip()]
        self._text.setHtml(
            f"<h2>{html.escape(title)}</h2>" +
            "".join(f"<p>{html.escape(' '.join(p.split()))}</p>" for p in paras)
        )
        self._current_title = title
        self._ask.setEnabled(True)
        if PHONE_LAYOUT:
            self._stack.setCurrentIndex(1)
