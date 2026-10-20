# Medical guideline sources

`pdfs/` holds the guideline documents used by the RAG verifier. **The PDFs are not committed to git**: they are copyrighted by their publishers. Each developer downloads them from the official source:

```bash
python -m scripts.download_guidelines
python -m scripts.ingest_guidelines
```

`sources.json` records, for each document: official title, publisher, the exact download URL, the publisher's landing page, the publication date **as printed on the document's cover**, the age range it covers, and (after download) the access date.

| file | publisher | published | notes |
|---|---|---|---|
| `nice_ng120_acute_cough.pdf` | NICE (UK) | 7 Feb 2019 | Acute cough: antimicrobial prescribing. https://www.nice.org.uk/guidance/ng120 |
| `nice_ng84_sore_throat.pdf` | NICE (UK) | 26 Jan 2018 | Acute sore throat: antimicrobial prescribing. https://www.nice.org.uk/guidance/ng84 |
| `nice_ng109_uti_lower.pdf` | NICE (UK) | 31 Oct 2018 | Lower UTI: antimicrobial prescribing. https://www.nice.org.uk/guidance/ng109 |
| `who_imai_acute_care.pdf` | WHO | Jan 2004 | **Not indexed** (`"index": false`): 2004 interim guidance, very likely superseded in parts. |

The PDF footers show the NICE documents were regenerated in 2025/2026, but the publication dates above are the original ones. **Before relying on any document, check the publisher's page that it is still the current version.** NICE guidance is UK guidance and may not match the practice or antibiotic resistance patterns where the chatbot is used.

Respect each publisher's terms of use (NICE: https://www.nice.org.uk/terms-and-conditions).

See `rag/README.md` for how to add documents.
