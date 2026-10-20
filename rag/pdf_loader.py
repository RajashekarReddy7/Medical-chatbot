"""PDF discovery and text extraction (PyMuPDF).

Produces, for each guideline PDF, a list of `PageText` objects whose paragraphs are
tagged with the section heading they appear under. Nothing is silently dropped:
empty, unreadable or probably-scanned documents are reported in `LoadedDocument.problems`.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import statistics
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .config import RagSettings, get_settings
from .models import SourceInfo

log = logging.getLogger("carebot.rag.pdf")

MIN_CHARS_PER_PAGE = 40          # below this a page is considered "empty"
SCANNED_EMPTY_RATIO = 0.6        # more empty pages than this => probably a scanned PDF
_LIST_START = re.compile(r"^\s*(?:\d+(?:\.\d+)*[.)]?|[•\-–▪●○■]|\([a-z0-9]{1,3}\))\s+")


@dataclass
class Paragraph:
    text: str
    section: str


@dataclass
class PageText:
    number: int                      # 1-based, as printed by PDF viewers
    paragraphs: list[Paragraph] = field(default_factory=list)
    char_count: int = 0
    ocr_used: bool = False


@dataclass
class LoadedDocument:
    path: Path
    document_id: str                 # stable: derived from the content hash
    content_hash: str
    source: SourceInfo
    pages: list[PageText] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    empty_pages: list[int] = field(default_factory=list)
    failed_pages: list[int] = field(default_factory=list)
    duplicate_of: Optional[str] = None
    usable: bool = True              # False => must not be indexed


# ------------------------------------------------------------------ sources.json
def load_sources(settings: Optional[RagSettings] = None) -> dict[str, SourceInfo]:
    """Read the provenance manifest. Keys are PDF file names."""
    s = settings or get_settings()
    if not s.guideline_sources_file.exists():
        return {}
    raw = json.loads(s.guideline_sources_file.read_text(encoding="utf-8"))
    entries = raw["documents"] if isinstance(raw, dict) else raw
    return {e["file"]: SourceInfo(**e) for e in entries}


def discover_pdfs(pdf_dir: Path) -> list[Path]:
    """All *.pdf files in the folder, sorted for deterministic ingestion order."""
    if not pdf_dir.exists():
        return []
    return sorted(p for p in pdf_dir.iterdir() if p.is_file() and p.suffix.lower() == ".pdf")


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


# ------------------------------------------------------------------ text helpers
def normalize_inline(text: str) -> str:
    """Collapse runs of spaces and fix hyphenation without touching digits, units or symbols."""
    text = text.replace("­", "")                       # soft hyphen
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)           # "pre-\nscribing" -> "prescribing"
    text = re.sub(r"[ \t ]+", " ", text)
    return text.strip()


def _is_running_header_footer(line: str, repeated: set[str]) -> bool:
    t = line.strip().lower()
    # bare page numbers and "Page 5 of 42" / "Page 5 of" (NICE splits the total onto its own line)
    return line in repeated or bool(re.fullmatch(r"(page\s*)?\d{1,4}(\s*(of|/)\s*\d{1,4})?|page\s*\d{1,4}\s*of", t))


def _page_lines(page) -> list[dict]:
    """Return text lines with their dominant font size and boldness (PyMuPDF 'dict' mode)."""
    lines: list[dict] = []
    data = page.get_text("dict")
    for block in data.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = [s for s in line.get("spans", []) if s.get("text", "").strip()]
            if not spans:
                continue
            text = "".join(s["text"] for s in spans)
            size = max(s["size"] for s in spans)
            bold = all((s.get("flags", 0) & 16) or "bold" in s.get("font", "").lower() for s in spans)
            lines.append({"text": text, "size": round(size, 1), "bold": bool(bold), "y0": line["bbox"][1], "block": id(block)})
    return lines


def _looks_like_heading(line: dict, body_size: float) -> bool:
    t = line["text"].strip()
    if not t or len(t) > 120 or t.endswith((".", ",", ";")) and not re.match(r"^\d", t):
        return False
    bigger = line["size"] >= body_size * 1.12
    numbered_bold = line["bold"] and bool(re.match(r"^\d+(\.\d+)*\s+\S", t))
    return bigger or numbered_bold or (line["bold"] and len(t) < 70 and not _LIST_START.match(t))


def _paragraphs_from_lines(lines: list[dict], body_size: float, section: str, repeated: set[str]) -> tuple[list[Paragraph], str]:
    """Group lines into paragraphs; headings update `section` instead of becoming paragraphs."""
    paragraphs: list[Paragraph] = []
    buf: list[str] = []
    prev_y: Optional[float] = None
    last_was_heading = False

    def flush():
        nonlocal buf
        if buf:
            txt = normalize_inline("\n".join(buf)).replace("\n", " ")
            if txt:
                paragraphs.append(Paragraph(txt, section))
            buf = []

    for ln in lines:
        text = ln["text"].strip()
        if not text or _is_running_header_footer(text, repeated):
            continue
        if _looks_like_heading(ln, body_size):
            flush()
            # a heading that wraps onto a second line is one section name, not two
            wrapped = last_was_heading and prev_y is not None and abs(ln["y0"] - prev_y) < body_size * 2.2
            section = f"{section} {text}".strip() if wrapped else text
            last_was_heading = True
            prev_y = ln["y0"]
            continue
        last_was_heading = False
        gap = prev_y is not None and (ln["y0"] - prev_y) > body_size * 1.9
        if buf and (_LIST_START.match(text) or gap):
            flush()
        buf.append(text)
        prev_y = ln["y0"]
    flush()
    return paragraphs, section


def _ocr_page_text(page) -> str:
    """OCR one page with PyMuPDF's Tesseract integration. Requires a Tesseract install."""
    tp = page.get_textpage_ocr(language="eng", dpi=200, full=True)
    return page.get_text("text", textpage=tp)


# ------------------------------------------------------------------ main entry point
def load_pdf(path: Path, source: Optional[SourceInfo] = None, settings: Optional[RagSettings] = None) -> LoadedDocument:
    """Extract one PDF. Never raises: failures are recorded in `problems` and `usable=False`."""
    s = settings or get_settings()
    try:
        import pymupdf as fitz  # PyMuPDF (older releases only provide the `fitz` import name)
    except ImportError:
        try:
            import fitz  # type: ignore[no-redef]
        except ImportError as e:  # pragma: no cover - dependency problem, reported clearly
            raise RuntimeError("PyMuPDF is required: pip install pymupdf") from e

    chash = file_hash(path)
    src = source or SourceInfo(file=path.name, title=path.stem.replace("_", " "), publisher="UNKNOWN", source_url="")
    doc = LoadedDocument(path=path, document_id=f"{path.stem}-{chash[:8]}", content_hash=chash, source=src)

    if source is None:
        doc.problems.append("No entry in sources.json: publisher, URL and date are unknown; add provenance before relying on it.")
    elif not source.index:
        doc.problems.append("Excluded by sources.json (\"index\": false). " + source.index_note)
        doc.usable = False
        return doc

    try:
        pdf = fitz.open(path)
    except Exception as e:
        doc.problems.append(f"Cannot open PDF (corrupt or encrypted?): {e}")
        doc.usable = False
        return doc

    with pdf:
        if pdf.needs_pass:
            doc.problems.append("PDF is password-protected.")
            doc.usable = False
            return doc
        if pdf.page_count == 0:
            doc.problems.append("PDF has no pages.")
            doc.usable = False
            return doc

        # Pass 1: collect lines per page + body font size + repeated header/footer lines.
        per_page: dict[int, list[dict]] = {}
        for i, page in enumerate(pdf, start=1):
            try:
                per_page[i] = _page_lines(page)
            except Exception as e:
                doc.failed_pages.append(i)
                doc.problems.append(f"Page {i}: extraction failed ({e}).")
                per_page[i] = []

        sizes = [ln["size"] for lines in per_page.values() for ln in lines for _ in range(max(1, len(ln["text"]) // 20))]
        body_size = statistics.median(sizes) if sizes else 10.0
        counts = Counter(ln["text"].strip() for lines in per_page.values() for ln in lines)
        threshold = max(3, int(0.4 * pdf.page_count))
        repeated = {t for t, c in counts.items() if c >= threshold and len(t) < 140}

        # Pass 2: build paragraphs with section tracking across pages.
        section = ""
        for i, page in enumerate(pdf, start=1):
            lines = per_page.get(i, [])
            chars = sum(len(ln["text"].strip()) for ln in lines)
            page_text = PageText(number=i, char_count=chars)
            if chars < MIN_CHARS_PER_PAGE and i not in doc.failed_pages:
                if s.ocr_enabled:
                    try:
                        ocr = _ocr_page_text(page)
                        if len(ocr.strip()) >= MIN_CHARS_PER_PAGE:
                            lines = [{"text": t, "size": body_size, "bold": False, "y0": float(n) * body_size * 1.3, "block": 0}
                                     for n, t in enumerate(ocr.splitlines()) if t.strip()]
                            page_text.char_count = sum(len(t["text"]) for t in lines)
                            page_text.ocr_used = True
                    except Exception as e:
                        doc.problems.append(f"Page {i}: OCR failed ({e}). Is Tesseract installed?")
                if not page_text.ocr_used:
                    doc.empty_pages.append(i)
            paragraphs, section = _paragraphs_from_lines(lines, body_size, section, repeated)
            page_text.paragraphs = paragraphs
            doc.pages.append(page_text)

    total = len(doc.pages)
    usable_chars = sum(p.char_count for p in doc.pages)
    if usable_chars == 0:
        doc.problems.append("No extractable text. This looks like a scanned PDF; enable RAG_OCR_ENABLED=true (needs Tesseract) or supply a text PDF.")
        doc.usable = False
    elif len(doc.empty_pages) / total > SCANNED_EMPTY_RATIO:
        doc.problems.append(f"{len(doc.empty_pages)}/{total} pages have no text; the PDF is probably scanned and the index would be incomplete.")
        doc.usable = False
    elif doc.empty_pages:
        doc.problems.append(f"{len(doc.empty_pages)} page(s) without text were skipped: {doc.empty_pages[:10]}")
    log.info("loaded %s: %d pages, usable=%s, problems=%d", path.name, total, doc.usable, len(doc.problems))
    return doc


def load_all(settings: Optional[RagSettings] = None) -> list[LoadedDocument]:
    """Load every PDF in the configured folder and mark content-duplicates as unusable."""
    s = settings or get_settings()
    sources = load_sources(s)
    docs: list[LoadedDocument] = []
    seen: dict[str, str] = {}
    for path in discover_pdfs(s.guideline_pdf_dir):
        d = load_pdf(path, sources.get(path.name), s)
        if d.content_hash in seen:
            d.duplicate_of = seen[d.content_hash]
            d.usable = False
            d.problems.append(f"Duplicate of {seen[d.content_hash]} (identical file content); not indexed twice.")
        else:
            seen[d.content_hash] = path.name
        docs.append(d)
    return docs
