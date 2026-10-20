"""Synthetic knowledge base for tests. EVERYTHING here is fictional test text, never real guidance.

The documents are generated as real PDFs (with PyMuPDF) so the whole pipeline - extraction, headings,
chunking, indexing, retrieval - is exercised end to end without any network, model download or Ollama.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pymupdf

from rag.config import RagSettings
from rag.embeddings import HashingEmbedder
from rag.ingest import ingest
from rag.judges import HeuristicJudge, OllamaJudge
from rag.retriever import Retriever
from rag.vector_store import LocalStore
from rag.verifier import GuidelineVerifier

H1, BODY = 16, 10

COUGH_ADULT = [  # (text, size, bold)
    [("Synthetic Acute Cough Guideline (TEST ONLY)", H1, True),
     ("Antibiotics for acute cough", 13, True),
     ("1.1.1 Do not offer an antibiotic to adults with acute cough who are otherwise well. Explain that antibiotics are not needed because the cough usually resolves without them.", BODY, False),
     ("1.1.2 Offer an immediate antibiotic prescription only if the person is systemically very unwell.", BODY, False)],
    [("Pregnancy", 13, True),
     ("1.2.1 Do not offer doxycycline to pregnant women with acute cough. Amoxicillin is preferred in pregnancy.", BODY, False),
     ("Exception: if the person has a penicillin allergy, discuss the options with a specialist before prescribing.", BODY, False),
     ("Self care", 13, True),
     ("1.3.1 Advise adequate fluid intake and rest for acute cough. Honey may be used for symptom relief in people aged over 1 year.", BODY, False)],
    [("When to seek help", 13, True),
     ("1.4.1 Advise people to seek urgent help if they develop severe breathlessness or cough up blood.", BODY, False),
     ("Duration", 13, True),
     ("1.5.1 Acute cough usually lasts up to 3 weeks and often improves without treatment.", BODY, False)],
]
COUGH_OTHER_PUBLISHER = [
    [("Synthetic Cough Statement from Another Publisher (TEST ONLY)", H1, True),
     ("Antibiotic strategy", 13, True),
     ("2.1.1 Offer a delayed antibiotic prescription to adults with acute cough, to be used if symptoms worsen.", BODY, False)],
    [("Review", 13, True), ("2.2.1 Review adults with acute cough after one week if symptoms have not improved.", BODY, False)],
    [("Notes", 13, True), ("2.3.1 Record the decision about antibiotics in the patient notes.", BODY, False)],
]
PAEDIATRIC = [
    [("Synthetic Paediatric Fever Guideline (TEST ONLY)", H1, True),
     ("Treating fever in young children", 13, True),
     ("3.1.1 Give paracetamol 15 mg per kg to children under 5 years with fever who are distressed.", BODY, False)],
    [("Monitoring", 13, True), ("3.2.1 Check the child again after four hours.", BODY, False)],
    [("Advice", 13, True), ("3.3.1 Keep the child hydrated with frequent small drinks.", BODY, False)],
]
OLD_DOC = [
    [("Synthetic Historic Guideline (TEST ONLY)", H1, True),
     ("Sore throat", 13, True),
     ("4.1.1 Gargle with warm salty water for relief of acute sore throat.", BODY, False)],
    [("More", 13, True), ("4.2.1 Lozenges may soothe sore throat.", BODY, False)],
    [("End", 13, True), ("4.3.1 Seek review if the sore throat lasts more than a week.", BODY, False)],
]

SOURCES = [
    {"file": "cough_adult.pdf", "title": "Synthetic Acute Cough Guideline", "publisher": "Synthetic Health Authority A",
     "source_url": "https://example.test/cough-a", "publication_date": "2024-05-01",
     "population": {"min_age_years": 18, "max_age_years": None, "description": "Adults"}},
    {"file": "cough_other.pdf", "title": "Synthetic Cough Statement", "publisher": "Synthetic Society B",
     "source_url": "https://example.test/cough-b", "publication_date": "2023-01-01",
     "population": {"min_age_years": 18, "max_age_years": None, "description": "Adults"}},
    {"file": "paediatric_fever.pdf", "title": "Synthetic Paediatric Fever Guideline", "publisher": "Synthetic Health Authority A",
     "source_url": "https://example.test/fever", "publication_date": "2024-02-01",
     "population": {"min_age_years": 0, "max_age_years": 5, "description": "Children under 5"}},
    {"file": "old_sore_throat.pdf", "title": "Synthetic Historic Guideline", "publisher": "Synthetic Archive",
     "source_url": "https://example.test/old", "publication_date": "1998-01-01",
     "population": {"min_age_years": 0, "max_age_years": None, "description": "Everyone"}},
]


def write_pdf(path: Path, pages: list[list[tuple[str, int, bool]]]) -> None:
    """Render (text, font size, bold) blocks into a multi-page PDF with a repeated footer."""
    doc = pymupdf.open()
    for items in pages:
        page = doc.new_page()
        y = 60.0
        for text, size, bold in items:
            lines = math.ceil(len(text) * size * 0.52 / 480) + 1
            h = lines * size * 1.35
            page.insert_textbox(pymupdf.Rect(60, y, 540, y + h), text, fontsize=size, fontname="hebo" if bold else "helv")
            y += h + (size * 1.2)
        page.insert_text((60, 800), "(c) Synthetic Test Footer - not real guidance", fontsize=8)
    doc.save(path)
    doc.close()


def build_settings(root: Path, **overrides) -> RagSettings:
    base = dict(guideline_pdf_dir=root / "pdfs", guideline_sources_file=root / "sources.json", persist_dir=root / "index",
                embedding_backend="hashing", vector_backend="local", judge="heuristic",
                chunk_size=600, chunk_overlap=100, top_k=4, min_relevance=0.25, max_source_age_years=10)
    base.update(overrides)
    return RagSettings(**base)


def build_kb(root: Path, with_old: bool = True) -> RagSettings:
    """Write the synthetic PDFs + sources.json under `root` and return settings pointing at them."""
    (root / "pdfs").mkdir(parents=True, exist_ok=True)
    write_pdf(root / "pdfs" / "cough_adult.pdf", COUGH_ADULT)
    write_pdf(root / "pdfs" / "cough_other.pdf", COUGH_OTHER_PUBLISHER)
    write_pdf(root / "pdfs" / "paediatric_fever.pdf", PAEDIATRIC)
    sources = list(SOURCES)
    if with_old:
        write_pdf(root / "pdfs" / "old_sore_throat.pdf", OLD_DOC)
    else:
        sources = [s for s in sources if s["file"] != "old_sore_throat.pdf"]
    (root / "sources.json").write_text(json.dumps({"documents": sources}), encoding="utf-8")
    return build_settings(root)


def build_retriever(settings: RagSettings) -> Retriever:
    emb, store = HashingEmbedder(), LocalStore(settings.persist_dir)
    ingest(settings, embedder=emb, store=store)
    return Retriever(store=store, embedder=emb, settings=settings)


class FakeLLM:
    """Scripted stand-in for Ollama: returns queued responses (strings) or raises queued exceptions."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        r = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(r, Exception):
            raise r
        return r


def verifier_with(retriever: Retriever, llm: FakeLLM | None = None, heuristic: bool = False) -> GuidelineVerifier:
    judge = HeuristicJudge() if heuristic else OllamaJudge(llm=llm)
    return GuidelineVerifier(retriever=retriever, judge=judge, settings=retriever.settings)
