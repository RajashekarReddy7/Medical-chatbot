"""Index building. Runs offline (via `python -m scripts.ingest_guidelines`), never inside a patient request."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from .chunker import chunk_document
from .config import RagSettings, get_settings
from .embeddings import Embedder, get_embedder
from .pdf_loader import LoadedDocument, load_all
from .vector_store import VectorStore, open_store

log = logging.getLogger("carebot.rag.ingest")
BATCH = 64


@dataclass
class DocReport:
    file: str
    status: str = ""                  # indexed | unchanged | skipped | excluded | failed | removed
    chunks: int = 0
    pages: int = 0
    empty_pages: list[int] = field(default_factory=list)
    failed_pages: list[int] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


@dataclass
class IngestReport:
    embedder: str = ""
    store: str = ""
    rebuilt: bool = False
    documents: list[DocReport] = field(default_factory=list)
    total_chunks: int = 0
    seconds: float = 0.0

    def summary_lines(self) -> list[str]:
        lines = [f"Embedder : {self.embedder}", f"Store    : {self.store}{' (rebuilt from scratch)' if self.rebuilt else ''}"]
        for d in self.documents:
            extra = f", {d.chunks} chunks, {d.pages} pages" if d.status in ("indexed", "unchanged") else ""
            lines.append(f"  [{d.status:<9}] {d.file}{extra}")
            for p in d.problems:
                lines.append(f"      ! {p}")
        lines.append(f"Total chunks in index: {self.total_chunks}  ({self.seconds:.1f}s)")
        return lines


def ingest(settings: Optional[RagSettings] = None, rebuild: bool = False,
           embedder: Optional[Embedder] = None, store: Optional[VectorStore] = None,
           docs: Optional[list[LoadedDocument]] = None) -> IngestReport:
    """Add/update/remove documents so the index matches the PDF folder. Idempotent."""
    t0 = time.time()
    s = settings or get_settings()
    emb = embedder or get_embedder(s)
    st = store or open_store(s)
    report = IngestReport(embedder=emb.name, store=st.kind)

    m = st.manifest.data
    if m.get("embedder") and m["embedder"] != emb.name:
        log.warning("embedder changed (%s -> %s): rebuilding the index", m["embedder"], emb.name)
        rebuild = True
    if rebuild:
        st.reset()
        report.rebuilt = True
    m = st.manifest.data
    m["embedder"] = emb.name

    loaded = docs if docs is not None else load_all(s)
    wanted_ids = {d.document_id for d in loaded if d.usable}

    # remove documents that were deleted or replaced (same file name, new content hash)
    for doc_id, info in list(st.documents().items()):
        if doc_id not in wanted_ids:
            st.delete_document(doc_id)
            del st.documents()[doc_id]
            report.documents.append(DocReport(file=info.get("file", doc_id), status="removed"))

    for d in loaded:
        rep = DocReport(file=d.path.name, pages=len(d.pages), empty_pages=d.empty_pages,
                        failed_pages=d.failed_pages, problems=list(d.problems))
        if not d.usable:
            rep.status = "skipped" if d.duplicate_of else ("excluded" if not d.source.index else "failed")
            report.documents.append(rep)
            continue
        if d.document_id in st.documents() and not rebuild:
            rep.status, rep.chunks = "unchanged", st.documents()[d.document_id]["chunks"]
            report.documents.append(rep)
            continue
        chunks = chunk_document(d, s)
        if not chunks:
            rep.status = "failed"
            rep.problems.append("Document produced no chunks.")
            report.documents.append(rep)
            continue
        for i in range(0, len(chunks), BATCH):
            batch = chunks[i:i + BATCH]
            st.add(batch, emb.embed([c.text for c in batch]))
        st.documents()[d.document_id] = {
            "file": d.path.name, "sha256": d.content_hash, "chunks": len(chunks), "pages": len(d.pages),
            "title": d.source.title, "publisher": d.source.publisher, "source_url": d.source.source_url,
            "publication_date": d.source.publication_date,
        }
        rep.status, rep.chunks = "indexed", len(chunks)
        report.documents.append(rep)

    m["store"] = st.kind
    m["dim"] = int(emb.embed(["dimension probe"]).shape[1])
    st.manifest.save()
    report.total_chunks = st.count()
    report.seconds = time.time() - t0
    return report
