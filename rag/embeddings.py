"""Local embedding backends. Nothing here ever calls an external cloud service.

Backends (select with EMBEDDING_BACKEND):
  sentence-transformers  preferred; needs `pip install sentence-transformers` (Python 3.9-3.12)
  chroma-onnx            same MiniLM model via ONNX Runtime, bundled with chromadb (no PyTorch, no Hugging Face)
  ollama                uses a local Ollama embedding model (e.g. `ollama pull nomic-embed-text`)
  hashing                dependency-free lexical fallback, deterministic. NOT semantic: it only
                         captures shared words/character n-grams. Used for tests and offline mode.
  auto                   sentence-transformers -> chroma-onnx -> ollama -> hashing (first one that works)

The embedder's `name` is stored with the index; querying with a different embedder than the one
used to build the index raises `IndexMismatchError` instead of returning meaningless scores.
"""
from __future__ import annotations

import hashlib
import logging
import re
import threading
from typing import Optional, Protocol

import numpy as np
import requests

from .config import RagSettings, get_settings

log = logging.getLogger("carebot.rag.embed")


class EmbeddingError(RuntimeError):
    pass


class IndexMismatchError(RuntimeError):
    pass


class Embedder(Protocol):
    name: str
    semantic: bool

    def embed(self, texts: list[str]) -> np.ndarray: ...


def _normalize(m: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (m / norms).astype(np.float32)


class SentenceTransformerEmbedder:
    semantic = True

    def __init__(self, model_name: str):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise EmbeddingError("sentence-transformers is not installed") from e
        try:
            self._model = SentenceTransformer(model_name)
        except Exception as e:  # download failure, bad name, offline
            raise EmbeddingError(f"cannot load embedding model '{model_name}': {e}") from e
        self.name = f"sentence-transformers:{model_name}"

    def embed(self, texts: list[str]) -> np.ndarray:
        vecs = self._model.encode(texts, batch_size=32, show_progress_bar=False, normalize_embeddings=True)
        return np.asarray(vecs, dtype=np.float32)


class ChromaOnnxEmbedder:
    """all-MiniLM-L6-v2 through ONNX Runtime (ships with chromadb; no PyTorch needed).

    The ~80 MB model is downloaded once from Chroma's own storage (not Hugging Face) into ~/.cache/chroma,
    which makes this the easiest semantic option on networks that block huggingface.co.
    """
    semantic = True

    def __init__(self):
        try:
            from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2
            self._ef = ONNXMiniLM_L6_V2()
            self._ef(["warm-up"])  # triggers the download / load now, so failures surface at start-up
        except ImportError as e:
            raise EmbeddingError("chromadb is not installed") from e
        except Exception as e:
            raise EmbeddingError(f"cannot load the ONNX MiniLM model: {e}") from e
        self.name = "chroma-onnx:all-MiniLM-L6-v2"

    def embed(self, texts: list[str]) -> np.ndarray:
        return _normalize(np.asarray(self._ef(texts), dtype=np.float32))


class OllamaEmbedder:
    semantic = True

    def __init__(self, base_url: str, model: str, timeout: float = 60.0):
        self.base_url, self.model, self.timeout = base_url, model, timeout
        self.name = f"ollama:{model}"
        # fail fast so `auto` can fall through
        self.embed(["connection test"])

    def embed(self, texts: list[str]) -> np.ndarray:
        try:
            r = requests.post(f"{self.base_url}/api/embed", json={"model": self.model, "input": texts}, timeout=self.timeout)
            if r.status_code == 404:  # older Ollama: single-prompt endpoint
                vecs = []
                for t in texts:
                    rr = requests.post(f"{self.base_url}/api/embeddings", json={"model": self.model, "prompt": t}, timeout=self.timeout)
                    rr.raise_for_status()
                    vecs.append(rr.json()["embedding"])
                return _normalize(np.asarray(vecs, dtype=np.float32))
            r.raise_for_status()
            return _normalize(np.asarray(r.json()["embeddings"], dtype=np.float32))
        except (requests.RequestException, KeyError, ValueError) as e:
            raise EmbeddingError(f"Ollama embedding failed ({self.model}): {e}") from e


class HashingEmbedder:
    """Signed feature hashing over word unigrams/bigrams and character 4-grams."""
    semantic = False

    def __init__(self, dim: int = 1024):
        self.dim = dim
        self.name = f"hashing:{dim}"

    @staticmethod
    def _features(text: str):
        words = re.findall(r"[a-z0-9]+", text.lower())
        for w in words:
            yield w
        for a, b in zip(words, words[1:]):
            yield f"{a}_{b}"
        joined = " ".join(words)
        for i in range(len(joined) - 3):
            yield "c:" + joined[i:i + 4]

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            for f in self._features(text):
                h = int(hashlib.md5(f.encode("utf-8")).hexdigest(), 16)
                out[row, h % self.dim] += 1.0 if (h >> 64) & 1 else -1.0
        return _normalize(out)


# ----------------------------------------------------------------------------- factory
_lock = threading.Lock()
_cached: dict[tuple, Embedder] = {}


def get_embedder(settings: Optional[RagSettings] = None, backend: Optional[str] = None) -> Embedder:
    """Return a process-wide shared embedder (models are loaded once, not per request)."""
    s = settings or get_settings()
    choice = (backend or s.embedding_backend).lower()
    key = (choice, s.embedding_model, s.ollama_embed_model, s.ollama_base_url)
    with _lock:
        if key in _cached:
            return _cached[key]
        emb = _build(choice, s)
        _cached[key] = emb
        return emb


def _build(choice: str, s: RagSettings) -> Embedder:
    if s.use_system_certs:
        _use_system_certs()
    if choice == "hashing":
        return HashingEmbedder()
    if choice == "sentence-transformers":
        return SentenceTransformerEmbedder(s.embedding_model)
    if choice == "chroma-onnx":
        return ChromaOnnxEmbedder()
    if choice == "ollama":
        return OllamaEmbedder(s.ollama_base_url, s.ollama_embed_model, s.llm_timeout_s)
    if choice != "auto":
        raise EmbeddingError(f"unknown EMBEDDING_BACKEND '{choice}'")
    errors = []
    for build in (lambda: SentenceTransformerEmbedder(s.embedding_model),
                  lambda: ChromaOnnxEmbedder(),
                  lambda: OllamaEmbedder(s.ollama_base_url, s.ollama_embed_model, s.llm_timeout_s)):
        try:
            return build()
        except EmbeddingError as e:
            errors.append(str(e))
    log.warning("No semantic embedder available (%s). Falling back to lexical hashing embeddings.", "; ".join(errors))
    return HashingEmbedder()


def _use_system_certs() -> None:
    """Trust the operating system's certificate store (needed behind some corporate TLS proxies)."""
    try:
        import truststore
        truststore.inject_into_ssl()
    except ImportError:
        log.warning("RAG_USE_SYSTEM_CERTS is set but `truststore` is not installed (pip install truststore)")


def reset_embedder_cache() -> None:
    with _lock:
        _cached.clear()
