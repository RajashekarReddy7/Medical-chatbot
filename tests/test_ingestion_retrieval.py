"""PDF loading, chunking, indexing and retrieval (no LLM involved)."""
import sys

import pytest

from rag.chunker import chunk_document
from rag.embeddings import HashingEmbedder
from rag.ingest import ingest
from rag.models import PatientContext
from rag.pdf_loader import discover_pdfs, load_all, load_pdf, load_sources
from rag.retriever import RetrievalError, Retriever
from rag.vector_store import LocalStore, VectorStoreError, open_store, reset_store_cache
from tests.helpers import build_kb, build_retriever, build_settings, write_pdf


# ----------------------------------------------------------------------------- loading
def test_pages_sections_and_footer_removal(kb):
    settings, _ = kb
    docs = {d.path.name: d for d in load_all(settings)}
    cough = docs["cough_adult.pdf"]
    assert cough.usable and len(cough.pages) == 3
    sections = {p.section for page in cough.pages for p in page.paragraphs}
    assert any("Antibiotics" in s for s in sections)
    assert any("Pregnancy" in s for s in sections)
    all_text = " ".join(p.text for page in cough.pages for p in page.paragraphs)
    assert "Synthetic Test Footer" not in all_text, "repeated footer should be stripped"
    assert "1.1.1 Do not offer an antibiotic" in all_text, "recommendation numbers must survive extraction"


def test_provenance_comes_from_sources_json(kb):
    settings, _ = kb
    doc = next(d for d in load_all(settings) if d.path.name == "cough_adult.pdf")
    assert doc.source.publisher == "Synthetic Health Authority A"
    assert doc.source.publication_date == "2024-05-01"


def test_unparseable_pdf_is_reported_not_raised(tmp_path):
    bad = tmp_path / "broken.pdf"
    bad.write_bytes(b"this is not a pdf at all")
    doc = load_pdf(bad)
    assert doc.usable is False
    assert any("Cannot open PDF" in p for p in doc.problems)


def test_scanned_or_empty_pdf_is_detected(tmp_path):
    import pymupdf
    d = pymupdf.open()
    for _ in range(3):
        d.new_page()                       # pages with no text at all
    p = tmp_path / "scan.pdf"
    d.save(p)
    doc = load_pdf(p)
    assert doc.usable is False
    assert any("scanned" in x.lower() or "no extractable text" in x.lower() for x in doc.problems)


def test_missing_provenance_is_flagged(tmp_path):
    p = tmp_path / "mystery.pdf"
    write_pdf(p, [[("Heading", 14, True), ("Some body text that is long enough to count as a real page of content here.", 10, False)]] * 3)
    doc = load_pdf(p, source=None)
    assert any("No entry in sources.json" in x for x in doc.problems)
    assert doc.source.publisher == "UNKNOWN"


# ----------------------------------------------------------------------------- chunking
def test_chunks_carry_metadata_and_page_numbers(kb):
    settings, _ = kb
    doc = next(d for d in load_all(settings) if d.path.name == "cough_adult.pdf")
    chunks = chunk_document(doc, settings)
    assert chunks
    for c in chunks:
        assert c.document_title and c.publisher and c.source_url
        assert 1 <= c.page_number <= c.page_end <= 3
        assert c.chunk_id
    assert len({c.chunk_id for c in chunks}) == len(chunks), "chunk ids must be unique"


def test_exception_stays_with_its_recommendation(kb):
    """Contraindication/exception text must not be separated from the recommendation it qualifies."""
    settings, _ = kb
    doc = next(d for d in load_all(settings) if d.path.name == "cough_adult.pdf")
    chunks = chunk_document(doc, settings)
    holder = [c for c in chunks if "Do not offer doxycycline" in c.text]
    assert len(holder) == 1
    assert "penicillin allergy" in holder[0].text


def test_chunks_do_not_cross_sections(kb):
    settings, _ = kb
    doc = next(d for d in load_all(settings) if d.path.name == "cough_adult.pdf")
    for c in chunk_document(doc, settings):
        assert not ("Do not offer an antibiotic" in c.text and "Do not offer doxycycline" in c.text)


# ----------------------------------------------------------------------------- ingestion
def test_ingest_is_idempotent_and_skips_duplicates(tmp_path):
    settings = build_kb(tmp_path)
    shutil_copy = (settings.guideline_pdf_dir / "cough_adult.pdf").read_bytes()
    (settings.guideline_pdf_dir / "cough_adult_copy.pdf").write_bytes(shutil_copy)   # identical content
    emb, store = HashingEmbedder(), LocalStore(settings.persist_dir)

    first = ingest(settings, embedder=emb, store=store)
    statuses = {d.file: d.status for d in first.documents}
    assert statuses["cough_adult.pdf"] == "indexed"
    assert statuses["cough_adult_copy.pdf"] == "skipped"          # duplicate never indexed twice
    n = store.count()
    assert n > 0

    second = ingest(settings, embedder=emb, store=store)
    assert {d.status for d in second.documents if d.file == "cough_adult.pdf"} == {"unchanged"}
    assert store.count() == n


def test_ingest_removes_deleted_and_replaced_documents(tmp_path):
    settings = build_kb(tmp_path)
    emb, store = HashingEmbedder(), LocalStore(settings.persist_dir)
    ingest(settings, embedder=emb, store=store)
    before = store.count()
    (settings.guideline_pdf_dir / "paediatric_fever.pdf").unlink()
    rep = ingest(settings, embedder=emb, store=store)
    assert any(d.status == "removed" for d in rep.documents)
    assert store.count() < before
    assert all("paracetamol" not in c.text.lower() for c in store.all_chunks())


def test_ingest_reports_failed_documents(tmp_path):
    settings = build_kb(tmp_path)
    (settings.guideline_pdf_dir / "garbage.pdf").write_bytes(b"%PDF-1.4 broken")
    rep = ingest(settings, embedder=HashingEmbedder(), store=LocalStore(settings.persist_dir))
    bad = next(d for d in rep.documents if d.file == "garbage.pdf")
    assert bad.status == "failed" and bad.problems
    assert rep.total_chunks > 0, "one bad file must not stop the others"


def test_excluded_source_is_not_indexed(tmp_path):
    import json
    settings = build_kb(tmp_path)
    data = json.loads(settings.guideline_sources_file.read_text())
    for d in data["documents"]:
        if d["file"] == "old_sore_throat.pdf":
            d["index"] = False
            d["index_note"] = "too old"
    settings.guideline_sources_file.write_text(json.dumps(data))
    store = LocalStore(settings.persist_dir)
    rep = ingest(settings, embedder=HashingEmbedder(), store=store)
    assert next(d for d in rep.documents if d.file == "old_sore_throat.pdf").status == "excluded"
    assert all("Gargle" not in c.text for c in store.all_chunks())


def test_embedder_change_requires_rebuild(tmp_path):
    settings = build_kb(tmp_path)
    store = LocalStore(settings.persist_dir)
    ingest(settings, embedder=HashingEmbedder(512), store=store)
    r = Retriever(store=store, embedder=HashingEmbedder(1024), settings=settings)
    with pytest.raises(RetrievalError, match="Re-run"):
        r.retrieve("Advise rest for cough")


# ----------------------------------------------------------------------------- retrieval
def test_retrieval_returns_real_passages_with_metadata(retriever):
    res = retriever.retrieve("Do not offer an antibiotic to adults with acute cough", PatientContext(age=30, symptoms=["cough"]))
    assert not res.no_evidence
    top = res.passages[0].chunk
    assert "antibiotic" in top.text.lower()
    assert top.page_number >= 1 and top.source_url.startswith("https://")


def test_no_evidence_for_unrelated_query(retriever):
    res = retriever.retrieve("Apply a warm compress to the knee after sports injury")
    assert res.no_evidence and res.passages == []
    assert "threshold" in res.note.lower()


def test_empty_index_gives_explicit_no_evidence(tmp_path):
    settings = build_settings(tmp_path)
    r = Retriever(store=LocalStore(settings.persist_dir), embedder=HashingEmbedder(), settings=settings)
    res = r.retrieve("anything")
    assert res.no_evidence and "empty" in res.note.lower()


def test_critical_terms_are_tracked(retriever):
    res = retriever.retrieve("Take ciprofloxacin 500 mg twice daily for cough")
    assert "ciprofloxacin" in res.critical_terms
    assert "ciprofloxacin" in res.missing_critical_terms      # no indexed passage mentions it


def test_top_k_and_deduplication(kb):
    settings, r = kb
    res = r.retrieve("antibiotic adults acute cough", top_k=2, min_relevance=0.0)
    assert len(res.passages) <= 2
    texts = [p.chunk.text for p in res.passages]
    assert len(texts) == len(set(texts))


def test_stale_flag_for_old_source(retriever):
    res = retriever.retrieve("Gargle with warm salty water for sore throat", min_relevance=0.1)
    old = [p for p in res.passages if "Historic" in p.chunk.document_title]
    assert old and old[0].source_stale is True


def test_store_failure_becomes_retrieval_error(kb):
    settings, _ = kb

    class Broken(LocalStore):
        def search(self, embedding, k):
            raise VectorStoreError("simulated outage")

    store = Broken(settings.persist_dir)
    r = Retriever(store=store, embedder=HashingEmbedder(), settings=settings)
    with pytest.raises(RetrievalError, match="unavailable"):
        r.retrieve("cough")


def test_chroma_missing_is_reported_cleanly(tmp_path, monkeypatch):
    reset_store_cache()
    monkeypatch.setitem(sys.modules, "chromadb", None)       # makes `import chromadb` fail
    settings = build_settings(tmp_path)
    with pytest.raises(VectorStoreError, match="not installed"):
        open_store(settings, backend="chroma", directory=tmp_path / "chroma_missing")
    # auto mode falls back to the local store instead of crashing
    assert open_store(settings, backend="auto", directory=tmp_path / "fallback").kind == "local"
    reset_store_cache()


def test_corrupt_manifest_is_detected(tmp_path):
    d = tmp_path / "idx"
    d.mkdir()
    (d / "manifest.json").write_text("{not json")
    with pytest.raises(VectorStoreError, match="corrupt"):
        LocalStore(d)
