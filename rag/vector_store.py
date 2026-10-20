"""Persistent vector stores behind one small interface.

* `ChromaStore` - ChromaDB (preferred; `pip install chromadb`, Python 3.9-3.12).
* `LocalStore`  - NumPy + JSON files. Dependency-light fallback that works on any Python.

Both keep a `manifest.json` in the persist directory recording which embedder built the index and
which documents (by content hash) are in it. That is what makes ingestion idempotent and lets the
retriever refuse an index built with a different embedder.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np

from .config import RagSettings, get_settings
from .models import Chunk

log = logging.getLogger("carebot.rag.store")


class VectorStoreError(RuntimeError):
    pass


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Manifest:
    """Small JSON file describing what the index contains."""

    def __init__(self, directory: Path):
        self.path = directory / "manifest.json"
        self.data: dict = {"embedder": None, "dim": None, "documents": {}, "updated": None}
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                raise VectorStoreError(f"corrupt manifest {self.path}: {e}") from e

    def save(self) -> None:
        self.data["updated"] = _utcnow()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)  # atomic: readers never see a half-written file


class VectorStore(ABC):
    kind: str

    def __init__(self, directory: Path):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        self.manifest = Manifest(directory)

    # --- abstract storage primitives
    @abstractmethod
    def add(self, chunks: list[Chunk], embeddings: np.ndarray) -> None: ...
    @abstractmethod
    def delete_document(self, document_id: str) -> None: ...
    @abstractmethod
    def search(self, embedding: np.ndarray, k: int) -> list[tuple[Chunk, float]]: ...
    @abstractmethod
    def all_chunks(self) -> list[Chunk]: ...
    @abstractmethod
    def count(self) -> int: ...
    @abstractmethod
    def reset(self) -> None: ...

    # --- shared helpers
    def documents(self) -> dict:
        return self.manifest.data["documents"]

    def version_token(self) -> str:
        """Changes whenever the index changes; lets the retriever refresh its keyword index."""
        return str(self.manifest.data.get("updated"))

    def reload_manifest(self) -> None:
        self.manifest = Manifest(self.directory)


class LocalStore(VectorStore):
    kind = "local"

    def __init__(self, directory: Path):
        super().__init__(directory)
        self._lock = threading.RLock()
        self._vec_path = directory / "vectors.npy"
        self._chunk_path = directory / "chunks.jsonl"
        self._chunks: list[Chunk] = []
        self._vectors: np.ndarray = np.zeros((0, 1), dtype=np.float32)
        self._load()

    def _load(self) -> None:
        with self._lock:
            self._chunks, self._vectors = [], np.zeros((0, 1), dtype=np.float32)
            if self._chunk_path.exists() and self._vec_path.exists():
                try:
                    self._chunks = [Chunk(**json.loads(line)) for line in self._chunk_path.read_text(encoding="utf-8").splitlines() if line.strip()]
                    self._vectors = np.load(self._vec_path)
                except Exception as e:
                    raise VectorStoreError(f"corrupt local index in {self.directory}: {e}") from e
                if len(self._chunks) != len(self._vectors):
                    raise VectorStoreError("local index is inconsistent (chunks/vectors length differ); rebuild it")

    def _persist(self) -> None:
        with self._lock:
            tmp_c, tmp_v = self._chunk_path.with_suffix(".tmp"), self._vec_path.with_suffix(".tmp.npy")
            tmp_c.write_text("\n".join(c.model_dump_json() for c in self._chunks), encoding="utf-8")
            np.save(tmp_v, self._vectors)
            os.replace(tmp_c, self._chunk_path)
            os.replace(tmp_v, self._vec_path)

    def add(self, chunks, embeddings):
        with self._lock:
            ids = {c.chunk_id for c in chunks}
            keep = [i for i, c in enumerate(self._chunks) if c.chunk_id not in ids]
            old_v = self._vectors[keep] if keep and self._vectors.shape[1] == embeddings.shape[1] else np.zeros((0, embeddings.shape[1]), np.float32)
            self._chunks = [self._chunks[i] for i in keep] + list(chunks)
            self._vectors = np.vstack([old_v, embeddings.astype(np.float32)])
            self._persist()

    def delete_document(self, document_id):
        with self._lock:
            keep = [i for i, c in enumerate(self._chunks) if c.document_id != document_id]
            self._chunks = [self._chunks[i] for i in keep]
            self._vectors = self._vectors[keep] if keep else np.zeros((0, max(self._vectors.shape[1], 1)), np.float32)
            self._persist()

    def search(self, embedding, k):
        with self._lock:
            if not self._chunks:
                return []
            scores = self._vectors @ embedding.astype(np.float32)   # unit vectors => cosine similarity
            top = np.argsort(-scores)[:k]
            return [(self._chunks[i], float(scores[i])) for i in top]

    def all_chunks(self):
        with self._lock:
            return list(self._chunks)

    def count(self):
        with self._lock:
            return len(self._chunks)

    def reset(self):
        with self._lock:
            self._chunks, self._vectors = [], np.zeros((0, 1), dtype=np.float32)
            for p in (self._chunk_path, self._vec_path):
                p.unlink(missing_ok=True)
            self.manifest.data = {"embedder": None, "dim": None, "documents": {}, "updated": None}
            self.manifest.save()


class ChromaStore(VectorStore):
    kind = "chroma"
    COLLECTION = "guidelines"

    def __init__(self, directory: Path):
        super().__init__(directory)
        try:
            import chromadb
        except ImportError as e:
            raise VectorStoreError("chromadb is not installed (pip install chromadb; needs Python 3.9-3.12)") from e
        try:
            self._client = chromadb.PersistentClient(path=str(directory / "chroma"))
            self._col = self._client.get_or_create_collection(self.COLLECTION, metadata={"hnsw:space": "cosine"})
        except Exception as e:
            raise VectorStoreError(f"cannot open ChromaDB at {directory}: {e}") from e

    @staticmethod
    def _meta(c: Chunk) -> dict:
        # Chroma metadata must be flat scalars; drop None values and keep the full chunk as JSON.
        return {"document_id": c.document_id, "page_number": c.page_number, "chunk_json": c.model_dump_json()}

    def add(self, chunks, embeddings):
        try:
            self._col.upsert(ids=[c.chunk_id for c in chunks], embeddings=embeddings.tolist(),
                             documents=[c.text for c in chunks], metadatas=[self._meta(c) for c in chunks])
        except Exception as e:
            raise VectorStoreError(f"ChromaDB write failed: {e}") from e

    def delete_document(self, document_id):
        try:
            self._col.delete(where={"document_id": document_id})
        except Exception as e:
            raise VectorStoreError(f"ChromaDB delete failed: {e}") from e

    def search(self, embedding, k):
        try:
            n = self._col.count()
            if n == 0:
                return []
            res = self._col.query(query_embeddings=[embedding.tolist()], n_results=min(k, n), include=["metadatas", "distances"])
        except Exception as e:
            raise VectorStoreError(f"ChromaDB query failed: {e}") from e
        out = []
        for meta, dist in zip(res["metadatas"][0], res["distances"][0]):
            out.append((Chunk(**json.loads(meta["chunk_json"])), 1.0 - float(dist)))   # cosine distance -> similarity
        return out

    def all_chunks(self):
        try:
            res = self._col.get(include=["metadatas"])
        except Exception as e:
            raise VectorStoreError(f"ChromaDB read failed: {e}") from e
        return [Chunk(**json.loads(m["chunk_json"])) for m in res["metadatas"]]

    def count(self):
        try:
            return self._col.count()
        except Exception as e:
            raise VectorStoreError(f"ChromaDB count failed: {e}") from e

    def reset(self):
        try:
            self._client.delete_collection(self.COLLECTION)
            self._col = self._client.get_or_create_collection(self.COLLECTION, metadata={"hnsw:space": "cosine"})
        except Exception as e:
            raise VectorStoreError(f"ChromaDB reset failed: {e}") from e
        self.manifest.data = {"embedder": None, "dim": None, "documents": {}, "updated": None}
        self.manifest.save()


_stores: dict[tuple, VectorStore] = {}
_stores_lock = threading.Lock()


def open_store(settings: Optional[RagSettings] = None, backend: Optional[str] = None, directory: Optional[Path] = None) -> VectorStore:
    """Open (and cache) the vector store. `auto` prefers Chroma and falls back to the local store."""
    s = settings or get_settings()
    choice = (backend or s.vector_backend).lower()
    d = directory or s.persist_dir
    key = (choice, str(d))
    with _stores_lock:
        if key in _stores:
            return _stores[key]
        if choice == "chroma":
            store: VectorStore = ChromaStore(d)
        elif choice == "local":
            store = LocalStore(d)
        elif choice == "auto":
            try:
                store = ChromaStore(d)
            except VectorStoreError as e:
                log.warning("ChromaDB unavailable (%s); using the local NumPy store.", e)
                store = LocalStore(d)
        else:
            raise VectorStoreError(f"unknown VECTOR_BACKEND '{choice}'")
        _stores[key] = store
        return store


def reset_store_cache() -> None:
    with _stores_lock:
        _stores.clear()
