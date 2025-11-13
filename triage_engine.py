# triage_engine.py
def evaluate_triage(struct):
    """
    Enhanced triage evaluation function.
    Returns dict: {"level": "Emergency" | "Urgent" | "Routine", "reason": "..."}
    """

    cc = (struct.get("chief_complaint") or "").lower()
    assoc = [s.lower() for s in struct.get("associated_symptoms", []) or []]
    severity = (struct.get("severity") or "").lower()
    vitals = struct.get("vitals") or {}

    # -------------------------
    # 🩺 Red flag keywords
    # -------------------------
    red_flags = [
        "chest pain", "shortness of breath", "difficulty breathing",
        "severe bleeding", "unconscious", "loss of consciousness",
        "sudden weakness", "slurred speech", "seizure",
        "altered mental state", "vomiting blood", "severe abdominal pain"
    ]

    # If any red flag symptom is in chief complaint or associated symptoms
    triggered_flags = [rf for rf in red_flags if rf in cc or any(rf in s for s in assoc)]
    if triggered_flags:
        joined_flags = ", ".join(triggered_flags)
        return {
            "level": "Emergency",
            "reason": f"⚠️ Red flag symptoms detected ({joined_flags}). Immediate medical attention required."
        }

    # -------------------------
    # 🧭 Vital sign thresholds
    # -------------------------
    try:
        hr = int(vitals.get("hr") or 0)
        sbp = int(vitals.get("sbp") or 0)
        temp = float(vitals.get("temp") or 0)
    except:
        hr, sbp, temp = 0, 0, 0.0

    if hr and hr > 130:
        return {"level": "Emergency", "reason": "⚠️ Very high heart rate (>130 bpm) — possible tachycardia."}
    if sbp and sbp < 90:
        return {"level": "Emergency", "reason": "⚠️ Critically low blood pressure (<90 mmHg)."}
    if temp and temp >= 40:
        return {"level": "Emergency", "reason": "⚠️ Extremely high fever (≥40°C)."}

    # -------------------------
    # 🟠 Urgent conditions
    # -------------------------
    urgent_keywords = [
        "high fever", "severe pain", "infection", "dehydration",
        "dizziness", "fainting", "persistent vomiting", "blood in stool",
        "severe headache", "pain not improving"
    ]

    triggered_urgent = [uk for uk in urgent_keywords if uk in cc or any(uk in s for s in assoc)]
    if triggered_urgent:
        joined_urgent = ", ".join(triggered_urgent)
        return {
            "level": "Urgent",
            "reason": f"⚠️ Concerning symptom(s) detected ({joined_urgent}). Needs prompt evaluation."
        }

    # Urgent if severity or fever noted
    if "severe" in severity or ("fever" in severity and "high" in severity):
        return {"level": "Urgent", "reason": "⚠️ High severity or fever reported."}
    if temp and 38.5 <= temp < 40:
        return {"level": "Urgent", "reason": "⚠️ High fever present (≥38.5°C)."}

    # -------------------------
    # 🟢 Default Routine
    # -------------------------
    return {
        "level": "Routine",
        "reason": "🟢 No red flags found; symptoms appear non-urgent."
    }
