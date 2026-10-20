# Guideline verification (RAG) for CareBot

> **Educational prototype. Not a medical device and not clinically validated.**
> A "supported" result means *retrieved guideline text appears consistent with a recommendation*. It does not mean the advice is correct or safe for a real patient. A qualified clinician must review all medical advice.

## What it does

The doctor agent proposes advice. Before that advice is shown as "checked", this module looks it up in trusted guideline PDFs and reports, **per recommendation**:

| status | meaning |
|---|---|
| `supported` | Retrieved guidance appears to support it for this patient. |
| `potential_conflict` | Retrieved guidance appears to say something different (e.g. "do not offer"). |
| `insufficient_evidence` | The indexed documents don't clearly address it (or the check could not run). **Not** the same as "wrong". |
| `escalate_for_review` | Possible emergency, or information needed to apply the advice safely is missing. A human must look. |

The original recommendation text is returned unchanged. Nothing is rewritten or auto-approved.

```
patient input -> symptom extractor -> triage engine -> doctor agent (proposed advice)
                                                              |
        explicit safety rules  <---------- (decided first, never needs the LLM or the index)
                                                              |
        retriever (hybrid: vectors + keyword coverage) -> judge (Ollama LLM) -> guards -> structured result
```

Key safety behaviour (all covered by tests):

* **Emergencies are decided by explicit rules first** (the existing `triage_engine.py` red flags and vital-sign thresholds, plus a few extra phrases in `rag/safety.py`). They don't depend on retrieval or the LLM, and an upstream *Emergency* triage can never be lowered.
* **Citations are real.** The LLM only *picks passage ids* (E1, E2…). Page, section, URL and quote come from the retrieved chunk. An unknown id, or a quote that isn't verbatim in the passage, is rejected and listed in `citation_issues`.
* **`supported` and `potential_conflict` both need a valid citation**, otherwise the result falls back to `insufficient_evidence`.
* **Drug names and doses must literally appear in the cited text** to count as supported, and so must any long word the knowledge base has never seen (e.g. a drug it doesn't cover).
* **Failures never default to "supported"**: invalid LLM JSON (one retry), Ollama down/timeout, ChromaDB/embedding failure → `insufficient_evidence` with `degraded: true`.
* **Wrong population**: a guideline whose age range doesn't include the patient is not applied.
* **Missing patient information** (age, allergies, current medicines, pregnancy status) for medication advice → `escalate_for_review`.
* **Old or undated sources** are flagged (`source_stale`) and force `requires_clinician_review`.
* **Absence of evidence is never treated as a conflict.**

## Files

```
rag/pdf_loader.py     PyMuPDF text extraction, headings, page numbers, scanned/empty/duplicate detection
rag/chunker.py        heading/paragraph-aware chunks; numbered recommendations stay with their exceptions
rag/embeddings.py     sentence-transformers | chroma-onnx | ollama | hashing (offline fallback)
rag/vector_store.py   ChromaDB store + dependency-light local NumPy store, shared manifest
rag/ingest.py         add / update / remove documents so the index matches the PDF folder
rag/retriever.py      hybrid retrieval, top-k, relevance threshold, dedupe, "no evidence" result
rag/judges.py         Ollama judge (validated JSON) + deterministic heuristic judge
rag/safety.py         emergency escalation and per-recommendation checks
rag/verifier.py       the engine that ties it together; returns VerificationResult
rag/models.py         Pydantic models (request, response, LLM output)
rag/config.py         every setting, from environment variables (.env.example)
scripts/              download_guidelines, ingest_guidelines, evaluate_rag
medical_guidelines/   sources.json (provenance) and pdfs/ (downloaded, not in git)
tests/                66 tests with synthetic data
```

## Setup

### 1. Python version (important)

ChromaDB and PyTorch/sentence-transformers do not support very new Python versions. **Use Python 3.10–3.12.** The project's current `venv/` (Python 3.15) cannot install them. Create a new environment:

```powershell
py -3.12 -m venv venv312
.\venv312\Scripts\activate
pip install -r requirements.txt
```

If you cannot install ChromaDB or sentence-transformers, the module still runs: the vector store falls back to a local NumPy store (`VECTOR_BACKEND=local`) and embeddings fall back to lexical hashing (`EMBEDDING_BACKEND=hashing`, **not semantic**, quality is lower).

### 2. Ollama

```bash
ollama serve
ollama pull mistral        # or whatever MODEL_NAME / OLLAMA_MODEL you already use
```

### 3. Configuration

Copy `.env.example` to `.env` and adjust. Defaults work for a local setup. The Ollama URL/model fall back to your existing `OLLAMA_URL` / `MODEL_NAME`.

### 4. Get the guideline PDFs

The PDFs are **not stored in git** (publisher copyright). Download them from the official sources listed in `medical_guidelines/sources.json`:

```bash
python -m scripts.download_guidelines
```

This also records the access date in `sources.json`. If a download fails it prints the official page to download from manually; save the file into `medical_guidelines/pdfs/` using the name in `sources.json`.

Included by default (NICE, UK): NG120 acute cough, NG84 sore throat, NG109 lower urinary tract infection (antimicrobial prescribing). A 2004 WHO IMAI document is listed but **excluded** (`"index": false`) because it is old, interim guidance.

> **Scope warning:** these three documents cover antibiotic prescribing for cough, sore throat and cystitis only. Most things your chatbot discusses are *not* covered, and those recommendations will correctly come back `insufficient_evidence`. Add more documents for broader coverage.

### 5. Build the index (offline step, not part of a patient request)

```bash
python -m scripts.ingest_guidelines             # add/update/remove what changed
python -m scripts.ingest_guidelines --rebuild   # wipe and rebuild from scratch
```

It prints a report (indexed / unchanged / skipped duplicate / excluded / failed, pages without text, chunk counts) and exits with code 1 if a document failed.

### 6. Run the API

```bash
uvicorn main:app --reload --port 8000
```

New endpoints (both need a login token like your other `/api` endpoints):

* `POST /api/verify-guideline` (alias `POST /verify-guideline`)
* `GET /api/guidelines/status` (which documents are indexed)
* `POST /api/chat` accepts `"verify_guidelines": true` and then also returns a `verification` object (slower: one LLM call per advice sentence). Default is off.

## Example

```bash
curl -X POST http://localhost:8000/api/verify-guideline \
  -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
  -d '{"patient_context": {"age": 30, "symptoms": ["cough", "runny nose"], "duration": "3 days",
                           "allergies": [], "medications": [], "medical_history": []},
       "recommendations": ["Offer an antibiotic to an otherwise healthy adult with an acute cough from a cold."]}'
```

Actual response (heuristic judge, real NICE NG120 index; shortened):

```json
{
  "verification_status": "potential_conflict",
  "recommendations": [{
    "recommendation": "Offer an antibiotic to an otherwise healthy adult with an acute cough from a cold.",
    "status": "potential_conflict",
    "reason": "A retrieved guideline sentence about the same subject has the opposite polarity (e.g. 'do not offer').",
    "evidence": [{
      "document_title": "Cough (acute): antimicrobial prescribing (NICE guideline NG120)",
      "publisher": "National Institute for Health and Care Excellence (NICE), UK",
      "page_number": 6,
      "section": "Acute cough associated with an upper respiratory tract infection",
      "source_url": "https://www.nice.org.uk/guidance/ng120/resources/cough-acute-antimicrobial-prescribing-pdf-66141652166341",
      "quoted_text": "1.1.8 Do not offer an antibiotic to treat an acute cough associated with an upper respiratory tract infection in people who are not systemically very unwell or at higher risk of complications …",
      "role": "contradicts"
    }],
    "missing_information": [], "safety_concerns": [], "requires_clinician_review": true
  }],
  "overall_safety_notes": [], "urgent_escalation": false, "degraded": false, "judge": "heuristic",
  "limitations": ["Verification is limited to the indexed guideline documents and does not cover all conditions.", "..."]
}
```

With Ollama stopped and the default judge, the same request returns `insufficient_evidence`, `degraded: true`, and `"judge failed: Ollama is not reachable (is `ollama serve` running?)"`. It does **not** return `supported`.

## Adding or updating guidelines

1. Put the PDF in `medical_guidelines/pdfs/`.
2. Add an entry to `medical_guidelines/sources.json` (title, publisher, official URL, **publication date copied from the document**, and the age range it covers). Without an entry the file is indexed but flagged "UNKNOWN provenance".
3. `python -m scripts.ingest_guidelines`. Replaced files (new content) and deleted files are handled automatically; identical copies are skipped.
4. Check currency yourself: confirm on the publisher's page that the document hasn't been replaced or withdrawn. Use `"index": false` to keep a file on disk without indexing it.

## Tests and evaluation

```bash
python -m pytest                                  # 66 tests, synthetic PDFs, no network/Ollama needed
python -m scripts.evaluate_rag                    # synthetic KB, heuristic judge
python -m scripts.evaluate_rag --kb real          # your real index (run ingest first)
python -m scripts.evaluate_rag --kb real --judge ollama
```

The tests cover supported / conflicting / no-evidence / missing-patient-info / exceptions kept with rules / conflicting sources / stale or unknown source / unparseable PDF / empty retrieval / invalid LLM JSON / Ollama down or timing out / ChromaDB unavailable / duplicate ingestion / emergency escalation / fabricated citations / out-of-scope population, plus API validation and privacy.

**How to read the numbers.** Results from the last run (heuristic judge, 12 hand-written cases on the real NICE index, embeddings `chroma-onnx:all-MiniLM-L6-v2`): status accuracy 11/12, retrieval recall 7/7, citation validity 7/7, conflict detection 3/3, abstention 3/3, escalation preserved 2/2. The one miss (`nitrofurantoin` advice) is a limit of the keyword judge: the supporting text is in a table whose row doesn't repeat the question's wording, so it abstained (the safe direction). Be careful with these figures: the cases were written by the same person who wrote the code, a threshold was tuned after the first run exposed misses, and there is no held-out set. They show the *software* behaves as designed. They say **nothing** about clinical safety. The Ollama (LLM) judge is tested only with mocked responses; it has not been run against a live model in this repository's test environment.

## Troubleshooting

| symptom | fix |
|---|---|
| `pip install chromadb` / `torch` fails | Wrong Python. Use 3.10–3.12 (`py -3.12 -m venv venv312`). |
| `The guideline index is empty` | Run `python -m scripts.download_guidelines` then `python -m scripts.ingest_guidelines`. |
| `index was built with 'X' but the current embedder is 'Y'` | Embedding backend changed. Re-run ingest with `--rebuild`. |
| Embedding model can't download, `CERTIFICATE_VERIFY_FAILED` | Corporate TLS proxy. `pip install truststore`, set `RAG_USE_SYSTEM_CERTS=true`. |
| `huggingface.co` blocked (403) | Use `EMBEDDING_BACKEND=chroma-onnx` (same MiniLM model, downloaded from Chroma's storage) or `ollama pull nomic-embed-text` with `EMBEDDING_BACKEND=ollama`. |
| Startup is slow with `EMBEDDING_BACKEND=auto` and no internet | `auto` tries Hugging Face first and retries; set the backend explicitly. |
| `Ollama is not reachable` / timed out | `ollama serve`; raise `RAG_LLM_TIMEOUT`; check `OLLAMA_BASE_URL` and the model name. |
| Document marked `failed` | Read the printed reason: password-protected, corrupt, or no text (scanned). For scans set `RAG_OCR_ENABLED=true` and install Tesseract (OCR path is untested here). |
| `ChromaDB unavailable` in logs | `VECTOR_BACKEND=auto` fell back to the local store. Install chromadb on a supported Python, or ignore. |
| Results look empty for a recommendation | Normal if the topic isn't covered. Lower `RAG_MIN_RELEVANCE` only after checking `/api/guidelines/status`. |

## Privacy and operations

* Everything runs locally: PDFs, embeddings, vector store and LLM. No patient data leaves the machine.
* Logs contain counts, timings and error types only. No symptoms or recommendation text is logged.
* The index lives in `CHROMA_PERSIST_DIR` (default `chroma_db/`, git-ignored). It contains only guideline text, no patient data. Back it up by copying the folder; delete it (or `--rebuild`) to remove it.
* The embedding model and index are loaded once per process and reused; the local store is guarded by a lock. Ingestion runs offline, not inside requests.

## Known limitations

* Only three narrow guideline documents are indexed by default (see scope warning).
* The heuristic judge cannot read nuance (tables, long qualifications); the LLM judge can, but a 7B local model can still misjudge. Both are guarded, neither is clinically validated.
* The safety phrase list is a small, illustrative, conservative set. **A clinician must review and extend it before any real use.** The code errs towards escalation; it will sometimes escalate unnecessarily.
* Population filtering uses the document-level age range in `sources.json`; age limits inside individual recommendations are only seen by the judge, not enforced.
* Staleness is based on the publication date you record (default limit 10 years). It does not know whether a newer version exists; check the publisher.
* In `/api/chat` the patient's age, allergies and medicines are unknown, so medication advice there will usually come back `escalate_for_review` (missing information). That is intended.
* No PDF report generation exists in this repository, so there is nothing to integrate with; the structured result can be added to one later.

## Ideas for later

Clinician-reviewed safety rules; more documents (e.g. headache, chest pain, fever, local national guidelines); a held-out evaluation set written by clinicians; table-aware extraction; a reranker model; running the LLM judge in the evaluation and comparing it with the heuristic.
