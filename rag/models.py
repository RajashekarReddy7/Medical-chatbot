"""Pydantic models shared by the RAG pipeline and the FastAPI layer."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

VerificationStatus = Literal["supported", "potential_conflict", "insufficient_evidence", "escalate_for_review"]

# Worst-first ordering, used to roll per-recommendation results up into one overall status.
STATUS_PRIORITY: dict[str, int] = {
    "escalate_for_review": 4,
    "potential_conflict": 3,
    "insufficient_evidence": 2,
    "supported": 1,
}


# ---------------------------------------------------------------- knowledge base
class PopulationScope(BaseModel):
    """Who a guideline applies to. `None` means no bound."""
    min_age_years: Optional[float] = None
    max_age_years: Optional[float] = None
    description: str = ""


class SourceInfo(BaseModel):
    """Provenance of one guideline PDF (one entry of medical_guidelines/sources.json)."""
    file: str
    title: str
    publisher: str
    source_url: str
    publication_date: Optional[str] = None  # ISO date or year, only if known
    version: Optional[str] = None
    accessed_date: Optional[str] = None
    landing_page: Optional[str] = None
    index: bool = True                      # False => kept on disk but never indexed or cited
    index_note: str = ""
    population: PopulationScope = Field(default_factory=PopulationScope)
    topics: list[str] = Field(default_factory=list)


class Chunk(BaseModel):
    """One retrievable passage with full provenance."""
    chunk_id: str
    document_id: str
    document_title: str
    publisher: str
    source_url: str
    publication_date: Optional[str] = None
    version: Optional[str] = None
    page_number: int
    page_end: int
    section: str = ""
    text: str
    population_min_age: Optional[float] = None
    population_max_age: Optional[float] = None
    population_description: str = ""


class RetrievedPassage(BaseModel):
    """A chunk returned by the retriever, plus how it was scored."""
    chunk: Chunk
    vector_score: Optional[float] = None   # cosine similarity, None in lexical-only mode
    keyword_coverage: float = 0.0          # IDF-weighted share of query terms found in the passage
    relevance: float = 0.0                 # combined score used for thresholding (NOT a correctness measure)
    matched_critical_terms: list[str] = Field(default_factory=list)
    is_recommendation: bool = False        # contains numbered recommendations (vs committee rationale/evidence)
    source_stale: bool = False             # older than RAG_MAX_SOURCE_AGE_YEARS or undated


class RetrievalResult(BaseModel):
    query: str
    passages: list[RetrievedPassage] = Field(default_factory=list)
    critical_terms: list[str] = Field(default_factory=list)
    missing_critical_terms: list[str] = Field(default_factory=list)
    unseen_terms: list[str] = Field(default_factory=list)   # long words that occur nowhere in the indexed documents
    no_evidence: bool = True
    note: str = ""


# ---------------------------------------------------------------- API / verification
class PatientContext(BaseModel):
    model_config = ConfigDict(extra="ignore")

    age: Optional[float] = Field(default=None, ge=0, le=130, description="Age in years (use fractions for infants)")
    sex: Optional[str] = None
    pregnant: Optional[bool] = None
    symptoms: list[str] = Field(default_factory=list)
    duration: Optional[str] = None
    medical_history: list[str] = Field(default_factory=list)
    allergies: Optional[list[str]] = None   # None = unknown, [] = none reported
    medications: Optional[list[str]] = None
    vitals: dict[str, str] = Field(default_factory=dict)
    assessment: Optional[str] = None        # the doctor agent's proposed assessment


class VerifyRequest(BaseModel):
    patient_context: PatientContext
    recommendations: list[str] = Field(min_length=1, max_length=20)
    triage: Optional[dict] = None           # existing triage result, e.g. {"level": "Urgent", "reason": "..."}


class Evidence(BaseModel):
    chunk_id: str
    document_title: str
    publisher: str
    page_number: int
    section: str = ""
    source_url: str
    publication_date: Optional[str] = None
    quoted_text: str
    role: Literal["supports", "contradicts", "context"] = "context"
    source_stale: bool = False


class RecommendationResult(BaseModel):
    recommendation: str
    status: VerificationStatus
    reason: str
    evidence: list[Evidence] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    safety_concerns: list[str] = Field(default_factory=list)
    conflicting_sources: bool = False
    requires_clinician_review: bool = True
    citation_issues: list[str] = Field(default_factory=list)  # fabricated/invalid citations that were rejected


class VerificationResult(BaseModel):
    verification_status: VerificationStatus
    recommendations: list[RecommendationResult]
    overall_safety_notes: list[str] = Field(default_factory=list)
    urgent_escalation: bool = False
    degraded: bool = False                  # True when retrieval/LLM failed and results are incomplete
    errors: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    judge: str = "ollama"


# ---------------------------------------------------------------- LLM output validation
class LLMJudgement(BaseModel):
    """What we accept back from the LLM for one recommendation. Anything else is rejected."""
    model_config = ConfigDict(extra="ignore")

    status: Literal["supported", "potential_conflict", "insufficient_evidence"]
    reason: str = ""
    supporting: list[str] = Field(default_factory=list)      # passage ids like "E1"
    contradicting: list[str] = Field(default_factory=list)
    quotes: dict[str, str] = Field(default_factory=dict)     # optional {"E1": "exact text"}; verified against the passage
    missing_information: list[str] = Field(default_factory=list)
    safety_concerns: list[str] = Field(default_factory=list)
    conflicting_sources: bool = False
