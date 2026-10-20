"""The component that compares ONE recommendation with retrieved passages.

`OllamaJudge`    - local LLM (Ollama). Its JSON is validated; passage ids and quotes are checked later.
`HeuristicJudge` - deterministic keyword/negation baseline. Works without any LLM; low assurance, and it
                   is labelled as such in every result. Used for offline evaluation or when Ollama is down
                   only if VERIFIER_JUDGE=heuristic is chosen explicitly.

A judge only *chooses among* the retrieved passages (by id). It never supplies citations of its own.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional, Protocol

import requests
from pydantic import ValidationError

from .config import RagSettings, get_settings
from .models import LLMJudgement, PatientContext, RetrievedPassage
from .text_utils import critical_terms, has_negation, sentences, term_in_text, tokenize

log = logging.getLogger("carebot.rag.judge")
MAX_PASSAGE_CHARS = 1200


class JudgeError(RuntimeError):
    """The judge could not produce a usable verdict (timeout, connection, invalid output)."""


class Judge(Protocol):
    name: str

    def judge(self, recommendation: str, patient: PatientContext, passages: list[RetrievedPassage]) -> LLMJudgement: ...


# ------------------------------------------------------------------------------- LLM client
class OllamaClient:
    def __init__(self, settings: Optional[RagSettings] = None):
        self.s = settings or get_settings()

    def complete(self, prompt: str) -> str:
        try:
            r = requests.post(
                f"{self.s.ollama_base_url}/api/generate",
                json={"model": self.s.ollama_model, "prompt": prompt, "stream": False, "format": "json",
                      "options": {"temperature": 0, "num_predict": 700}},
                timeout=self.s.llm_timeout_s)
            r.raise_for_status()
            return r.json().get("response", "")
        except requests.Timeout as e:
            raise JudgeError(f"Ollama timed out after {self.s.llm_timeout_s:.0f}s") from e
        except requests.ConnectionError as e:
            raise JudgeError("Ollama is not reachable (is `ollama serve` running?)") from e
        except (requests.RequestException, ValueError) as e:
            raise JudgeError(f"Ollama request failed: {e}") from e


# ------------------------------------------------------------------------------- prompt + parsing
def patient_summary(p: PatientContext) -> str:
    bits = []
    if p.age is not None:
        bits.append(f"age {p.age:g}")
    if p.sex:
        bits.append(f"sex {p.sex}")
    if p.pregnant is not None:
        bits.append("pregnant" if p.pregnant else "not pregnant")
    if p.symptoms:
        bits.append("symptoms: " + ", ".join(p.symptoms))
    if p.duration:
        bits.append(f"duration: {p.duration}")
    if p.medical_history:
        bits.append("history: " + ", ".join(p.medical_history))
    bits.append("allergies: " + ("unknown" if p.allergies is None else (", ".join(p.allergies) or "none reported")))
    bits.append("medications: " + ("unknown" if p.medications is None else (", ".join(p.medications) or "none reported")))
    if p.vitals:
        bits.append("vitals: " + ", ".join(f"{k} {v}" for k, v in p.vitals.items()))
    return "; ".join(bits)


def build_prompt(recommendation: str, patient: PatientContext, passages: list[RetrievedPassage]) -> str:
    blocks = []
    for i, p in enumerate(passages, start=1):
        c = p.chunk
        kind = "RECOMMENDATION TEXT" if p.is_recommendation else "SUPPORTING DISCUSSION (rationale/evidence, not itself a recommendation)"
        blocks.append(f"[E{i}] {c.document_title} ({c.publisher}), page {c.page_number}, section \"{c.section}\" - {kind}\n{c.text[:MAX_PASSAGE_CHARS]}")
    return f"""You are a careful clinical-guideline checker for an educational prototype. You do NOT diagnose or treat.
Decide whether the PROPOSED RECOMMENDATION is supported or contradicted by the GUIDELINE PASSAGES below.

Rules:
- Use ONLY the passages below. Never use outside knowledge, never invent passages, page numbers, thresholds or quotes.
- "supported": a passage directly states or clearly implies the recommendation for this kind of patient.
- "potential_conflict": a passage advises something inconsistent with the recommendation (e.g. says not to offer it, or gives an exception/contraindication that applies to this patient).
- "insufficient_evidence": the passages do not address the recommendation, or only partly, or the patient does not match the passage population. Absence of evidence is NOT a conflict.
- Base "supported" / "potential_conflict" on RECOMMENDATION TEXT where available; SUPPORTING DISCUSSION explains reasoning but is not the advice.
- Pay attention to negations ("do not offer"), drug names, doses, durations, and the population each passage covers.
- A list item (bullet) inherits the instruction of the sentence that introduces the list (e.g. "Do not offer the following: ...").
- Cite passages by their id only (E1, E2, ...). If you add a quote it must be copied word for word from that passage.
- If two passages disagree, set "conflicting_sources" to true.
- List patient information that is missing and needed to judge safely.

PATIENT: {patient_summary(patient)}
PROPOSED RECOMMENDATION: {recommendation}

GUIDELINE PASSAGES:
{chr(10).join(blocks)}

Reply with ONLY this JSON object:
{{"status": "supported" | "potential_conflict" | "insufficient_evidence",
  "reason": "one or two sentences",
  "supporting": ["E1"], "contradicting": [],
  "quotes": {{"E1": "exact words copied from the passage"}},
  "missing_information": [], "safety_concerns": [], "conflicting_sources": false}}"""


def parse_judgement(raw: str) -> LLMJudgement:
    """Validate the LLM's JSON. Raises JudgeError on anything malformed."""
    text = (raw or "").strip()
    if not text:
        raise JudgeError("empty LLM response")
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, flags=re.S)  # tolerate prose around the object
        if not m:
            raise JudgeError("LLM response is not JSON") from None
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError as e:
            raise JudgeError(f"LLM response is not valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise JudgeError("LLM JSON is not an object")
    # models often return a bare string/None where we expect a list
    for key in ("supporting", "contradicting", "missing_information", "safety_concerns"):
        v = data.get(key)
        if v is None:
            data[key] = []
        elif isinstance(v, str):
            data[key] = [v] if v else []
    if not isinstance(data.get("quotes", {}), dict):
        data["quotes"] = {}
    try:
        return LLMJudgement(**data)
    except ValidationError as e:
        raise JudgeError(f"LLM JSON failed validation: {e.errors()[0]['msg']} ({e.errors()[0]['loc']})") from e


class OllamaJudge:
    name = "ollama"

    def __init__(self, llm=None, settings: Optional[RagSettings] = None):
        self.llm = llm or OllamaClient(settings)

    def judge(self, recommendation, patient, passages):
        prompt = build_prompt(recommendation, patient, passages)
        last: Optional[JudgeError] = None
        for attempt in range(2):                       # one retry for malformed output, not for outages
            raw = self.llm.complete(prompt if attempt == 0 else prompt + "\n\nYour previous answer was invalid. Return ONLY the JSON object.")
            try:
                return parse_judgement(raw)
            except JudgeError as e:
                last = e
                log.warning("invalid LLM judgement (attempt %d): %s", attempt + 1, e)
        raise last or JudgeError("invalid LLM output")


# ------------------------------------------------------------------------------- heuristic baseline
def best_sentence(text: str, query_tokens: set[str]) -> tuple[str, float]:
    """Sentence of `text` that shares the most query terms (used for quotes and the heuristic judge)."""
    best, score = "", 0.0
    for s in sentences(text):
        toks = set(tokenize(s))
        if not toks or not query_tokens:
            continue
        sc = len(toks & query_tokens) / len(query_tokens)
        if sc > score:
            best, score = s, sc
    return best, score


_BULLET = re.compile(r"^\s*(?:[•\-–▪●○■]|\([a-z0-9]{1,3}\))\s+")


def candidate_sentences(text: str) -> list[tuple[str, bool]]:
    """(sentence, negated) pairs. A bullet inherits negation from the line that introduces its list."""
    out: list[tuple[str, bool]] = []
    intro_neg = False
    for line in text.split("\n"):
        if not line.strip():
            continue
        if _BULLET.match(line):
            neg_ctx = intro_neg
        else:
            intro_neg = has_negation(line)
            neg_ctx = False
        for s in sentences(line):
            out.append((s, neg_ctx or has_negation(s)))
    return out


class HeuristicJudge:
    """Keyword + negation rules. Cannot read nuance; it abstains whenever it is unsure.

    Only numbered recommendation passages are judged (committee rationale is ignored), and a sentence must
    contain the recommendation's drug names and overlap strongly with its wording to count as support or conflict.
    """
    name = "heuristic"

    def judge(self, recommendation, patient, passages):
        rec_tokens = set(tokenize(recommendation))
        rec_neg = has_negation(recommendation)
        crit = [t for t in critical_terms(recommendation) if not re.search(r"\d", t)]
        support, contra = [], []
        for i, p in enumerate(passages, start=1):
            if not p.is_recommendation:
                continue
            for sent, neg in candidate_sentences(p.chunk.text):
                toks = set(tokenize(sent))
                overlap = len(toks & rec_tokens) / len(rec_tokens) if rec_tokens else 0.0
                has_crit = (not crit) or any(term_in_text(t, sent.lower()) for t in crit)
                # A drug/treatment name shared with the sentence is a strong anchor, so a lower word-overlap suffices.
                if not has_crit or overlap < (0.35 if crit else 0.5):
                    continue
                (contra if neg != rec_neg else support).append((overlap, f"E{i}", sent))
        support.sort(reverse=True)
        contra.sort(reverse=True)
        if contra and (not support or contra[0][0] >= support[0][0]):
            ids = [c[1] for c in contra[:2]]
            return LLMJudgement(status="potential_conflict", reason="A retrieved guideline sentence about the same subject has the opposite polarity (e.g. 'do not offer').",
                                contradicting=ids, quotes={c[1]: c[2] for c in contra[:2]}, conflicting_sources=bool(support))
        if support:
            ids = [c[1] for c in support[:2]]
            return LLMJudgement(status="supported", reason="A retrieved guideline sentence covers the same subject with the same polarity (keyword match; low-assurance judge).",
                                supporting=ids, quotes={c[1]: c[2] for c in support[:2]})
        return LLMJudgement(status="insufficient_evidence", reason="No retrieved sentence clearly addresses this recommendation.")


def get_judge(settings: Optional[RagSettings] = None, llm=None) -> Judge:
    s = settings or get_settings()
    return HeuristicJudge() if s.judge == "heuristic" else OllamaJudge(llm=llm, settings=s)
