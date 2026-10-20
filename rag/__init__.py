"""RAG-based medical guideline verification for CareBot.

Pipeline: PDFs -> pdf_loader -> chunker -> embeddings -> vector_store   (offline, scripts/ingest_guidelines.py)
          recommendation -> retriever -> judges -> verifier (+ safety)   (online, FastAPI)

See rag/README.md. Import the heavy pieces lazily: `from rag.verifier import get_verifier`.
"""
