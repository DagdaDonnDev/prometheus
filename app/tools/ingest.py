"""
Document ingestion pipeline.
Processes PDFs, text files, and web content into the knowledge base.
Run once to build the knowledge base, then RAG uses it forever.

Usage:
    python tools/ingest.py                    # ingest all sources
    python tools/ingest.py --source army      # ingest specific source
    python tools/ingest.py --rebuild          # clear and rebuild
    python tools/ingest.py --stats            # show knowledge base statistics
    python tools/ingest.py --download-wikipedia   # fetch + ingest Simple English Wikipedia
    python tools/ingest.py --wikipedia FILE       # ingest a dump you already have
"""

import os
import sys
import json
import argparse
import hashlib
import shutil
from pathlib import Path

# Run from anywhere: work in the prometheus folder (one up from tools/) so
# relative paths and `import core…` resolve the same as for main.py
ROOT_DIR = Path(__file__).resolve().parent.parent
os.chdir(ROOT_DIR)
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
from typing import List, Dict, Optional, Generator, Tuple


KNOWLEDGE_PATH = Path("knowledge_base")
PROCESSED_PATH = Path("memory/processed_sources.json")
CHUNK_SIZE = 400        # words per chunk
CHUNK_OVERLAP = 50      # word overlap between chunks

# Domains where page images are extracted alongside text
IMAGE_ELIGIBLE_DOMAINS = {
    "plants_temperate", "plants_tropical", "plants_desert", "plants_arctic",
    "medical", "emergency_medicine", "where_no_doctor", "where_no_dentist",
    "blacksmithing", "electronics", "build", "navigation",
    # Survival manuals and practical books are full of diagrams too
    "survival", "army_fm_3_05_70", "farming", "food_preservation",
    "nuclear_survival", "weather_patterns", "survivor_library",
}

# Target image dimensions for extracted pages (width in px, maintain aspect)
IMAGE_PAGE_WIDTH = 800


class TextExtractor:
    """Extract clean text from various file formats."""

    def extract(self, file_path: Path) -> Optional[str]:
        suffix = file_path.suffix.lower()

        if suffix == ".txt" or suffix == ".md":
            return self._extract_text(file_path)
        elif suffix == ".pdf":
            return self._extract_pdf(file_path)
        elif suffix in (".html", ".htm"):
            return self._extract_html(file_path)
        elif suffix == ".json":
            return self._extract_json(file_path)
        else:
            return None

    def extract_pdf_with_pages(self, path: Path) -> List[Tuple[int, str]]:
        """
        Extract text per page from a PDF.
        Returns list of (page_num, text) tuples.
        Page numbers are 1-indexed.
        """
        try:
            try:
                import pymupdf as fitz   # PyMuPDF ≥ 1.24 name
            except ImportError:
                import fitz
            doc = fitz.open(str(path))
            pages = []
            for i, page in enumerate(doc):
                text = page.get_text()
                if text.strip():
                    pages.append((i + 1, text))
            doc.close()
            return pages
        except ImportError:
            # Fall back to extracting full text as single page
            text = self._extract_pdf(path)
            return [(1, text)] if text else []
        except Exception as e:
            print(f"  Error extracting PDF {path.name}: {e}")
            return []

    def extract_page_images(
        self, path: Path, image_dir: Path, source: str
    ) -> Dict[int, Path]:
        """
        Extract each PDF page as a JPEG image.
        Only called for image-eligible domains.
        Returns dict of {page_num: image_path}.
        Skips pages that already have an image file.
        """
        page_images: Dict[int, Path] = {}

        try:
            try:
                import pymupdf as fitz   # PyMuPDF ≥ 1.24 name
            except ImportError:
                import fitz
            image_dir.mkdir(parents=True, exist_ok=True)
            doc = fitz.open(str(path))

            for i, page in enumerate(doc):
                page_num = i + 1
                img_path = image_dir / f"{source}_p{page_num:03d}.jpg"
                page_images[page_num] = img_path

                if img_path.exists():
                    continue  # Already extracted — skip

                # Render at target width
                zoom = IMAGE_PAGE_WIDTH / page.rect.width
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat)
                pix.save(str(img_path))

            doc.close()

        except ImportError:
            pass  # PyMuPDF not installed — no images
        except Exception as e:
            print(f"  Image extraction failed for {path.name}: {e}")

        return page_images

    def _extract_text(self, path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return ""

    def _extract_pdf(self, path: Path) -> str:
        try:
            try:
                import pymupdf as fitz   # PyMuPDF ≥ 1.24 name
            except ImportError:
                import fitz
            doc = fitz.open(str(path))
            text = ""
            for page in doc:
                text += page.get_text()
            doc.close()
            return text
        except ImportError:
            print(f"  PyMuPDF not installed — skipping PDF: {path.name}")
            return ""
        except Exception as e:
            print(f"  Error extracting PDF {path.name}: {e}")
            return ""

    def _extract_html(self, path: Path) -> str:
        try:
            from bs4 import BeautifulSoup
            html = path.read_text(encoding="utf-8", errors="replace")
            soup = BeautifulSoup(html, "lxml")
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            return soup.get_text(separator="\n", strip=True)
        except ImportError:
            print(f"  BeautifulSoup not installed — skipping HTML: {path.name}")
            return ""
        except Exception as e:
            print(f"  Error extracting HTML {path.name}: {e}")
            return ""

    def _extract_json(self, path: Path) -> str:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, str):
                return data
            elif isinstance(data, dict):
                return json.dumps(data, indent=2)
            elif isinstance(data, list):
                return "\n".join(str(item) for item in data)
        except Exception:
            return ""
        return ""


class Chunker:
    """Split text into overlapping chunks for RAG."""

    def __init__(self, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, text: str, source: str, domain: str,
              page_num: int = 0) -> List[Dict]:
        """
        Split text into chunks with metadata.
        page_num: if non-zero, stored in each chunk for image lookup.
        """
        text = self._clean(text)
        words = text.split()

        if len(words) < 20:
            return []

        chunks = []
        step = self.chunk_size - self.overlap
        chunk_idx = 0

        for i in range(0, len(words), step):
            chunk_words = words[i:i + self.chunk_size]
            if len(chunk_words) < 20:
                continue

            content = " ".join(chunk_words)
            chunk_id = (
                f"{domain}_{source}_p{page_num}_{chunk_idx}"
                if page_num else
                f"{domain}_{source}_{chunk_idx}"
            )

            chunk = {
                "id": chunk_id,
                "content": content,
                "source": source,
                "domain": domain,
                "word_count": len(chunk_words),
                "chunk_index": chunk_idx,
            }
            if page_num:
                chunk["page_num"] = page_num

            chunks.append(chunk)
            chunk_idx += 1

        return chunks

    def chunk_pages(
        self, pages: List[Tuple[int, str]], source: str, domain: str
    ) -> List[Dict]:
        """
        Chunk a list of (page_num, text) tuples.
        Each chunk retains the page number it came from.
        """
        all_chunks = []
        for page_num, text in pages:
            page_chunks = self.chunk(text, source, domain, page_num=page_num)
            all_chunks.extend(page_chunks)
        return all_chunks

    def _clean(self, text: str) -> str:
        """Clean text for chunking."""
        import re
        text = re.sub(r'\s+', ' ', text)
        # Keep maths and units (=, +, ×, ², ≈, Ω …) — formulas are knowledge.
        # Only strip markup and decoration (#, *, |, `, ~, bullets, emoji).
        text = re.sub(
            r'[^\w\s.,;:!?\'\"()\[\]\-/°%=+×·⋅*^<>²³¹⁰⁴⁵⁶⁷⁸⁹⁻₀₁₂₃₄₅₆₇₈₉'
            r'≈≤≥±√π½¼¾−→←↔≠∞Ωµμ∆Δ∑θφλστ]+',
            ' ', text
        )
        text = re.sub(r' +', ' ', text)
        return text.strip()


class Ingester:
    """Main ingestion pipeline."""

    def __init__(self, rebuild: bool = False):
        self.extractor = TextExtractor()
        self.chunker = Chunker()
        self.rebuild = rebuild
        self.processed = self._load_processed()
        self.all_chunks: List[Dict] = []

        # Try to load vector DB
        self.collection = None
        self.embedder = None
        self._init_vector_db()

    def _load_processed(self) -> Dict:
        if PROCESSED_PATH.exists() and not self.rebuild:
            try:
                return json.loads(PROCESSED_PATH.read_text())
            except Exception:
                pass
        return {}

    def _save_processed(self):
        PROCESSED_PATH.parent.mkdir(parents=True, exist_ok=True)
        PROCESSED_PATH.write_text(json.dumps(self.processed, indent=2))

    def _init_vector_db(self):
        try:
            from core.ai.embedder import get_embedder
            import chromadb

            print("Loading embedding model (all-MiniLM-L6-v2)...")
            self.embedder = get_embedder()

            client = chromadb.PersistentClient(path="memory/chroma_db")

            if self.rebuild:
                try:
                    client.delete_collection("prometheus_knowledge")
                    print("Cleared existing knowledge base.")
                except Exception:
                    pass

            self.collection = client.get_or_create_collection(
                name="prometheus_knowledge",
                metadata={"hnsw:space": "cosine"}
            )
            print(f"Vector DB ready. Current chunks: {self.collection.count()}")

        except ImportError as e:
            print(f"Vector DB not available ({e}). Will save chunks as JSON only.")

    def ingest_all(self, source_filter: Optional[str] = None):
        """Process all files in knowledge_base directory."""
        if not KNOWLEDGE_PATH.exists():
            print(f"Knowledge base directory not found: {KNOWLEDGE_PATH}")
            print("Create it and add your source materials.")
            return

        total_files = 0
        total_chunks = 0
        total_images = 0
        skipped = 0
        duplicates = 0

        # Step 0: tidy the index before adding anything new
        #   - forget files that were deleted from knowledge_base/
        #   - find the same book indexed twice under different names
        #     (it would count as two independent sources)
        removed, twins = self._tidy_index()
        self._seen_content = {
            e["content_sha"]: e["file"]
            for e in self.processed.values() if e.get("content_sha")
        }

        for domain_dir in sorted(KNOWLEDGE_PATH.iterdir()):
            if not domain_dir.is_dir():
                continue

            domain = domain_dir.name

            if source_filter and source_filter not in domain:
                continue

            print(f"\n📁 Processing domain: {domain}")
            image_eligible = domain in IMAGE_ELIGIBLE_DOMAINS

            for file_path in sorted(domain_dir.rglob("*")):
                if not file_path.is_file():
                    continue
                if file_path.suffix.lower() not in (
                    ".txt", ".md", ".pdf", ".html", ".htm", ".json"
                ):
                    continue
                if file_path.name == "README.md":
                    continue   # folder placeholder, not knowledge

                file_hash = self._file_hash(file_path)
                entry = self.processed.get(file_hash)
                # A PDF indexed before its folder got page pictures is done again
                # once, page by page, so its pictures exist and chunks know their page
                needs_pages = (
                    entry is not None and image_eligible and
                    file_path.suffix.lower() == ".pdf" and not entry.get("paged")
                )
                if entry is not None and not self.rebuild and not needs_pages:
                    skipped += 1
                    continue
                if needs_pages:
                    print(f"  ↻ {file_path.name}: adding page pictures")

                # Same contents as a file already indexed? Skip it.
                content_sha = self._content_hash(file_path)
                twin = self._seen_content.get(content_sha)
                if twin and twin != str(file_path) and Path(twin).exists():
                    print(f"  ⚠ Skipped {file_path.name} — same contents as {Path(twin).name}")
                    duplicates += 1
                    continue
                self._seen_content[content_sha] = str(file_path)

                is_pdf = file_path.suffix.lower() == ".pdf"
                source = file_path.stem.replace(" ", "_").lower()
                chunks = []
                img_count = 0

                if is_pdf and image_eligible:
                    # Per-page extraction: text with page numbers + images
                    pages = self.extractor.extract_pdf_with_pages(file_path)
                    if not pages:
                        continue

                    chunks = self.chunker.chunk_pages(pages, source, domain)

                    # Extract page images (skips already-extracted)
                    image_dir = domain_dir / "_images"
                    page_images = self.extractor.extract_page_images(
                        file_path, image_dir, source
                    )
                    img_count = len(page_images)
                    total_images += img_count
                    # Which of those pages really have a figure (only they're shown)
                    from core.library import figures
                    figures.record(KNOWLEDGE_PATH, domain, source, figures.scan(file_path))

                elif is_pdf:
                    # Non-image-eligible PDF: extract full text, no page tracking
                    text = self.extractor.extract(file_path)
                    if not text or len(text.strip()) < 100:
                        continue
                    chunks = self.chunker.chunk(text, source, domain)

                else:
                    # Text/HTML/JSON
                    text = self.extractor.extract(file_path)
                    if not text or len(text.strip()) < 100:
                        continue
                    chunks = self.chunker.chunk(text, source, domain)

                if not chunks:
                    continue

                self.all_chunks.extend(chunks)
                # An edited file gets a new key — drop its old entry
                for old_key in [k for k, e in self.processed.items()
                                if e.get("file") == str(file_path)]:
                    del self.processed[old_key]
                self.processed[file_hash] = {
                    "file": str(file_path),
                    "source": source,
                    "domain": domain,
                    "chunks": len(chunks),
                    "images": img_count,
                    "content_sha": content_sha,
                    "paged": bool(is_pdf and image_eligible),
                }

                total_files += 1
                total_chunks += len(chunks)
                img_note = f" + {img_count} images" if img_count else ""
                print(f"  ✓ {file_path.name} → {len(chunks)} chunks{img_note}")

        print(f"\n📊 Summary:")
        print(f"  Files processed: {total_files}")
        print(f"  Files skipped (already indexed): {skipped}")
        if duplicates:
            print(f"  Duplicate files skipped: {duplicates} "
                  f"(delete the extra copies to stop this message)")
        if removed:
            print(f"  Deleted files removed from the index: {removed}")
        print(f"  New chunks: {total_chunks}")
        if total_images:
            print(f"  Page images extracted: {total_images}")

        if self.all_chunks:
            self._embed_and_store()

        self._save_processed()
        print("\n✅ Ingestion complete.")

    def _embed_and_store(self):
        """
        Store chunks for search.

        Step 1: always write the JSON keyword index — it's the fallback when
                the vector DB isn't available, and the Training Path scans it
                directly for its anchors.
        Step 2: if the vector DB is available, replace each re-indexed file's
                old chunks and embed the new ones.
        """
        self._save_json_fallback()
        if not self.collection or not self.embedder:
            return

        # Remove old chunks for every file being re-indexed, so an edited file
        # doesn't keep stale text (or extra chunks if it got shorter)
        for domain, source in sorted({(c["domain"], c["source"]) for c in self.all_chunks}):
            try:
                self.collection.delete(where={"$and": [
                    {"domain": {"$eq": domain}}, {"source": {"$eq": source}},
                ]})
            except Exception:
                pass

        print(f"\nEmbedding {len(self.all_chunks)} chunks...")

        batch_size = 64
        total = len(self.all_chunks)

        for i in range(0, total, batch_size):
            batch = self.all_chunks[i:i + batch_size]

            texts = [c["content"] for c in batch]
            ids = [c["id"] for c in batch]
            metadatas = [
                {
                    "source": c["source"],
                    "domain": c["domain"],
                    "page_num": c.get("page_num", 0),
                }
                for c in batch
            ]

            # upsert, not add: a chunk id that somehow survived is replaced, not skipped
            embeddings = self.embedder.encode(texts).tolist()
            self.collection.upsert(
                documents=texts,
                embeddings=embeddings,
                ids=ids,
                metadatas=metadatas,
            )

            pct = min(100, int(((i + batch_size) / total) * 100))
            print(f"  Embedded: {min(i + batch_size, total)}/{total} ({pct}%)", end="\r")

        print(f"\n✓ Stored {self.collection.count()} total chunks in vector DB")

    def _save_json_fallback(self):
        """Save chunks as JSON for keyword search fallback."""
        fallback_path = Path("memory/chunks_fallback.json")
        fallback_path.parent.mkdir(parents=True, exist_ok=True)

        # Step 1: start from the existing index (empty on --rebuild)
        existing = []
        if fallback_path.exists() and not self.rebuild:
            try:
                existing = json.loads(fallback_path.read_text())
            except Exception:
                pass

        # Step 2: drop old chunks of every file being re-indexed, then add the new ones
        reindexed = {(c["domain"], c["source"]) for c in self.all_chunks}
        existing = [c for c in existing
                    if (c.get("domain"), c.get("source")) not in reindexed]
        # Wikipedia never goes in the keyword index (it's loaded into RAM at
        # startup); its own full-text search covers it
        new_chunks = [c for c in self.all_chunks if c.get("domain") != "wikipedia"]
        existing = [c for c in existing if c.get("domain") != "wikipedia"]
        existing.extend(new_chunks)
        fallback_path.write_text(json.dumps(existing))
        print(f"✓ Saved {len(existing)} chunks to JSON fallback")

    @staticmethod
    def _content_hash(path: Path) -> str:
        """SHA-256 of the file's bytes — the same book under any name matches."""
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
        return h.hexdigest()

    def _tidy_index(self):
        """
        Returns (files removed, duplicate copies removed).

        Step 1: entries whose file no longer exists → remove their chunks.
        Step 2: fill in content fingerprints for entries indexed before v22.
        Step 3: two entries with the same fingerprint → keep the first path
                (alphabetical), remove the other's chunks.
        """
        if self.rebuild or not self.processed:
            return 0, 0

        to_purge = set()       # (domain, source) pairs to drop from both stores
        removed = twins = 0

        # Step 1
        for key, e in list(self.processed.items()):
            if not Path(e.get("file", "")).exists():
                to_purge.add((e.get("domain"), e.get("source")))
                del self.processed[key]
                removed += 1

        # Step 2
        for e in self.processed.values():
            if not e.get("content_sha"):
                try:
                    e["content_sha"] = self._content_hash(Path(e["file"]))
                except OSError:
                    pass

        # Step 3
        by_sha = {}
        for key, e in sorted(self.processed.items(), key=lambda kv: kv[1].get("file", "")):
            sha = e.get("content_sha")
            if not sha:
                continue
            if sha in by_sha:
                print(f"  ⚠ {Path(e['file']).name} is the same file as "
                      f"{Path(by_sha[sha]).name} — removing the extra copy from the index")
                to_purge.add((e.get("domain"), e.get("source")))
                del self.processed[key]
                twins += 1
            else:
                by_sha[sha] = e["file"]

        if to_purge:
            self._purge(to_purge)
            self._save_processed()
        return removed, twins

    def _purge(self, pairs):
        """Remove every chunk of the given (domain, source) files from both stores."""
        fallback_path = Path("memory/chunks_fallback.json")
        if fallback_path.exists():
            try:
                chunks = json.loads(fallback_path.read_text())
                chunks = [c for c in chunks
                          if (c.get("domain"), c.get("source")) not in pairs]
                fallback_path.write_text(json.dumps(chunks))
            except Exception:
                pass
        if self.collection:
            for domain, source in pairs:
                try:
                    self.collection.delete(where={"$and": [
                        {"domain": {"$eq": domain}}, {"source": {"$eq": source}},
                    ]})
                except Exception:
                    pass

    def _file_hash(self, path: Path) -> str:
        """Get a hash of file path + modification time."""
        stat = path.stat()
        return hashlib.md5(f"{path}{stat.st_mtime}".encode()).hexdigest()


def create_sample_knowledge_base():
    """Create starter knowledge base with seed content."""
    print("Creating starter knowledge base structure...")

    domains = {
        "survival": "Core survival skills — water, fire, shelter, food, navigation",
        "medical": "Medical procedures, first aid, improvised medicine",
        "electronics": "Electronics from scratch, salvage, retrofitting, modification",
        "navigation": "Navigation without GPS, star tables, terrain reading",
        "farming": "Agriculture, food preservation, animal husbandry",
        "build": "Construction, tools, fabrication from raw materials",
        "chemistry": "Materials science, metallurgy, chemistry fundamentals",
        "companion": "Philosophy, psychology, meaning, human connection",
        "scientific_reference": "Universal laws and constants — Training Path anchor source",
        "reasoning": "Critical thinking frameworks, decision making under uncertainty",
        "plants_temperate": "Edible and medicinal plants — temperate biome",
        "plants_tropical": "Edible and medicinal plants — tropical biome",
        "plants_desert": "Edible and medicinal plants — desert biome",
        "plants_arctic": "Edible and medicinal plants — arctic biome",
        "water_purification": "Water sourcing and purification — full build instructions",
        "emergency_medicine": "Emergency medical procedures — step by step",
        "food_preservation": "Fermentation, canning, curing, root cellaring",
        "blacksmithing": "Blacksmithing and tool making from scrap metal",
        "soap_making": "Soap from ash and fat — full process",
        "army_fm_3_05_70": "US Army Survival Manual FM 3-05.70",
        "where_no_doctor": "Where There Is No Doctor — Hesperian Foundation",
        "where_no_dentist": "Where There Is No Dentist — Hesperian Foundation",
        "nuclear_survival": "Nuclear War Survival Skills — Cresson Kearny",
        "foxfire": "Foxfire Books — Appalachian survival oral tradition",
        "survivor_library": "Pre-electricity practical manuals 1800s-1900s",
        "the_knowledge": "The Knowledge — Lewis Dartnell",
        "rebuild_ladder": "Civilization rebuild ladder and dependency chains",
        "weather_patterns": "Regional weather patterns and natural forecasting",
        "soil_maps": "Soil identification and agricultural land reading",
    }

    readme_lines = [
        "# Prometheus Knowledge Base\n",
        "Place source material files in the appropriate domain folders.\n",
        "Run `python tools/ingest.py` to process and index all files.\n\n",
        "## Domain Folders\n"
    ]

    for domain, description in domains.items():
        domain_path = KNOWLEDGE_PATH / domain
        domain_path.mkdir(parents=True, exist_ok=True)

        # Create README in each domain
        readme = domain_path / "README.md"
        if not readme.exists():
            readme.write_text(
                f"# {domain.replace('_', ' ').title()}\n\n"
                f"{description}\n\n"
                f"## Add Sources Here\n\n"
                f"Place .txt, .md, or .pdf files in this folder.\n"
                f"Run `python tools/ingest.py` to index them.\n\n"
                f"## Recommended Sources\n\n"
                f"See the main README for download links and sources.\n"
            )

        readme_lines.append(f"- `{domain}/` — {description}\n")

    # Write main README
    (KNOWLEDGE_PATH / "README.md").write_text("".join(readme_lines))
    print(f"✓ Created {len(domains)} domain folders")


# ── Wikipedia ──────────────────────────────────────────────────────────────

WIKI_BASE_URL  = "https://dumps.wikimedia.org/simplewiki/latest/"
WIKI_DUMP_NAME = "simplewiki-latest-pages-articles.xml.bz2"
WIKI_SUMS_NAME = "simplewiki-latest-sha1sums.txt"
from core.app.paths import setup_dir
WIKI_DOWNLOAD_DIR = setup_dir()   # prometheus_setup/, inside or next to the project
# Wikimedia asks automated clients for a descriptive User-Agent
WIKI_USER_AGENT = "Prometheus-offline-knowledge-ingest/1.0 (+https://github.com/DagdaDonnDev/prometheus)"


def download_wikipedia(dest_dir: Path = WIKI_DOWNLOAD_DIR,
                       base_url: str = WIKI_BASE_URL,
                       dump_name: str = WIKI_DUMP_NAME,
                       sums_name: str = WIKI_SUMS_NAME) -> Optional[Path]:
    """
    Download a Wikipedia dump file (by default the latest Simple English one).

    Step 1: download to <name>.part, resuming if a previous attempt was cut off
    Step 2: check the SHA-1 Wikimedia publishes (skipped with a warning if
            the checksum list can't be fetched)
    Step 3: rename to the final name, replacing any older dump

    Returns the dump path, or None if the download failed.
    """
    import requests

    dest_dir.mkdir(parents=True, exist_ok=True)
    final = dest_dir / dump_name
    part = dest_dir / (dump_name + ".part")
    if final.exists() and not part.exists():
        print(f"  ✓ Already downloaded: {final}")
        return final
    headers = {"User-Agent": WIKI_USER_AGENT}

    # Step 1: download (resume from .part if present)
    have = part.stat().st_size if part.exists() else 0
    if have:
        headers["Range"] = f"bytes={have}-"
        print(f"  Resuming download at {have / 1024 / 1024:.0f} MB")
    try:
        with requests.get(base_url + dump_name, headers=headers,
                          stream=True, timeout=60) as r:
            if r.status_code == 416:          # .part is already complete
                pass
            elif r.status_code not in (200, 206):
                print(f"  ✗ Download failed: HTTP {r.status_code}")
                return None
            else:
                if r.status_code == 200 and have:
                    have = 0                  # server ignored Range — start over
                total = have + int(r.headers.get("Content-Length", 0) or 0)
                done = have
                with open(part, "ab" if have else "wb") as f:
                    for block in r.iter_content(1 << 20):
                        f.write(block)
                        done += len(block)
                        if total:
                            print(f"  Downloaded {done / 1024 / 1024:,.0f} / "
                                  f"{total / 1024 / 1024:,.0f} MB", end="\r")
                print()
    except requests.RequestException as e:
        print(f"\n  ✗ Download interrupted: {e}\n"
              f"    Run the same command again to resume.")
        return None

    # Step 2: verify
    expected = None
    try:
        sums = requests.get(base_url + sums_name,
                            headers={"User-Agent": WIKI_USER_AGENT}, timeout=30)
        if sums.ok:
            # The list names files with their date ("enwiki-20261101-pages-…");
            # match on what comes after it
            want = dump_name.split("-", 2)[2]
            for line in sums.text.splitlines():
                parts = line.split()
                if len(parts) == 2 and parts[1].split("-", 2)[-1] == want:
                    expected = parts[0]
    except requests.RequestException:
        pass

    if expected:
        h = hashlib.sha1()
        with open(part, "rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
        if h.hexdigest() != expected:
            print("  ✗ Checksum doesn't match — the file is damaged. Deleting it; "
                  "run the command again to re-download.")
            part.unlink()
            return None
        print("  ✓ Checksum verified")
    else:
        print("  ⚠ Couldn't fetch Wikimedia's checksum list — file not verified")

    # Step 3: replace any older dump
    part.replace(final)
    print(f"  ✓ Saved {final} ({final.stat().st_size / 1024 / 1024:,.0f} MB)")
    return final


def parse_wikipedia_dump(dump_path: Path, output_dir: Path,
                         max_articles: int = 0,
                         min_words: int = 100) -> int:
    """
    Extract articles from a Wikipedia XML dump (.xml or .xml.bz2) as .txt files.

    - Only real articles (namespace 0), no redirects, nothing under min_words.
    - Works with any MediaWiki export schema version (the namespace is stripped
      generically — the old code expected one exact version and found nothing).
    - A refresh rewrites only articles whose text changed (so ingest only
      re-indexes those) and deletes articles that are no longer in the dump.

    Returns the number of articles extracted.
    """
    import bz2
    import re
    import xml.etree.ElementTree as ET

    output_dir.mkdir(parents=True, exist_ok=True)

    from core.library.wikitext import clean_wikitext

    def safe_filename(title: str) -> str:
        safe = re.sub(r'[^\w\s-]', '', title)
        safe = re.sub(r'\s+', '_', safe.strip())
        return safe[:100] + ".txt"

    print(f"  Opening dump: {dump_path.name}")
    if dump_path.suffix == ".bz2":
        file_obj = bz2.open(dump_path, "rt", encoding="utf-8", errors="replace")
    else:
        file_obj = open(dump_path, "r", encoding="utf-8", errors="replace")

    count = skipped = redirects = unchanged = 0
    written = set()
    print("  Parsing XML stream (several minutes for a full dump)…")

    try:
        context = ET.iterparse(file_obj, events=("start", "end"))
        _, root = next(context)            # keep a handle so memory can be freed

        title, ns, text = "", "", ""
        for event, elem in context:
            if event != "end":
                continue
            tag = elem.tag.rsplit("}", 1)[-1]   # strip any schema namespace

            if tag == "title":
                title = elem.text or ""
            elif tag == "ns":
                ns = (elem.text or "").strip()
            elif tag == "text":
                text = elem.text or ""
            elif tag == "page":
                keep = True
                if ns != "0":
                    keep = False                                  # talk, user, project pages…
                elif text.lstrip().upper().startswith("#REDIRECT"):
                    redirects += 1
                    keep = False

                if keep:
                    clean = clean_wikitext(text)
                    if len(clean.split()) < min_words:
                        skipped += 1
                    else:
                        name = safe_filename(title)
                        out_path = output_dir / name
                        content = f"# {title}\n\n{clean}"
                        # Only rewrite changed articles, so ingest re-indexes only those
                        if out_path.exists() and out_path.read_text(
                                encoding="utf-8", errors="replace") == content:
                            unchanged += 1
                        else:
                            out_path.write_text(content, encoding="utf-8")
                        written.add(name)
                        count += 1
                        if count % 1000 == 0:
                            print(f"  Extracted: {count:,} articles…", end="\r")

                title, ns, text = "", "", ""
                root.clear()                    # free everything parsed so far
                if max_articles and count >= max_articles:
                    print(f"\n  Reached limit of {max_articles:,} articles.")
                    break
    finally:
        file_obj.close()

    # Articles no longer in the dump (only on a full run — a limited run
    # would otherwise delete everything past the limit)
    removed = 0
    if not max_articles:
        for old in output_dir.glob("*.txt"):
            if old.name not in written:
                old.unlink()
                removed += 1

    print(f"\n  ✓ {count:,} articles ({unchanged:,} unchanged, {removed:,} removed; "
          f"{redirects:,} redirects and {skipped:,} short pages skipped)")
    return count


def ingest_wikipedia(dump_path: Optional[str] = None, max_articles: int = 0,
                     download: bool = False, extract_only: bool = False) -> bool:
    """
    Extract a Wikipedia dump into knowledge_base/wikipedia/ and index it.

        python tools/ingest.py --download-wikipedia            # fetch latest, then ingest
        python tools/ingest.py --wikipedia FILE.xml(.bz2)      # use a dump you already have
    """
    if download:
        print("\n🌐 Downloading the latest Simple English Wikipedia dump")
        dump = download_wikipedia()
        if not dump:
            return False
    else:
        dump = Path(dump_path)
        if not dump.exists():
            print(f"Dump file not found: {dump_path}\n"
                  f"Download it with:  python tools/ingest.py --download-wikipedia")
            return False

    if KNOWLEDGE_PATH.resolve() in dump.resolve().parents:
        print(f"  ⚠ {dump.name} is inside {KNOWLEDGE_PATH}/ — move it to "
              f"{WIKI_DOWNLOAD_DIR}/ so desktop builds don't copy it.")

    output_dir = KNOWLEDGE_PATH / "wikipedia"
    print(f"\n📖 Extracting {dump.name} → {output_dir}"
          + (f" (first {max_articles:,} articles)" if max_articles else ""))
    count = parse_wikipedia_dump(dump, output_dir, max_articles=max_articles)
    if not count:
        print("  ✗ No articles found — is this a pages-articles dump?")
        return False

    # Search inside every article (SQLite full-text — minutes, no AI model)
    print("\n🔎 Building the Wikipedia search index…")
    from core.library.wiki_index import build_index
    build_index(output_dir, KNOWLEDGE_PATH / "wikipedia_search.sqlite")

    if extract_only:
        # Chat lookups and the Wikipedia tab read the extracted files directly,
        # so this is enough to use it. Indexing adds meaning-based search later.
        print(f"\n✅ Extracted to {output_dir}. Chat and the Wikipedia tab can use it now.\n"
              f"   For meaning-based search too, index it later (slow — hours on a CPU):\n"
              f"       python tools/ingest.py --source wikipedia")
        return True

    print(f"\nIndexing Wikipedia articles…")
    Ingester(rebuild=False).ingest_all(source_filter="wikipedia")
    print("\n✅ Wikipedia ingestion complete.")
    return True


def ingest_wikipedia_full(dump_path: Optional[str] = None, top: int = 1_000_000,
                          workers: int = 0) -> bool:
    """
    The most linked-to English Wikipedia articles → knowledge_base/wikipedia_full.sqlite.

        python tools/ingest.py --download-wikipedia-full [--top 1000000]
        python tools/ingest.py --wikipedia-full <enwiki-…-multistream.xml.bz2> [--top N]

    Step 1: download the multistream dump and its index (about 24 GB; resumes)
    Step 2: build (core/library/wiki_full.py) — two passes over the dump on every core,
            then the search index. Hours, once; running again carries on.
    """
    from core.library import wiki_full
    if dump_path:
        dump = Path(dump_path)
        index = dump.with_name(dump.name.replace(".xml.bz2", "-index.txt.bz2"))
        if not dump.exists() or not index.exists():
            print(f"Need both {dump.name} and {index.name} side by side.")
            return False
    else:
        print("\n🌐 Downloading English Wikipedia (about 24 GB — resumes if cut off)")
        index = download_wikipedia(base_url=wiki_full.BASE_URL, dump_name=wiki_full.INDEX_NAME,
                                   sums_name=wiki_full.SUMS_NAME)
        dump = index and download_wikipedia(base_url=wiki_full.BASE_URL, dump_name=wiki_full.DUMP_NAME,
                                            sums_name=wiki_full.SUMS_NAME)
        if not dump:
            return False
    free = shutil.disk_usage(KNOWLEDGE_PATH if KNOWLEDGE_PATH.exists() else ".").free / 1e9
    need = 15 * top / 1_000_000
    if free < need:
        print(f"  ⚠ About {need:.0f} GB is needed for {top:,} articles and {free:.0f} GB is free.")
    print(f"\n📖 Building the {top:,} most linked-to articles → {KNOWLEDGE_PATH / wiki_full.DB_NAME}")
    print("   Takes a few hours. You can stop it and run the same command later to carry on.")
    count = wiki_full.build(dump, index, KNOWLEDGE_PATH / wiki_full.DB_NAME, top=top, workers=workers)
    if count:
        print(f"\n✅ Done. Chat and the Wikipedia section use it from now on.\n"
              f"   The download in {dump.parent} can be deleted to free about 24 GB.")
    return count > 0


def main():
    parser = argparse.ArgumentParser(
        description="Prometheus knowledge base ingestion pipeline"
    )
    parser.add_argument(
        "--source",
        help="Ingest specific source/domain folder only (e.g. 'medical')"
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Clear and rebuild entire vector index from scratch"
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="Create knowledge base folder structure only (no indexing)"
    )
    parser.add_argument(
        "--wikipedia",
        metavar="DUMP_FILE",
        help="Ingest a Wikipedia XML dump file (.xml or .xml.bz2)"
    )
    parser.add_argument(
        "--download-wikipedia",
        action="store_true",
        help="Download the latest Simple English Wikipedia dump, then ingest it"
    )
    parser.add_argument(
        "--download-wikipedia-full",
        action="store_true",
        help="Download English Wikipedia and keep the most linked-to articles (--top, default 1,000,000)"
    )
    parser.add_argument(
        "--wikipedia-full",
        metavar="DUMP_FILE",
        help="Build from an English multistream dump you already have (its -index file beside it)"
    )
    parser.add_argument(
        "--top",
        type=int,
        default=1_000_000,
        metavar="N",
        help="With --download-wikipedia-full / --wikipedia-full: how many articles to keep"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=0,
        metavar="N",
        help="Processes to use for the full Wikipedia build (default: all cores but one)"
    )
    parser.add_argument(
        "--wiki-index",
        action="store_true",
        help="Build the Wikipedia search index from already-extracted articles (minutes)"
    )
    parser.add_argument(
        "--extract-only",
        action="store_true",
        help="With --wikipedia/--download-wikipedia: extract articles but don't index them yet"
    )
    parser.add_argument(
        "--max-articles",
        type=int,
        default=0,
        metavar="N",
        help="Maximum articles to extract from Wikipedia dump (0=all)"
    )
    parser.add_argument(
        "--figures",
        action="store_true",
        help="Note which PDF pages have a figure, so only those are shown under answers (seconds per book)"
    )
    parser.add_argument(
        "--titles",
        action="store_true",
        help="Fill in readable book titles (knowledge_base/titles.json) — seconds"
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show knowledge base statistics"
    )
    args = parser.parse_args()

    if args.init:
        create_sample_knowledge_base()
        return

    if args.wiki_index:
        from core.library.wiki_index import build_index
        ok = build_index(KNOWLEDGE_PATH / "wikipedia", KNOWLEDGE_PATH / "wikipedia_search.sqlite") > 0
        sys.exit(0 if ok else 1)

    if args.download_wikipedia_full or args.wikipedia_full:
        ok = ingest_wikipedia_full(args.wikipedia_full, top=args.top, workers=args.workers)
        sys.exit(0 if ok else 1)

    if args.wikipedia or args.download_wikipedia:
        ok = ingest_wikipedia(args.wikipedia, max_articles=args.max_articles,
                              download=args.download_wikipedia,
                              extract_only=args.extract_only)
        sys.exit(0 if ok else 1)

    if args.figures:
        from core.library import figures
        figures.build(KNOWLEDGE_PATH)
        return

    if args.titles:
        from core.library import titles
        titles.build(KNOWLEDGE_PATH)
        return

    if args.stats:
        _print_stats()
        return

    # Auto-create structure if missing
    if not KNOWLEDGE_PATH.exists():
        print("Knowledge base not found. Creating structure...")
        create_sample_knowledge_base()

    ingester = Ingester(rebuild=args.rebuild)
    ingester.ingest_all(source_filter=args.source)
    # Readable names for any new books (shown under answers)
    from core.library import titles
    titles.build(KNOWLEDGE_PATH)


def _print_stats():
    """Print knowledge base statistics."""
    if not KNOWLEDGE_PATH.exists():
        print("Knowledge base not found.")
        return

    total_files = 0
    total_size = 0
    domain_stats = {}

    for domain_dir in sorted(KNOWLEDGE_PATH.iterdir()):
        if not domain_dir.is_dir():
            continue
        files = list(domain_dir.rglob("*"))
        files = [f for f in files if f.is_file() and f.name != "README.md"]
        if not files:
            continue
        size = sum(f.stat().st_size for f in files)
        domain_stats[domain_dir.name] = (len(files), size)
        total_files += len(files)
        total_size += size

    print(f"\n📊 Knowledge Base Statistics")
    print(f"{'='*50}")
    print(f"{'Domain':<30} {'Files':>6} {'Size':>10}")
    print(f"{'-'*50}")
    for domain, (count, size) in domain_stats.items():
        size_str = f"{size/1024/1024:.1f} MB" if size > 1024*1024 else f"{size/1024:.0f} KB"
        print(f"{domain:<30} {count:>6} {size_str:>10}")
    print(f"{'-'*50}")
    total_str = f"{total_size/1024/1024:.1f} MB"
    print(f"{'TOTAL':<30} {total_files:>6} {total_str:>10}")

    # Check vector DB
    try:
        import chromadb
        client = chromadb.PersistentClient(path="memory/chroma_db")
        col = client.get_collection("prometheus_knowledge")
        print(f"\nVector DB: {col.count():,} chunks indexed")
    except Exception:
        print(f"\nVector DB: not yet indexed (run: python tools/ingest.py)")


if __name__ == "__main__":
    main()
