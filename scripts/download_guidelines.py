"""Download the guideline PDFs listed in medical_guidelines/sources.json from their official URLs.

    python -m scripts.download_guidelines           # download missing files
    python -m scripts.download_guidelines --force   # re-download everything

The PDFs are NOT stored in git (publisher copyright; see medical_guidelines/README.md): each person
downloads them from the publisher. After a successful download `accessed_date` is written back to
sources.json so the provenance record is complete.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date

import requests

from rag.config import get_settings

UA = "Mozilla/5.0 (CareBot educational prototype; guideline download)"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)

    s = get_settings()
    raw = json.loads(s.guideline_sources_file.read_text(encoding="utf-8"))
    s.guideline_pdf_dir.mkdir(parents=True, exist_ok=True)
    failures = 0

    for doc in raw["documents"]:
        target = s.guideline_pdf_dir / doc["file"]
        if target.exists() and not args.force:
            print(f"[have   ] {doc['file']}")
            continue
        try:
            r = requests.get(doc["source_url"], headers={"User-Agent": UA}, timeout=90, allow_redirects=True)
            r.raise_for_status()
            if not r.content.startswith(b"%PDF"):
                raise ValueError(f"not a PDF (content-type {r.headers.get('content-type')})")
            target.write_bytes(r.content)
            doc["accessed_date"] = date.today().isoformat()
            print(f"[ok     ] {doc['file']}  ({len(r.content) // 1024} KB)  {doc['source_url']}")
        except (requests.RequestException, ValueError) as e:
            failures += 1
            print(f"[FAILED ] {doc['file']}: {e}\n          Download it manually from {doc.get('landing_page') or doc['source_url']} "
                  f"and save it as {target}", file=sys.stderr)

    s.guideline_sources_file.write_text(json.dumps(raw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
