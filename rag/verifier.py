"""Guideline verification engine: retrieval + judge + deterministic guards + safety rules.

Design rules (see rag/README.md):
* Emergency escalation comes from explicit rules and is decided BEFORE retrieval or the LLM run.
* A citation is only ever a real retrieved passage. Judge output that names a passage we did not
  retrieve, or quotes text that is not in the passage, is rejected and recorded as a citation issue.
* "supported" and "potential_conflict" both need at least one valid citation; otherwise the result
  falls back to "insufficient_evidence". Failures never default to "supported".
* The original recommendation text is returned untouched. We never rewrite medical advice.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from typing import Optional

from .config import RagSettings, get_settings
from .judges import Judge, JudgeError, best_sentence, get_judge
from .models import (STATUS_PRIORITY, Evidence, LLMJudgement, PatientContext, RecommendationResult,
                     RetrievalResult, RetrievedPassage, VerificationResult)
from .retriever import Retriever, RetrievalError
from .safety import SafetyAssessment, assess_safety, recommendation_checks
from .text_utils import term_in_text, tokenize

log = logging.getLogger("carebot.rag.verify")

BASE_LIMITATIONS = [
    "Verification is limited to the indexed guideline documents and does not cover all conditions.",
    "A 'supported' result means retrieved guidance appears consistent with the recommendation; it is not a guarantee of clinical correctness.",
    "This is an educational prototype, not a clinically validated decision-support system. A qualified clinician must review medical advice.",
]
MAX_QUOTE_CHARS = 400


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower()).strip()


def applicable(passage: RetrievedPassage, age: Optional[float]) -> bool:
    """False when the patient's age is outside the population the source document covers."""
    if age is None:
        return True
    c = passage.chunk
    if c.population_min_age is not None and age < c.population_min_age:
        return False
    if c.population_max_age is not None and age > c.population_max_age:
        return False
    return True


def _evidence(passage: RetrievedPassage, role: str, quote: str) -> Evidence:
    c = passage.chunk
    return Evidence(chunk_id=c.chunk_id, document_title=c.document_title, publisher=c.publisher,
                    page_number=c.page_number, section=c.section, source_url=c.source_url,
                    publication_date=c.publication_date, quoted_text=quote[:MAX_QUOTE_CHARS], role=role,
                    source_stale=passage.source_stale)


class GuidelineVerifier:
    def __init__(self, retriever: Optional[Retriever] = None, judge: Optional[Judge] = None,
                 settings: Optional[RagSettings] = None):
        self.settings = settings or get_settings()
        self.retriever = retriever or Retriever(settings=self.settings)
        self.judge = judge or get_judge(self.settings)

    # ------------------------------------------------------------------ public API
    def verify(self, patient: PatientContext, recommendations: list[str], triage: Optional[dict] = None) -> VerificationResult:
        t0 = time.time()
        safety = assess_safety(patient, recommendations, triage)
        results: list[RecommendationResult] = []
        errors: list[str] = []
        for rec in recommendations:
            try:
                results.append(self._verify_one(rec, patient, safety, errors))
            except Exception as e:  # last-resort guard: one bad recommendation must not sink the response
                log.exception("unexpected verification failure")
                errors.append(f"unexpected error: {type(e).__name__}")
                results.append(RecommendationResult(
                    recommendation=rec, status="escalate_for_review" if safety.urgent_escalation else "insufficient_evidence",
                    reason="Verification failed unexpectedly; this recommendation was NOT verified.", requires_clinician_review=True))

        overall = max((r.status for r in results), key=lambda s: STATUS_PRIORITY[s])
        notes = list(safety.notes)
        if safety.urgent_escalation:
            notes = safety.emergency_reasons + notes
        limitations = list(BASE_LIMITATIONS)
        if self.judge.name == "heuristic":
            limitations.append("Judged by a keyword/negation heuristic (no LLM): low assurance, may miss nuance.")
        if any(e.source_stale for r in results for e in r.evidence):
            limitations.append("Some cited sources are older than the configured age limit or undated; check for newer guidance.")
        log.info("verified %d recommendation(s) in %.2fs overall=%s escalation=%s errors=%d",
                 len(recommendations), time.time() - t0, overall, safety.urgent_escalation, len(errors))
        return VerificationResult(
            verification_status=overall, recommendations=results, overall_safety_notes=notes,
            urgent_escalation=safety.urgent_escalation, degraded=bool(errors), errors=sorted(set(errors)),
            limitations=limitations, judge=self.judge.name)

    # ------------------------------------------------------------------ one recommendation
    def _verify_one(self, rec: str, patient: PatientContext, safety: SafetyAssessment, errors: list[str]) -> RecommendationResult:
        missing, concerns = recommendation_checks(rec, patient, safety)
        out = RecommendationResult(recommendation=rec, status="insufficient_evidence", reason="",
                                   missing_information=missing, safety_concerns=concerns)

        # 1) retrieval (best effort). Emergencies do not wait on it.
        retrieval: Optional[RetrievalResult] = None
        try:
            retrieval = self.retriever.retrieve(rec, patient)
        except RetrievalError as e:
            errors.append(f"retrieval failed: {e}")
            log.warning("retrieval failed: %s", e)

        passages = retrieval.passages if retrieval else []
        usable = [p for p in passages if applicable(p, patient.age)]
        out_of_scope = [p for p in passages if not applicable(p, patient.age)]

        # 2) emergency: explicit rules win; evidence is attached only as context
        if safety.urgent_escalation:
            out.status = "escalate_for_review"
            out.reason = ("Possible emergency identified by explicit safety rules: " + "; ".join(safety.emergency_reasons)
                          + ". Seek urgent medical assessment; guideline evidence below is context only.")
            qtok = set(tokenize(rec))
            out.evidence = [_evidence(p, "context", best_sentence(p.chunk.text, qtok)[0] or p.chunk.text) for p in usable[:2]]
            out.safety_concerns.insert(0, "Possible emergency: do not rely on this recommendation without urgent clinical assessment.")
            out.requires_clinician_review = True
            return out

        # 3) knowledge-base problems / no usable evidence
        if retrieval is None:
            out.reason = "The guideline knowledge base could not be queried, so this recommendation was NOT verified."
            return out
        if not usable:
            if out_of_scope:
                out.reason = "Retrieved guidance is for a different patient population (age range) than this patient, so it cannot be applied."
                out.safety_concerns.append("Retrieved guideline population does not match the patient's age.")
            else:
                out.reason = retrieval.note or "No relevant guideline passage was found in the indexed documents."
            return out

        # 4) judge
        try:
            judgement = self.judge.judge(rec, patient, usable)
        except JudgeError as e:
            errors.append(f"judge failed: {e}")
            out.reason = f"The comparison step failed ({e}); this recommendation was NOT verified."
            out.evidence = [_evidence(p, "context", best_sentence(p.chunk.text, set(tokenize(rec)))[0] or p.chunk.text) for p in usable[:2]]
            return out

        self._apply_judgement(out, judgement, usable, rec, retrieval)
        self._finalise(out, patient)
        return out

    # ------------------------------------------------------------------ guards
    def _apply_judgement(self, out: RecommendationResult, j: LLMJudgement, usable: list[RetrievedPassage],
                         rec: str, retrieval: RetrievalResult) -> None:
        by_id = {f"E{i}": p for i, p in enumerate(usable, start=1)}
        qtok = set(tokenize(rec))

        def collect(ids: list[str], role: str) -> list[tuple[str, RetrievedPassage, Evidence]]:
            found = []
            for pid in dict.fromkeys(ids):
                p = by_id.get(pid)
                if p is None:
                    out.citation_issues.append(f"Judge cited '{pid}', which is not a retrieved passage; citation rejected.")
                    continue
                quote = j.quotes.get(pid, "")
                if quote and _norm(quote) in _norm(p.chunk.text):
                    text = quote.strip()
                else:
                    if quote:
                        out.citation_issues.append(f"Quote for {pid} was not found verbatim in the passage; replaced with the closest retrieved sentence.")
                    text = best_sentence(p.chunk.text, qtok)[0] or p.chunk.text
                found.append((pid, p, _evidence(p, role, text)))
            return found

        supports = collect(j.supporting, "supports")
        contras = collect(j.contradicting, "contradicts")
        out.missing_information = list(dict.fromkeys(out.missing_information + j.missing_information))
        out.safety_concerns = list(dict.fromkeys(out.safety_concerns + j.safety_concerns))
        out.conflicting_sources = j.conflicting_sources
        out.reason = j.reason.strip()
        status = j.status

        if status == "supported":
            if not supports:
                status, out.reason = "insufficient_evidence", "The comparison claimed support but cited no valid retrieved passage."
            else:
                # safety-critical terms (drug names, doses) must literally appear in the cited text
                cited_text = " ".join(p.chunk.text.lower() for _, p, _ in supports)
                absent = [t for t in retrieval.critical_terms if not term_in_text(t, cited_text)]
                absent += [t for t in retrieval.unseen_terms if t not in absent]   # never mentioned anywhere in the KB
                if absent:
                    status = "insufficient_evidence"
                    out.reason = ("The cited guideline text does not mention: " + ", ".join(absent)
                                  + ". Drug names and doses must appear in the evidence before a recommendation can count as supported.")
                    supports = []
        elif status == "potential_conflict":
            if not contras:
                status, out.reason = "insufficient_evidence", "The comparison suggested a conflict but cited no valid retrieved passage."

        if out.conflicting_sources and supports and contras:
            status = "potential_conflict"
            out.safety_concerns.append("Retrieved sources disagree with each other; clinician review needed.")

        out.status = status
        unique: dict[tuple, Evidence] = {}   # overlapping chunks can cite the same sentence twice
        for e in [e for _, _, e in supports] + [e for _, _, e in contras]:
            unique.setdefault((e.document_title, e.page_number, e.role, _norm(e.quoted_text)), e)
        out.evidence = list(unique.values())
        if status == "supported" and any(e.source_stale for e in out.evidence):
            out.safety_concerns.append("Supporting source is older than the configured age limit or undated; check for newer guidance.")

    def _finalise(self, out: RecommendationResult, patient: PatientContext) -> None:
        # Missing patient information blocks an unqualified 'supported' for medication advice.
        if out.status == "supported" and out.missing_information:
            out.status = "escalate_for_review"
            out.reason = ("Guidance appears to support this, but information needed to apply it safely is missing: "
                          + ", ".join(out.missing_information) + ". " + out.reason).strip()
        if not out.reason:
            out.reason = {"supported": "Retrieved guidance supports this recommendation.",
                          "potential_conflict": "Retrieved guidance appears inconsistent with this recommendation.",
                          "insufficient_evidence": "The indexed guidance does not clearly address this recommendation.",
                          "escalate_for_review": "Needs clinician review."}[out.status]
        out.requires_clinician_review = (out.status != "supported" or bool(out.safety_concerns)
                                         or bool(out.missing_information) or bool(out.citation_issues))


# ------------------------------------------------------------------ shared instance for the API
_instance: Optional[GuidelineVerifier] = None
_instance_lock = threading.Lock()


def get_verifier() -> GuidelineVerifier:
    """One verifier per process, so models and the index are loaded once."""
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = GuidelineVerifier()
        return _instance


def reset_verifier() -> None:
    global _instance
    with _instance_lock:
        _instance = None
