"""Central configuration for the guideline-verification RAG system.

Every value can be overridden with an environment variable (see `.env.example`).
Existing project settings are reused where they exist: `OLLAMA_URL` / `MODEL_NAME`
from `utils.py` are accepted as fallbacks for `OLLAMA_BASE_URL` / `OLLAMA_MODEL`.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _env(*names: str, default: str = "") -> str:
    for n in names:
        v = os.getenv(n)
        if v not in (None, ""):
            return v
    return default


def _path(value: str) -> Path:
    p = Path(value)
    return p if p.is_absolute() else PROJECT_ROOT / p


@dataclass(frozen=True)
class RagSettings:
    # --- Ollama (local LLM + optional local embeddings) ---
    ollama_base_url: str = field(default_factory=lambda: _env("OLLAMA_BASE_URL", "OLLAMA_URL", default="http://localhost:11434").rstrip("/"))
    ollama_model: str = field(default_factory=lambda: _env("OLLAMA_MODEL", "MODEL_NAME", default="mistral:latest"))
    ollama_embed_model: str = field(default_factory=lambda: _env("OLLAMA_EMBED_MODEL", default="nomic-embed-text"))
    llm_timeout_s: float = field(default_factory=lambda: float(_env("RAG_LLM_TIMEOUT", default="90")))

    # --- Embeddings: auto | sentence-transformers | ollama | hashing ---
    embedding_backend: str = field(default_factory=lambda: _env("EMBEDDING_BACKEND", default="auto").lower())
    embedding_model: str = field(default_factory=lambda: _env("EMBEDDING_MODEL", default="sentence-transformers/all-MiniLM-L6-v2"))

    use_system_certs: bool = field(default_factory=lambda: _env("RAG_USE_SYSTEM_CERTS", default="false").lower() in ("1", "true", "yes"))

    # --- Knowledge base ---
    guideline_pdf_dir: Path = field(default_factory=lambda: _path(_env("GUIDELINE_PDF_DIR", default="medical_guidelines/pdfs")))
    guideline_sources_file: Path = field(default_factory=lambda: _path(_env("GUIDELINE_SOURCES_FILE", default="medical_guidelines/sources.json")))

    # --- Vector store: auto | chroma | local ---
    vector_backend: str = field(default_factory=lambda: _env("VECTOR_BACKEND", default="auto").lower())
    persist_dir: Path = field(default_factory=lambda: _path(_env("CHROMA_PERSIST_DIR", default="chroma_db")))

    # --- Chunking ---
    chunk_size: int = field(default_factory=lambda: int(_env("RAG_CHUNK_SIZE", default="1000")))
    chunk_overlap: int = field(default_factory=lambda: int(_env("RAG_CHUNK_OVERLAP", default="150")))

    # --- Retrieval ---
    top_k: int = field(default_factory=lambda: int(_env("RAG_TOP_K", default="5")))
    min_relevance: float = field(default_factory=lambda: float(_env("RAG_MIN_RELEVANCE", default="0.30")))

    # --- Verification ---
    judge: str = field(default_factory=lambda: _env("VERIFIER_JUDGE", default="ollama").lower())  # ollama | heuristic
    max_source_age_years: int = field(default_factory=lambda: int(_env("RAG_MAX_SOURCE_AGE_YEARS", default="10")))

    # --- PDF extraction ---
    ocr_enabled: bool = field(default_factory=lambda: _env("RAG_OCR_ENABLED", default="false").lower() in ("1", "true", "yes"))


def get_settings() -> RagSettings:
    """Build settings from the current environment (cheap; call as needed)."""
    return RagSettings()
