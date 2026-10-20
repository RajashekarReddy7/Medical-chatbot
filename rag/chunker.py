"""Heading- and paragraph-aware chunking.

Rules that matter clinically:
* A chunk never spans two sections, so a recommendation is not mixed with a different topic.
* A numbered recommendation ("1.2.3 ...") starts a new chunk, so its number stays with its text.
* A qualifier paragraph ("Do not ...", "Unless ...", "However ...", "Contraindicated ...") is always
  kept in the same chunk as the paragraph before it, so contraindications are not separated from
  the recommendation they qualify.
* Consecutive chunks overlap by up to `chunk_overlap` characters (whole paragraphs only).
"""
from __future__ import annotations

import hashlib
import re
from typing import Optional

from .config import RagSettings, get_settings
from .models import Chunk
from .pdf_loader import LoadedDocument, Paragraph

_NUMBERED_REC = re.compile(r"^\s*\d+(\.\d+){1,3}\s+\S")
_QUALIFIER = re.compile(
    r"^\s*(do not|don't|never|avoid|unless|except|however|but |only if|if |contraindicat|caution|"
    r"note:|exceptions?|apart from|not recommended|should not|must not)", re.I)
MIN_CHUNK_CHARS = 200


def _split_long(text: str, limit: int) -> list[str]:
    """Split an over-long paragraph at sentence boundaries (never mid-number or mid-unit)."""
    if len(text) <= limit:
        return [text]
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9•])", text)
    out, cur = [], ""
    for sent in sentences:
        if cur and len(cur) + 1 + len(sent) > limit:
            out.append(cur)
            cur = sent
        else:
            cur = f"{cur} {sent}".strip()
    if cur:
        out.append(cur)
    return out


def _chunk_id(document_id: str, page: int, index: int, text: str) -> str:
    return hashlib.sha1(f"{document_id}|{page}|{index}|{text[:80]}".encode("utf-8")).hexdigest()[:16]


def chunk_document(doc: LoadedDocument, settings: Optional[RagSettings] = None) -> list[Chunk]:
    """Turn one loaded document into provenance-tagged chunks."""
    s = settings or get_settings()
    size, overlap = s.chunk_size, s.chunk_overlap
    src = doc.source

    # Flatten to (page, paragraph) preserving order; split any oversized paragraph.
    units: list[tuple[int, Paragraph]] = []
    for page in doc.pages:
        for para in page.paragraphs:
            for piece in _split_long(para.text, size):
                units.append((page.number, Paragraph(piece, para.section)))

    chunks: list[Chunk] = []
    cur: list[tuple[int, Paragraph]] = []
    fresh = 0  # paragraphs added since the last emit (overlap-only buffers are never emitted)

    def cur_len() -> int:
        return sum(len(p.text) + 1 for _, p in cur)

    def emit(carry_overlap: bool = True):
        nonlocal cur, fresh
        if cur and fresh:
            text = "\n".join(p.text for _, p in cur).strip()
            if text:
                first_page, last_page = cur[0][0], cur[-1][0]
                chunks.append(Chunk(
                    chunk_id=_chunk_id(doc.document_id, first_page, len(chunks), text),
                    document_id=doc.document_id, document_title=src.title, publisher=src.publisher,
                    source_url=src.source_url, publication_date=src.publication_date, version=src.version,
                    page_number=first_page, page_end=last_page, section=cur[0][1].section, text=text,
                    population_min_age=src.population.min_age_years, population_max_age=src.population.max_age_years,
                    population_description=src.population.description,
                ))
        carried: list[tuple[int, Paragraph]] = []
        if carry_overlap:
            total = 0
            for item in reversed(cur):  # carry whole trailing paragraph(s) as overlap
                if total + len(item[1].text) > overlap:
                    break
                carried.insert(0, item)
                total += len(item[1].text)
        cur = carried
        fresh = 0

    for page_no, para in units:
        if cur:
            if para.section != cur[-1][1].section:
                emit(carry_overlap=False)              # never overlap across sections
            else:
                starts_rec = bool(_NUMBERED_REC.match(para.text)) and cur_len() >= MIN_CHUNK_CHARS
                too_big = cur_len() + len(para.text) > size
                if starts_rec or (too_big and not _QUALIFIER.match(para.text)):
                    emit()
        cur.append((page_no, para))
        fresh += 1
    emit(carry_overlap=False)
    return chunks
