"""Software evaluation of the guideline-verification pipeline on a set of synthetic cases.

    python -m scripts.evaluate_rag                       # synthetic KB, heuristic judge (offline, deterministic)
    python -m scripts.evaluate_rag --kb real             # your real index (run ingest first)
    python -m scripts.evaluate_rag --kb real --judge ollama --cases tests/data/eval_cases_real.json

This measures whether the SOFTWARE behaves as designed (retrieves the right source, cites real text,
abstains when evidence is missing, never loses an escalation). It is NOT clinical validation: passing
here says nothing about whether advice is medically safe.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import re
import sys
import tempfile
import time
from pathlib import Path

from rag.config import get_settings
from rag.judges import get_judge
from rag.models import PatientContext
from rag.retriever import Retriever
from rag.verifier import GuidelineVerifier

ROOT = Path(__file__).resolve().parent.parent


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower()).strip()


def build_synthetic():
    sys.path.insert(0, str(ROOT))
    from tests.helpers import build_kb, build_retriever
    tmp = Path(tempfile.mkdtemp(prefix="carebot_eval_"))
    settings = build_kb(tmp)
    return settings, build_retriever(settings)


def run(cases: list[dict], verifier: GuidelineVerifier) -> tuple[list[dict], dict]:
    chunks = {c.chunk_id: c for c in verifier.retriever.store.all_chunks()}
    rows = []
    for case in cases:
        patient = PatientContext(**case["patient_context"])
        t0 = time.time()
        err = None
        try:
            retrieval = verifier.retriever.retrieve(case["recommendation"], patient)
            result = verifier.verify(patient, [case["recommendation"]], case.get("triage"))
        except Exception as e:  # report, do not crash the whole run
            err, retrieval, result = f"{type(e).__name__}: {e}", None, None
        dt = time.time() - t0
        row = {"id": case["id"], "expected": case["expected_status"], "actual": None, "seconds": round(dt, 3), "error": err,
               "retrieved_docs": [], "citation_valid": None, "relevant_retrieved": None, "escalation_preserved": None}
        if result:
            rec = result.recommendations[0]
            row["actual"] = rec.status
            row["retrieved_docs"] = sorted({p.chunk.document_title for p in retrieval.passages})
            exp_src = case.get("expected_source")
            if exp_src:
                row["relevant_retrieved"] = any(exp_src.lower() in p.chunk.document_title.lower() or exp_src.lower() in p.chunk.text.lower()
                                                for p in retrieval.passages)
            if rec.evidence:
                ok = True
                for e in rec.evidence:
                    ch = chunks.get(e.chunk_id)
                    ok &= bool(ch) and _norm(e.quoted_text) in _norm(ch.text) and ch.page_number == e.page_number
                row["citation_valid"] = ok
            if case.get("triage", {}).get("level") == "Emergency" or case.get("expect_escalation"):
                row["escalation_preserved"] = result.urgent_escalation and rec.status == "escalate_for_review"
        rows.append(row)

    def ratio(pred, rows_):
        sel = [r for r in rows_ if pred(r)]
        return None if not sel else (sum(1 for r in sel if r["_ok"]) / len(sel), len(sel))

    for r in rows:
        r["_ok"] = r["actual"] == r["expected"]
    metrics = {
        "cases": len(rows),
        "errors": sum(1 for r in rows if r["error"]),
        "status_accuracy": ratio(lambda r: True, rows),
        "retrieval_recall": _rate([r["relevant_retrieved"] for r in rows if r["relevant_retrieved"] is not None]),
        "citation_validity": _rate([r["citation_valid"] for r in rows if r["citation_valid"] is not None]),
        "conflict_detection_recall": ratio(lambda r: r["expected"] == "potential_conflict", rows),
        "abstention_accuracy": ratio(lambda r: r["expected"] == "insufficient_evidence", rows),
        "escalation_preserved": _rate([r["escalation_preserved"] for r in rows if r["escalation_preserved"] is not None]),
        "mean_seconds": round(sum(r["seconds"] for r in rows) / max(len(rows), 1), 3),
    }
    for r in rows:
        r.pop("_ok")
    return rows, metrics


def _rate(vals):
    return None if not vals else (sum(1 for v in vals if v) / len(vals), len(vals))


def fmt(m):
    return "n/a (no cases)" if m is None else f"{m[0]:.0%} ({round(m[0] * m[1])}/{m[1]})"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--kb", choices=["synthetic", "real"], default="synthetic")
    ap.add_argument("--judge", choices=["heuristic", "ollama"], default="heuristic")
    ap.add_argument("--cases", help="path to a cases JSON file")
    ap.add_argument("--out", default="rag_eval_report.json")
    args = ap.parse_args(argv)

    if args.kb == "synthetic":
        settings, retriever = build_synthetic()
        cases_path = Path(args.cases or ROOT / "tests" / "data" / "eval_cases_synthetic.json")
    else:
        settings = get_settings()
        retriever = Retriever(settings=settings)
        cases_path = Path(args.cases or ROOT / "tests" / "data" / "eval_cases_real.json")
    settings = dataclasses.replace(settings, judge=args.judge)
    verifier = GuidelineVerifier(retriever=retriever, judge=get_judge(settings), settings=settings)
    cases = json.loads(cases_path.read_text(encoding="utf-8"))

    rows, metrics = run(cases, verifier)
    print(f"\nKnowledge base: {args.kb}   judge: {verifier.judge.name}   cases: {len(cases)}\n")
    for r in rows:
        mark = "ok  " if r["actual"] == r["expected"] else "DIFF"
        print(f"[{mark}] {r['id']:<34} expected={r['expected']:<22} actual={str(r['actual']):<22} {r['seconds']}s {r['error'] or ''}")
    print("\nMetrics (software behaviour only, NOT clinical validation):")
    for k, v in metrics.items():
        print(f"  {k:<28} {fmt(v) if isinstance(v, tuple) or v is None else v}")
    Path(args.out).write_text(json.dumps({"kb": args.kb, "judge": verifier.judge.name, "metrics": metrics, "cases": rows}, indent=2, default=list), encoding="utf-8")
    print(f"\nFull report written to {args.out}")
    return 0 if not metrics["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
