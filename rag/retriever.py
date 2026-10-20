"""Hybrid retrieval: vector similarity + IDF-weighted keyword coverage.

Important: `relevance` only says "this passage is about the same thing as the query".
It is never evidence that a recommendation is correct; the verifier decides that.
"""
from __future__ import annotations

import logging
import math
import re
import threading
from datetime import date
from typing import Optional

import numpy as np

from .config import RagSettings, get_settings
from .embeddings import Embedder, EmbeddingError, IndexMismatchError, get_embedder
from .models import Chunk, PatientContext, RetrievalResult, RetrievedPassage
from .text_utils import critical_terms, is_recommendation, jaccard, stem, term_in_text, tokenize
from .vector_store import VectorStore, VectorStoreError, open_store

log = logging.getLogger("carebot.rag.retrieve")

VECTOR_WEIGHT_SEMANTIC = 0.5
VECTOR_WEIGHT_LEXICAL_EMBEDDER = 0.3
DEDUP_JACCARD = 0.85
RECOMMENDATION_BOOST = 0.04


class RetrievalError(RuntimeError):
    """Raised when the knowledge base cannot be queried (store/embedder failure)."""


def _year(d: Optional[str]) -> Optional[int]:
    if not d:
        return None
    m = re.search(r"(19|20)\d{2}", d)
    return int(m.group(0)) if m else None


def age_group_terms(age: Optional[float], pregnant: Optional[bool]) -> list[str]:
    terms = []
    if age is not None:
        terms += ["child", "children"] if age < 12 else (["young", "people", "adolescent"] if age < 18 else (["adult"] if age < 65 else ["adult", "older"]))
    if pregnant:
        terms += ["pregnancy"]
    return terms


def build_query(recommendation: str, patient: Optional[PatientContext] = None) -> str:
    """Recommendation first (it carries the drug/negation qualifiers), then key patient context."""
    parts = [recommendation.strip()]
    if patient:
        # Keep the added context short: every extra word dilutes the recommendation's own terms.
        # (Duration is deliberately left out; it matches guideline text only by accident.)
        parts += patient.symptoms[:2]
        parts += age_group_terms(patient.age, patient.pregnant)
    return " ".join(p for p in parts if p)


class _Lexicon:
    """Per-index document frequencies for IDF-weighted coverage."""

    def __init__(self, chunks: list[Chunk]):
        self.token_sets = [set(tokenize(c.text)) for c in chunks]
        n = max(len(chunks), 1)
        df: dict[str, int] = {}
        for ts in self.token_sets:
            for t in ts:
                df[t] = df.get(t, 0) + 1
        self.idf = {t: math.log(1 + n / c) for t, c in df.items()}
        self.n = n

    def weight(self, token: str) -> float:
        return self.idf.get(token, math.log(1 + self.n))  # unseen term: rare => high weight

    def coverage(self, query_tokens: set[str], idx: int) -> float:
        if not query_tokens:
            return 0.0
        total = sum(self.weight(t) for t in query_tokens)
        hit = sum(self.weight(t) for t in query_tokens if t in self.token_sets[idx])
        return hit / total if total else 0.0


class Retriever:
    def __init__(self, store: Optional[VectorStore] = None, embedder: Optional[Embedder] = None,
                 settings: Optional[RagSettings] = None):
        self.settings = settings or get_settings()
        self._store = store
        self._embedder = embedder
        self._lex: Optional[_Lexicon] = None
        self._lex_chunks: list[Chunk] = []
        self._lex_version: Optional[str] = None
        self._lock = threading.Lock()

    # ----- lazy, shared resources (loaded once, reused across requests)
    @property
    def store(self) -> VectorStore:
        if self._store is None:
            try:
                self._store = open_store(self.settings)
            except VectorStoreError as e:
                raise RetrievalError(f"knowledge base unavailable: {e}") from e
        return self._store

    @property
    def embedder(self) -> Embedder:
        if self._embedder is None:
            try:
                self._embedder = get_embedder(self.settings)
            except EmbeddingError as e:
                raise RetrievalError(f"embedding model unavailable: {e}") from e
        return self._embedder

    def _lexicon(self) -> tuple[_Lexicon, list[Chunk]]:
        with self._lock:
            self.store.reload_manifest()
            ver = self.store.version_token()
            if self._lex is None or ver != self._lex_version:
                self._lex_chunks = self.store.all_chunks()
                self._lex = _Lexicon(self._lex_chunks)
                self._lex_version = ver
            return self._lex, self._lex_chunks

    def status(self) -> dict:
        try:
            m = self.store.manifest.data
            return {"store": self.store.kind, "embedder": m.get("embedder"), "chunks": self.store.count(),
                    "documents": [{"file": v["file"], "title": v["title"], "publisher": v["publisher"],
                                   "publication_date": v.get("publication_date"), "chunks": v["chunks"]}
                                  for v in self.store.documents().values()], "updated": m.get("updated")}
        except (VectorStoreError, RetrievalError) as e:
            return {"error": str(e)}

    # ----- main entry point
    def retrieve(self, recommendation: str, patient: Optional[PatientContext] = None,
                 top_k: Optional[int] = None, min_relevance: Optional[float] = None) -> RetrievalResult:
        k = top_k or self.settings.top_k
        floor = self.settings.min_relevance if min_relevance is None else min_relevance
        query = build_query(recommendation, patient)
        crit = critical_terms(recommendation)
        result = RetrievalResult(query=query, critical_terms=crit)

        try:
            if self.store.count() == 0:
                result.note = "The guideline index is empty. Run `python -m scripts.ingest_guidelines`."
                return result
            built_with = self.store.manifest.data.get("embedder")
            if built_with and built_with != self.embedder.name:
                raise IndexMismatchError(
                    f"index was built with '{built_with}' but the current embedder is '{self.embedder.name}'. "
                    "Re-run `python -m scripts.ingest_guidelines --rebuild`.")
            lex, chunks = self._lexicon()
            qvec = self.embedder.embed([query])[0]
            vec_hits = self.store.search(qvec, max(k * 4, 12))
        except IndexMismatchError as e:
            raise RetrievalError(str(e)) from e
        except (VectorStoreError, EmbeddingError) as e:
            raise RetrievalError(f"knowledge base unavailable: {e}") from e

        index_of = {c.chunk_id: i for i, c in enumerate(chunks)}
        qtokens = set(tokenize(query, expand=True))
        sem = getattr(self.embedder, "semantic", True)
        w_vec = VECTOR_WEIGHT_SEMANTIC if sem else VECTOR_WEIGHT_LEXICAL_EMBEDDER

        # Candidate pool = vector hits  UNION  best lexical matches (so exact clinical terms are not missed).
        vec_score = {c.chunk_id: s for c, s in vec_hits}
        lex_scores = sorted(((lex.coverage(qtokens, i), i) for i in range(len(chunks))), reverse=True)[: max(k * 4, 12)]
        pool: dict[str, Chunk] = {c.chunk_id: c for c, _ in vec_hits}
        for _, i in lex_scores:
            pool.setdefault(chunks[i].chunk_id, chunks[i])
        missing_vec = [cid for cid in pool if cid not in vec_score]
        if missing_vec:  # score lexical-only candidates against the query vector too
            cmat = self.embedder.embed([pool[c].text for c in missing_vec])
            for cid, v in zip(missing_vec, cmat):
                vec_score[cid] = float(np.dot(qvec, v))

        max_age = self.settings.max_source_age_years
        this_year = date.today().year
        scored: list[RetrievedPassage] = []
        for cid, ch in pool.items():
            cov = lex.coverage(qtokens, index_of[cid]) if cid in index_of else 0.0
            v = max(vec_score.get(cid, 0.0), 0.0)
            is_rec = is_recommendation(ch.text, ch.section)
            # small preference for actual recommendations over rationale text (never enough to pass the threshold alone)
            relevance = min(1.0, w_vec * v + (1 - w_vec) * cov + (RECOMMENDATION_BOOST if is_rec else 0.0))
            yr = _year(ch.publication_date)
            low = ch.text.lower()
            scored.append(RetrievedPassage(
                chunk=ch, vector_score=round(v, 4), keyword_coverage=round(cov, 4), relevance=round(relevance, 4),
                matched_critical_terms=[t for t in crit if term_in_text(t, low)], is_recommendation=is_rec,
                source_stale=(yr is None) or (this_year - yr > max_age)))

        # Highest relevance first; among near-ties prefer the more recent source.
        scored.sort(key=lambda p: (round(p.relevance, 2), _year(p.chunk.publication_date) or 0), reverse=True)

        candidates: list[RetrievedPassage] = []
        for p in scored:
            if p.relevance < floor:
                continue
            toks = tokenize(p.chunk.text)
            if any(jaccard(toks, tokenize(q.chunk.text)) >= DEDUP_JACCARD for q in candidates):
                continue  # near-duplicate passage (e.g. overlap or repeated table)
            candidates.append(p)

        # Reserve half the slots for actual recommendations: committee rationale is wordy and would
        # otherwise crowd out the one-line recommendation that decides the verdict.
        reserved = [p for p in candidates if p.is_recommendation][: max(1, (k + 1) // 2)]
        rest = [p for p in candidates if p not in reserved][: k - len(reserved)]
        kept = sorted(reserved + rest, key=lambda p: p.relevance, reverse=True)

        result.passages = kept
        result.no_evidence = not kept
        found = {t for p in kept for t in p.matched_critical_terms}
        result.missing_critical_terms = [t for t in crit if t not in found]
        # Long words the knowledge base has never seen (e.g. a drug it does not cover) cannot be verified.
        result.unseen_terms = sorted({w for w in re.findall(r"[a-z]{10,}", recommendation.lower())
                                      if stem(w) not in lex.idf and w not in lex.idf})
        if not kept:
            result.note = f"No indexed passage reached the relevance threshold ({floor})."
        return result
