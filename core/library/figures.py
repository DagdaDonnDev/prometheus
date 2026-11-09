"""
Which pages of a book actually have a picture on them.

Ingest saves every PDF page as an image (knowledge_base/<folder>/_images/),
so an answer used to show a photo of whatever page the text came from —
usually just more text. This notes the pages with a figure, so only those
are shown, and so "a picture of hemlock" can prefer them.

A page counts as a figure page if:
  Step 1: it has a caption — "Fig. 12", "Figure 3", "Plate IV", "Illustration"
  Step 2: it has much less text than the book's usual page (the rest is a
          drawing) — but isn't nearly blank (title and end pages)
  Step 3: (born-digital PDFs) a picture is placed on it that isn't a
          full-page scan, or it's covered in line drawing
  Step 4: never the first two pages (cover, title page) unless captioned

Scanned books (archive.org) are one full-page image per page, so Step 3
can't tell there — Steps 1 and 2 do the work.

Kept in knowledge_base/<folder>/_images/figures.json: {source: [page numbers]}.
    python tools/ingest.py --figures      (seconds per book; also done by ingest)
"""

import json
import re
from pathlib import Path
from statistics import median
from typing import Dict, List, Optional, Set

_CAPTION = re.compile(r"\b(fig\.?|figure|plate|illustration|diagram)\s*[\divxlc]+", re.I)
_cache: Dict[str, object] = {}


def scan_pdf(path: Path) -> Set[int]:
    """Page numbers (1-based) that have a figure."""
    try:
        try:
            import pymupdf as fitz
        except ImportError:
            import fitz
        doc = fitz.open(str(path))
    except Exception:
        return set()
    pages = []
    try:
        for page in doc:
            text = page.get_text("text") or ""
            words = len(text.split())
            area = abs(page.rect.width * page.rect.height) or 1.0
            placed = 0
            try:
                for info in page.get_image_info():
                    x0, y0, x1, y1 = info.get("bbox", (0, 0, 0, 0))
                    share = abs((x1 - x0) * (y1 - y0)) / area
                    if 0.05 < share < 0.85:          # a picture, not a full-page scan
                        placed += 1
            except Exception:
                pass
            try:
                drawn = len(page.get_drawings()) if not placed else 0
            except Exception:
                drawn = 0
            pages.append((words, bool(_CAPTION.search(text)), placed, drawn))
    finally:
        doc.close()

    typical = median([w for w, *_ in pages if w > 30] or [0])
    out = set()
    for n, (words, caption, placed, drawn) in enumerate(pages, 1):
        if n <= 2 and not caption:
            continue        # Step 4: the cover and title page aren't figures (one came up for "halo")
        sparse = typical and 25 <= words < typical * 0.45
        if caption or sparse or placed or drawn > 40:   # Steps 1, 2, 3
            out.add(n)
    return out


def _path(kb: Path, domain: str) -> Path:
    return kb / domain / "_images" / "figures.json"


def record(kb: Path, domain: str, source: str, pages: Set[int]):
    """Save one book's figure pages."""
    p = _path(kb, domain)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    data[source] = sorted(pages)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data), encoding="utf-8")


def build(kb: Path = Path("knowledge_base"), progress=print) -> int:
    """Note figure pages for every PDF that has page images. Returns books scanned."""
    from core.library.titles import source_key
    done = 0
    for folder in sorted(p for p in kb.iterdir() if p.is_dir()) if kb.is_dir() else []:
        if not (folder / "_images").is_dir():
            continue
        for pdf in sorted(folder.rglob("*.pdf")):
            if "_images" in pdf.parts:
                continue
            pages = scan_pdf(pdf)
            record(kb, folder.name, source_key(pdf), pages)
            done += 1
            progress(f"  {folder.name}/{pdf.name}: {len(pages)} figure page(s)")
    progress(f"  Figures noted for {done} book(s)")
    return done


def figure_pages(domain: str, source: str, kb: Path = Path("knowledge_base")) -> Optional[List[int]]:
    """A book's figure pages, or None if it hasn't been scanned (show every page, as before)."""
    p = _path(kb, domain)
    try:
        mtime = p.stat().st_mtime
    except OSError:
        return None
    key = str(p)
    if _cache.get(key, (None,))[0] != mtime:
        try:
            _cache[key] = (mtime, json.loads(p.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            _cache[key] = (mtime, {})
    pages = _cache[key][1].get(source)
    return None if pages is None else pages


PICTURE_REQUEST = re.compile(
    r"\b(picture|pictures|image|images|photo|photos|photograph|diagram|diagrams|illustration|"
    r"drawing|sketch|show me|what does .{1,40} look like|what do .{1,40} look like|"
    r"how (do|can|would|could|should) (i|you|we) (identify|recognise|recognize|spot|tell)|"
    r"how to (identify|recognise|recognize|spot|tell))\b", re.I)


def wants_picture(query: str) -> bool:
    return bool(PICTURE_REQUEST.search(query or ""))
