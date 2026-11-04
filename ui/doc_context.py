"""
Document Context Manager
=========================
Lets the user attach PDFs, text files, images, and other documents
as personal context — medical records, local maps, personal notes,
hand-written guides, anything relevant to their specific situation.

These documents are:
  - Indexed into a SEPARATE personal ChromaDB collection
  - Searched alongside the main knowledge base
  - Tagged as personal context in confidence scoring
  - Persisted across sessions
  - Deletable without touching the main knowledge base

This is different from the main knowledge base ingestion (ingest.py).
That is for reference library sources.
This is for YOUR specific documents.
"""

import os
import json
import shutil
import hashlib
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QScrollArea, QFileDialog,
    QListWidget, QListWidgetItem, QSizePolicy,
    QMessageBox, QProgressBar, QDialog, QTextEdit,
    QLineEdit, QComboBox
)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QFont, QDragEnterEvent, QDropEvent


# ── Paths ──────────────────────────────────────────────────────────────────

PERSONAL_DOCS_DIR    = Path("memory/personal_docs")
PERSONAL_DB_PATH     = Path("memory/personal_chroma_db")
PERSONAL_INDEX_PATH  = Path("memory/personal_docs_index.json")

SUPPORTED_EXTENSIONS = {
    ".pdf":  "PDF Document",
    ".txt":  "Text File",
    ".md":   "Markdown",
    ".doc":  "Word Document",
    ".docx": "Word Document",
    ".html": "Web Page",
    ".htm":  "Web Page",
    ".csv":  "Spreadsheet",
    ".json": "JSON Data",
    ".png":  "Image (OCR)",
    ".jpg":  "Image (OCR)",
    ".jpeg": "Image (OCR)",
}


# ── Document index ─────────────────────────────────────────────────────────

class PersonalDocIndex:
    """Tracks which personal documents have been indexed."""

    def __init__(self):
        PERSONAL_DOCS_DIR.mkdir(parents=True, exist_ok=True)
        self._index: Dict[str, Dict] = {}
        self._load()

    def _load(self):
        if PERSONAL_INDEX_PATH.exists():
            try:
                self._index = json.loads(PERSONAL_INDEX_PATH.read_text())
            except Exception:
                self._index = {}

    def _save(self):
        PERSONAL_INDEX_PATH.write_text(json.dumps(self._index, indent=2))

    def add(self, file_hash: str, info: Dict):
        self._index[file_hash] = info
        self._save()

    def remove(self, file_hash: str):
        self._index.pop(file_hash, None)
        self._save()

    def exists(self, file_hash: str) -> bool:
        return file_hash in self._index

    def all_docs(self) -> List[Dict]:
        return list(self._index.values())

    def get(self, file_hash: str) -> Optional[Dict]:
        return self._index.get(file_hash)


# ── Text extraction ────────────────────────────────────────────────────────

def extract_text(file_path: Path) -> Tuple[str, str]:
    """
    Extract text from a file.
    Returns (text, extraction_method) tuple.
    """
    suffix = file_path.suffix.lower()

    if suffix == ".pdf":
        return _extract_pdf(file_path)

    elif suffix in (".txt", ".md", ".csv", ".json"):
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
            return text, "text"
        except Exception as e:
            return "", f"error: {e}"

    elif suffix in (".doc", ".docx"):
        return _extract_docx(file_path)

    elif suffix in (".html", ".htm"):
        return _extract_html(file_path)

    elif suffix in (".png", ".jpg", ".jpeg"):
        return _extract_image_ocr(file_path)

    return "", "unsupported"


def _extract_pdf(path: Path) -> Tuple[str, str]:
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(str(path))
        pages = []
        for page_num, page in enumerate(doc):
            text = page.get_text()
            if text.strip():
                pages.append(f"[Page {page_num + 1}]\n{text}")
        doc.close()
        return "\n\n".join(pages), "pdf"
    except ImportError:
        return "", "PyMuPDF not installed (pip install PyMuPDF)"
    except Exception as e:
        return "", f"pdf error: {e}"


def _extract_docx(path: Path) -> Tuple[str, str]:
    try:
        import docx
        doc = docx.Document(str(path))
        text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        return text, "docx"
    except ImportError:
        return "", "python-docx not installed (pip install python-docx)"
    except Exception as e:
        return "", f"docx error: {e}"


def _extract_html(path: Path) -> Tuple[str, str]:
    try:
        from bs4 import BeautifulSoup
        html = path.read_text(encoding="utf-8", errors="replace")
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        return soup.get_text(separator="\n", strip=True), "html"
    except ImportError:
        # Fallback: strip tags manually
        import re
        html = path.read_text(encoding="utf-8", errors="replace")
        text = re.sub(r'<[^>]+>', ' ', html)
        text = re.sub(r'\s+', ' ', text).strip()
        return text, "html_basic"
    except Exception as e:
        return "", f"html error: {e}"


def _extract_image_ocr(path: Path) -> Tuple[str, str]:
    """OCR an image using tesseract if available."""
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(path)
        text = pytesseract.image_to_string(img)
        return text, "ocr"
    except ImportError:
        return "", "OCR requires: pip install pytesseract pillow (and tesseract binary)"
    except Exception as e:
        return "", f"ocr error: {e}"


# ── Indexing worker ────────────────────────────────────────────────────────

class IndexWorker(QThread):
    """Indexes a document into the personal ChromaDB collection."""
    progress = Signal(str)
    finished = Signal(bool, str)  # success, message

    def __init__(self, file_path: Path, doc_info: Dict, index: PersonalDocIndex):
        super().__init__()
        self.file_path = file_path
        self.doc_info  = doc_info
        self.index     = index

    def run(self):
        try:
            self.progress.emit(f"Extracting text from {self.file_path.name}...")
            text, method = extract_text(self.file_path)

            if not text or len(text.strip()) < 50:
                self.finished.emit(
                    False,
                    f"Could not extract text: {method}"
                )
                return

            word_count = len(text.split())
            self.progress.emit(
                f"Extracted {word_count:,} words ({method}). Indexing..."
            )

            # Chunk the text
            chunks = self._chunk(text, self.doc_info["source_name"])

            # Try to add to ChromaDB
            try:
                self._index_to_chroma(chunks)
                self.doc_info["chunks"] = len(chunks)
                self.doc_info["word_count"] = word_count
                self.doc_info["extraction_method"] = method
                self.doc_info["indexed"] = True
                self.index.add(self.doc_info["hash"], self.doc_info)
                self.finished.emit(
                    True,
                    f"Indexed {len(chunks)} chunks from {self.file_path.name}"
                )
            except Exception as e:
                # Save without vector indexing — keyword search still works
                self.doc_info["chunks"] = 0
                self.doc_info["word_count"] = word_count
                self.doc_info["extraction_method"] = method
                self.doc_info["indexed"] = False
                self.doc_info["text_cache"] = text[:50000]  # cache for keyword search
                self.index.add(self.doc_info["hash"], self.doc_info)
                self.finished.emit(
                    True,
                    f"Saved {self.file_path.name} (keyword search only — ChromaDB unavailable)"
                )

        except Exception as e:
            self.finished.emit(False, f"Error: {e}")

    def _chunk(self, text: str, source: str, size: int = 400, overlap: int = 50) -> List[Dict]:
        import re
        text = re.sub(r'\s+', ' ', text).strip()
        words = text.split()
        chunks = []
        step = size - overlap
        for i in range(0, len(words), step):
            chunk_words = words[i:i + size]
            if len(chunk_words) < 20:
                continue
            chunks.append({
                "id": f"personal_{source}_{i}",
                "content": " ".join(chunk_words),
                "source": source,
                "domain": "personal",
            })
        return chunks

    def _index_to_chroma(self, chunks: List[Dict]):
        from sentence_transformers import SentenceTransformer
        import chromadb

        embedder = SentenceTransformer(
            "all-MiniLM-L6-v2",
            cache_folder="memory/model_cache"
        )
        client = chromadb.PersistentClient(path=str(PERSONAL_DB_PATH))
        collection = client.get_or_create_collection(
            "prometheus_personal",
            metadata={"hnsw:space": "cosine"}
        )

        texts = [c["content"] for c in chunks]
        ids   = [c["id"] for c in chunks]
        metas = [{"source": c["source"], "domain": "personal"} for c in chunks]

        batch_size = 64
        for i in range(0, len(texts), batch_size):
            embeddings = embedder.encode(texts[i:i+batch_size]).tolist()
            collection.add(
                documents=texts[i:i+batch_size],
                embeddings=embeddings,
                ids=ids[i:i+batch_size],
                metadatas=metas[i:i+batch_size],
            )


# ── Personal document searcher (used by RAG) ──────────────────────────────

class PersonalDocSearcher:
    """
    Searches personal documents.
    Called by the RAG engine alongside the main knowledge base.
    """

    def __init__(self):
        self._collection = None
        self._embedder   = None
        self._index      = PersonalDocIndex()
        self._ready      = False

    def initialize(self):
        try:
            from sentence_transformers import SentenceTransformer
            import chromadb

            self._embedder = SentenceTransformer(
                "all-MiniLM-L6-v2",
                cache_folder="memory/model_cache"
            )
            client = chromadb.PersistentClient(path=str(PERSONAL_DB_PATH))
            self._collection = client.get_or_create_collection("prometheus_personal")
            self._ready = True
        except Exception:
            self._ready = False

    def search(self, query: str, n: int = 2) -> List[Dict]:
        """Search personal documents for relevant context."""
        if not self._index.all_docs():
            return []

        if self._ready and self._collection and self._collection.count() > 0:
            return self._vector_search(query, n)
        return self._keyword_search(query, n)

    def _vector_search(self, query: str, n: int) -> List[Dict]:
        try:
            emb = self._embedder.encode([query]).tolist()
            results = self._collection.query(
                query_embeddings=emb,
                n_results=min(n, self._collection.count()),
                include=["documents", "metadatas"]
            )
            if not results or not results["documents"]:
                return []
            return [
                {
                    "content": doc,
                    "source": meta.get("source", "personal"),
                    "domain": "personal",
                    "confidence": {"level": "MEDIUM", "score": 75, "source": "personal_doc"}
                }
                for doc, meta in zip(results["documents"][0], results["metadatas"][0])
            ]
        except Exception:
            return self._keyword_search(query, n)

    def _keyword_search(self, query: str, n: int) -> List[Dict]:
        query_words = set(query.lower().split())
        scored = []
        for doc_info in self._index.all_docs():
            text = doc_info.get("text_cache", "")
            if not text:
                continue
            words = set(text.lower().split())
            score = len(query_words & words)
            if score > 0:
                # Return relevant chunk
                idx = 0
                for word in query_words:
                    pos = text.lower().find(word)
                    if pos > 0:
                        idx = max(0, pos - 200)
                        break
                snippet = text[idx:idx+800]
                scored.append((score, {
                    "content": snippet,
                    "source": doc_info.get("source_name", "personal"),
                    "domain": "personal",
                    "confidence": {"level": "MEDIUM", "score": 70, "source": "personal_doc"}
                }))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in scored[:n]]


# ── UI Widget ──────────────────────────────────────────────────────────────

class DocumentContextWidget(QWidget):
    """
    Dialog for managing personal document context.
    Supports drag and drop + file picker.
    """
    documents_updated = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._index = PersonalDocIndex()
        self._worker: Optional[IndexWorker] = None
        self.setObjectName("docContextWidget")
        self.setAcceptDrops(True)
        self._setup_ui()
        self._load_doc_list()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QFrame()
        header.setObjectName("header")
        header.setFixedHeight(50)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 0, 16, 0)

        title = QLabel("📎 Personal Documents")
        title.setObjectName("headerTitle")
        font = title.font()
        font.setPointSize(14)
        font.setBold(True)
        title.setFont(font)

        hl.addWidget(title)
        hl.addStretch()
        layout.addWidget(header)

        # Drop zone
        self._drop_zone = DropZone()
        self._drop_zone.files_dropped.connect(self._on_files_dropped)
        layout.addWidget(self._drop_zone)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(12, 8, 12, 8)
        btn_row.setSpacing(8)

        add_btn = QPushButton("📁 Add Files")
        add_btn.setObjectName("primaryBtn")
        add_btn.clicked.connect(self._pick_files)

        self._remove_btn = QPushButton("🗑 Remove Selected")
        self._remove_btn.setObjectName("navBtn")
        self._remove_btn.clicked.connect(self._remove_selected)
        self._remove_btn.setEnabled(False)

        clear_btn = QPushButton("Clear All")
        clear_btn.setObjectName("navBtnSecondary")
        clear_btn.clicked.connect(self._clear_all)

        btn_row.addWidget(add_btn)
        btn_row.addWidget(self._remove_btn)
        btn_row.addStretch()
        btn_row.addWidget(clear_btn)
        layout.addLayout(btn_row)

        # Progress bar (hidden until indexing)
        self._progress = QProgressBar()
        self._progress.setObjectName("indexProgress")
        self._progress.setFixedHeight(4)
        self._progress.setTextVisible(False)
        self._progress.setRange(0, 0)  # indeterminate
        self._progress.hide()
        layout.addWidget(self._progress)

        # Status label
        self._status = QLabel("")
        self._status.setObjectName("infoLabel")
        self._status.setContentsMargins(12, 0, 12, 4)
        layout.addWidget(self._status)

        # Document list
        self._list = QListWidget()
        self._list.setObjectName("docList")
        self._list.setSelectionMode(QListWidget.ExtendedSelection)
        self._list.itemSelectionChanged.connect(
            lambda: self._remove_btn.setEnabled(len(self._list.selectedItems()) > 0)
        )
        layout.addWidget(self._list)

        # Info footer
        footer = QLabel(
            "Documents are indexed and searched alongside the knowledge base. "
            "Add medical records, personal notes, local maps, or any relevant files."
        )
        footer.setObjectName("noteLabel")
        footer.setWordWrap(True)
        footer.setContentsMargins(12, 8, 12, 8)
        layout.addWidget(footer)

        # Supported formats info
        formats_label = QLabel(
            "Supported: PDF, TXT, MD, DOCX, HTML, CSV, JSON"
            + (" · PNG/JPG (requires tesseract for OCR)" if True else "")
        )
        formats_label.setObjectName("infoLabel")
        formats_label.setContentsMargins(12, 0, 12, 8)
        layout.addWidget(formats_label)

    def _load_doc_list(self):
        """Populate list from index."""
        self._list.clear()
        for doc in self._index.all_docs():
            self._add_list_item(doc)

    def _add_list_item(self, doc: Dict):
        name = doc.get("original_name", "Unknown")
        size_kb = doc.get("size_bytes", 0) / 1024
        words = doc.get("word_count", 0)
        indexed = doc.get("indexed", False)

        status = "✓" if indexed else "~"
        detail = f"{size_kb:.0f} KB"
        if words:
            detail += f" · {words:,} words"

        item = QListWidgetItem(f"{status}  {name}  —  {detail}")
        item.setData(Qt.UserRole, doc.get("hash"))
        item.setToolTip(doc.get("path", ""))
        self._list.addItem(item)

    def _pick_files(self):
        """Open file picker dialog."""
        extensions = " ".join(f"*{ext}" for ext in SUPPORTED_EXTENSIONS)
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Add Documents",
            "",
            f"Supported Files ({extensions});;All Files (*.*)"
        )
        if paths:
            for path in paths:
                self._index_file(Path(path))

    def _on_files_dropped(self, paths: List[str]):
        for path in paths:
            p = Path(path)
            if p.suffix.lower() in SUPPORTED_EXTENSIONS:
                self._index_file(p)
            else:
                self._status.setText(
                    f"Skipped {p.name} — unsupported format"
                )

    def _index_file(self, file_path: Path):
        """Copy file to personal docs and index it."""
        if not file_path.exists():
            return

        # Hash the file for deduplication
        file_hash = hashlib.md5(file_path.read_bytes()).hexdigest()

        if self._index.exists(file_hash):
            self._status.setText(f"{file_path.name} already indexed")
            return

        # Copy to personal docs directory
        dest = PERSONAL_DOCS_DIR / file_path.name
        # Handle name collision
        counter = 1
        while dest.exists():
            dest = PERSONAL_DOCS_DIR / f"{file_path.stem}_{counter}{file_path.suffix}"
            counter += 1

        shutil.copy2(file_path, dest)

        doc_info = {
            "hash":          file_hash,
            "original_name": file_path.name,
            "path":          str(dest),
            "source_name":   file_path.stem.replace(" ", "_").lower(),
            "added":         datetime.now().isoformat(),
            "size_bytes":    file_path.stat().st_size,
            "suffix":        file_path.suffix.lower(),
        }

        # Index in background
        self._progress.show()
        self._status.setText(f"Indexing {file_path.name}...")

        self._worker = IndexWorker(dest, doc_info, self._index)
        self._worker.progress.connect(self._status.setText)
        self._worker.finished.connect(self._on_index_done)
        self._worker.start()

    def _on_index_done(self, success: bool, message: str):
        self._progress.hide()
        self._status.setText(message)
        self._load_doc_list()
        self.documents_updated.emit()

    def _remove_selected(self):
        selected = self._list.selectedItems()
        if not selected:
            return

        names = [item.text().split("  —  ")[0].strip("✓~ ") for item in selected]
        reply = QMessageBox.question(
            self,
            "Remove Documents",
            f"Remove {len(selected)} document(s)?\n\n"
            + "\n".join(names),
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        for item in selected:
            file_hash = item.data(Qt.UserRole)
            if file_hash:
                doc = self._index.get(file_hash)
                if doc:
                    # Delete the copied file
                    try:
                        Path(doc["path"]).unlink(missing_ok=True)
                    except Exception:
                        pass
                    # Remove from vector DB
                    self._remove_from_chroma(doc.get("source_name", ""))
                self._index.remove(file_hash)

        self._load_doc_list()
        self.documents_updated.emit()
        self._status.setText(f"Removed {len(selected)} document(s)")

    def _remove_from_chroma(self, source_name: str):
        try:
            import chromadb
            client = chromadb.PersistentClient(path=str(PERSONAL_DB_PATH))
            collection = client.get_collection("prometheus_personal")
            # Delete all chunks from this source
            results = collection.get(where={"source": source_name})
            if results and results["ids"]:
                collection.delete(ids=results["ids"])
        except Exception:
            pass

    def _clear_all(self):
        if not self._index.all_docs():
            return
        reply = QMessageBox.question(
            self,
            "Clear All Documents",
            "Remove all personal documents from context?\n"
            "This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        for doc in self._index.all_docs():
            try:
                Path(doc["path"]).unlink(missing_ok=True)
            except Exception:
                pass

        # Clear the ChromaDB collection
        try:
            import chromadb
            client = chromadb.PersistentClient(path=str(PERSONAL_DB_PATH))
            client.delete_collection("prometheus_personal")
        except Exception:
            pass

        # Clear index file
        PERSONAL_INDEX_PATH.write_text("{}")
        self._index._index = {}
        self._load_doc_list()
        self.documents_updated.emit()
        self._status.setText("All personal documents removed")

    # ── Drag and drop ──────────────────────────────────────────────────────

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        paths = [url.toLocalFile() for url in event.mimeData().urls()]
        self._on_files_dropped(paths)


class DropZone(QFrame):
    """Visual drag-and-drop target."""
    files_dropped = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("dropZone")
        self.setFixedHeight(80)
        self.setAcceptDrops(True)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)

        lbl = QLabel("📎  Drag and drop files here")
        lbl.setObjectName("dropZoneLabel")
        lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl)

        sub = QLabel("PDF, TXT, MD, DOCX, HTML, CSV, JSON, PNG, JPG")
        sub.setObjectName("infoLabel")
        sub.setAlignment(Qt.AlignCenter)
        layout.addWidget(sub)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            self.setObjectName("dropZoneActive")
            self.style().unpolish(self)
            self.style().polish(self)
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self.setObjectName("dropZone")
        self.style().unpolish(self)
        self.style().polish(self)

    def dropEvent(self, event: QDropEvent):
        self.setObjectName("dropZone")
        self.style().unpolish(self)
        self.style().polish(self)
        paths = [url.toLocalFile() for url in event.mimeData().urls()]
        self.files_dropped.emit(paths)
