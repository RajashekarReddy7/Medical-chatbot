"""Explicit, rule-based safety checks. They never depend on the LLM or on retrieval succeeding.

The rules are deliberately simple and conservative (they err towards escalation). They are a starting
set for a student prototype; any real deployment needs them reviewed and extended by clinicians.

Reused, not re-invented: the red-flag keywords and vital-sign thresholds live in `triage_engine.py`
and are called from here. The RAG verifier can only keep or raise urgency; it can never lower it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from triage_engine import RED_FLAG_KEYWORDS, evaluate_triage

from .models import PatientContext
from .text_utils import critical_terms

# Additional emergency phrases beyond the triage engine's list (illustrative; clinician review required).
EXTRA_EMERGENCY_PHRASES = (
    "coughing up blood", "coughing blood", "haemoptysis", "hemoptysis", "blue lips", "cyanosis",
    "severe breathlessness", "can't breathe", "cannot breathe", "struggling to breathe", "unresponsive",
    "suicidal", "wants to die", "want to die", "anaphylaxis", "swelling of the face", "swelling of the throat",
    "face drooping", "worst headache", "sudden severe headache", "non-blanching rash", "stiff neck",
    "crushing chest", "vomiting blood", "black stools", "confusion", "fitting",
)
FALSE_REASSURANCE_PHRASES = (
    "nothing to worry", "no need to see", "no need for a doctor", "no need to seek", "will go away on its own",
    "completely harmless", "no cause for concern", "ignore", "don't need medical",
)
_NUM = re.compile(r"-?\d+(?:\.\d+)?")


@dataclass
class SafetyAssessment:
    urgent_escalation: bool = False
    emergency_reasons: list[str] = field(default_factory=list)
    prompt_assessment_indicated: bool = False       # triage level Urgent
    notes: list[str] = field(default_factory=list)


def _num(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    m = _NUM.search(str(value))
    return m.group(0) if m else None


def _triage_struct(p: PatientContext) -> dict:
    """Shape a PatientContext like the structured dict that triage_engine.evaluate_triage expects."""
    v = {k.lower(): val for k, val in p.vitals.items()}
    vitals = {
        "hr": _num(v.get("hr") or v.get("heart_rate") or v.get("pulse")),
        "sbp": _num(v.get("sbp") or v.get("systolic")),
        "temp": _num(v.get("temp") or v.get("temperature")),
    }
    bp = v.get("bp") or v.get("blood_pressure")
    if bp and not vitals["sbp"]:
        vitals["sbp"] = _num(bp.split("/")[0])
    return {
        "chief_complaint": " ".join(p.symptoms),
        "associated_symptoms": list(p.symptoms),
        "severity": "severe" if any("severe" in s.lower() for s in p.symptoms) else "",
        "vitals": {k: x for k, x in vitals.items() if x},
    }


def assess_safety(patient: PatientContext, recommendations: list[str], triage: Optional[dict] = None) -> SafetyAssessment:
    """Decide whether this case must be escalated, independent of any guideline evidence."""
    out = SafetyAssessment()

    # 1) existing triage engine rules (red flags + vitals) re-run on the patient's own data
    own = evaluate_triage(_triage_struct(patient))
    if own["level"] == "Emergency":
        out.urgent_escalation = True
        out.emergency_reasons.append(own["reason"].replace("⚠️", "").strip())
    elif own["level"] == "Urgent":
        out.prompt_assessment_indicated = True

    # 2) an emergency triage already decided upstream can never be downgraded here
    level = str((triage or {}).get("level", "")).lower()
    if level == "emergency":
        out.urgent_escalation = True
        out.emergency_reasons.append("Upstream triage classified this case as Emergency.")
    elif level == "urgent":
        out.prompt_assessment_indicated = True

    # 3) phrase scan over everything the patient/agent said
    blob = " ".join(patient.symptoms + patient.medical_history + [patient.assessment or ""] + recommendations).lower()
    phrases = [ph for ph in (*RED_FLAG_KEYWORDS, *EXTRA_EMERGENCY_PHRASES) if ph in blob]
    # a red-flag phrase inside a recommendation that merely tells the patient what to watch for is
    # still escalated: this errs on the side of caution on purpose.
    if phrases:
        out.urgent_escalation = True
        out.emergency_reasons.append("Possible emergency indicator(s): " + ", ".join(sorted(set(phrases))))

    if out.prompt_assessment_indicated and not out.urgent_escalation:
        out.notes.append("Triage indicates Urgent: prompt professional assessment is advised.")
    if out.urgent_escalation:
        out.notes.append("Possible emergency: seek urgent medical assessment now. Guideline verification does not change this.")
    return out


def recommendation_checks(rec: str, patient: PatientContext, safety: SafetyAssessment) -> tuple[list[str], list[str]]:
    """Return (missing_patient_information, safety_concerns) for one recommendation."""
    missing: list[str] = []
    concerns: list[str] = []
    drugs = [t for t in critical_terms(rec) if not re.search(r"\d", t)]
    dosing = [t for t in critical_terms(rec) if re.search(r"\d", t)]

    if drugs or dosing:
        if patient.age is None:
            missing.append("patient age")
        if patient.allergies is None:
            missing.append("allergy history")
        if patient.medications is None:
            missing.append("current medications (interaction check)")
        if (patient.sex or "").lower().startswith("f") and patient.age is not None and 12 <= patient.age <= 55 and patient.pregnant is None:
            missing.append("pregnancy status")
        concerns.append("Medication advice must be reviewed by a clinician before it is acted on.")

    low = rec.lower()
    if any(ph in low for ph in FALSE_REASSURANCE_PHRASES) and (safety.prompt_assessment_indicated or safety.urgent_escalation or missing):
        concerns.append("Possible false reassurance given the urgency of the case or missing information.")
    return missing, concerns
