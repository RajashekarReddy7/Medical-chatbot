"""Readable demo of the guideline verifier on the real index.

    python -m scripts.demo_rag                    # keyword/negation judge (no LLM needed)
    python -m scripts.demo_rag --judge ollama     # use your local Ollama model as the judge
"""
from __future__ import annotations

import argparse
import dataclasses
import textwrap

from rag.config import get_settings
from rag.judges import get_judge
from rag.models import PatientContext
from rag.verifier import GuidelineVerifier

ICON = {"supported": "OK  supported", "potential_conflict": "!!  potential_conflict",
        "insufficient_evidence": "??  insufficient_evidence", "escalate_for_review": "**  escalate_for_review"}

HEALTHY = dict(age=30, allergies=[], medications=[], medical_history=[])
DEMOS = [
    ("Advice that matches the guideline",
     PatientContext(symptoms=["cough", "runny nose"], **HEALTHY),
     "Do not offer an antibiotic to treat an acute cough associated with an upper respiratory tract infection in people who are not systemically very unwell.", None),
    ("Advice that contradicts the guideline",
     PatientContext(symptoms=["cough", "runny nose"], **HEALTHY),
     "Offer an antibiotic to an otherwise healthy adult with an acute cough from a cold.", None),
    ("Drug the guideline says not to offer",
     PatientContext(symptoms=["cough"], **HEALTHY),
     "Offer an oral bronchodilator such as salbutamol for an acute cough from a cold.", None),
    ("Topic the knowledge base does not cover (it abstains)",
     PatientContext(symptoms=["knee pain"], **HEALTHY),
     "Apply a warm compress to the knee.", None),
    ("A drug the knowledge base never mentions (cannot be 'supported')",
     PatientContext(symptoms=["cough", "fever"], **HEALTHY),
     "Prescribe oseltamivir for an acute cough with fever.", None),
    ("Medication advice but allergies / age unknown (needs a human)",
     PatientContext(symptoms=["dysuria"]),
     "Obtain a midstream urine sample from pregnant women before antibiotics are taken, and send for culture.", None),
    ("Possible emergency (rules decide, not the LLM)",
     PatientContext(age=55, symptoms=["chest pain", "shortness of breath"]),
     "Rest at home and drink plenty of fluids.", None),
]


def wrap(s: str, indent: str) -> str:
    return textwrap.fill(s, width=100, initial_indent=indent, subsequent_indent=indent)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--judge", choices=["heuristic", "ollama"], default="heuristic")
    args = ap.parse_args()
    settings = dataclasses.replace(get_settings(), judge=args.judge)
    verifier = GuidelineVerifier(settings=settings, judge=get_judge(settings))
    info = verifier.retriever.status()
    print(f"Index: {info.get('chunks')} passages from {len(info.get('documents', []))} documents, "
          f"embedder {info.get('embedder')}, judge: {verifier.judge.name}\n")

    for n, (title, patient, rec, triage) in enumerate(DEMOS, 1):
        v = verifier.verify(patient, [rec], triage)
        r = v.recommendations[0]
        print(f"{'=' * 100}\n{n}. {title}")
        print(f"   Patient : age {patient.age}, symptoms {patient.symptoms}")
        print(wrap(f"Advice  : {rec}", "   ").lstrip() if False else wrap(f"Advice  : {rec}", "   "))
        print(f"   RESULT  : {ICON[r.status]}{'   (EMERGENCY ESCALATION)' if v.urgent_escalation else ''}")
        print(wrap(f"Why     : {r.reason}", "   "))
        for e in r.evidence:
            print(f"   Source  : [{e.role}] {e.publisher.split('(')[0].strip()}, {e.document_title.split('(')[0].strip()}, page {e.page_number}")
            print(wrap(f"Quote   : \"{e.quoted_text}\"", "   "))
        if r.missing_information:
            print(f"   Missing : {', '.join(r.missing_information)}")
        for c in r.safety_concerns[:2]:
            print(wrap(f"Concern : {c}", "   "))
        print(f"   Clinician review needed: {r.requires_clinician_review}")
    print("=" * 100)


if __name__ == "__main__":
    main()
