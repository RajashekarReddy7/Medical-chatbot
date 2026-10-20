"""Build or refresh the guideline index.

    python -m scripts.ingest_guidelines             # add / update / remove changed documents
    python -m scripts.ingest_guidelines --rebuild   # wipe the index and rebuild from the PDFs
    python -m scripts.ingest_guidelines --embedding hashing --vector local   # force backends (offline mode)

Exit code is 1 if any document failed (so CI / scripts notice), 0 otherwise.
"""
from __future__ import annotations

import argparse
import dataclasses
import logging
import sys

from rag.config import get_settings
from rag.embeddings import EmbeddingError, get_embedder
from rag.ingest import ingest
from rag.vector_store import VectorStoreError, open_store


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rebuild", action="store_true", help="delete the existing index first")
    ap.add_argument("--embedding", help="override EMBEDDING_BACKEND (auto|sentence-transformers|ollama|hashing)")
    ap.add_argument("--vector", help="override VECTOR_BACKEND (auto|chroma|local)")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    settings = get_settings()
    overrides = {}
    if args.embedding:
        overrides["embedding_backend"] = args.embedding
    if args.vector:
        overrides["vector_backend"] = args.vector
    if overrides:
        settings = dataclasses.replace(settings, **overrides)

    print(f"PDF folder : {settings.guideline_pdf_dir}")
    print(f"Index dir  : {settings.persist_dir}")
    try:
        report = ingest(settings, rebuild=args.rebuild, embedder=get_embedder(settings), store=open_store(settings))
    except (EmbeddingError, VectorStoreError) as e:
        print(f"\nIngestion failed: {e}", file=sys.stderr)
        return 1

    print()
    print("\n".join(report.summary_lines()))
    failed = [d for d in report.documents if d.status == "failed"]
    if report.total_chunks == 0:
        print("\nThe index is empty. Download PDFs first: python -m scripts.download_guidelines", file=sys.stderr)
        return 1
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
