# symptom_extractor.py
import requests, json
from utils import OLLAMA_URL, MODEL_NAME

EXTRACTION_INSTRUCTION = """
Extract these fields from the conversation and return ONLY JSON:
- chief_complaint (string)
- onset (string, e.g., '2 days', 'this morning')
- severity (string: mild/moderate/severe)
- associated_symptoms (array of strings)
- risk_factors (array of strings)
- vitals (object, e.g., {"hr": "80", "bp":"120/80", "temp":"37.0"})
If missing, use empty strings or empty lists/objects.
Conversation:
"""

def _call_ollama_simple(prompt):
    url = f"{OLLAMA_URL}/api/generate"
    payload = {"model": MODEL_NAME, "prompt": prompt, "max_tokens": 300, "temperature": 0, "stream": False}
    r = requests.post(url, json=payload, timeout=30)
    r.raise_for_status()
    resp = r.json()
    return resp.get("response") if isinstance(resp, dict) else None

def extract_structured(conversation_text):
    prompt = EXTRACTION_INSTRUCTION + "\n" + conversation_text + "\n\nReturn JSON now:"
    try:
        raw = _call_ollama_simple(prompt)
        # Try to parse JSON if model returns JSON
        if raw:
            raw = raw.strip()
            # sometimes model returns backticks
            for c in ("```json\n", "```", "`"):
                raw = raw.replace(c, "")
            return json.loads(raw)
    except Exception:
        pass
    # fallback: minimal skeleton if parsing fails
    return {
        "chief_complaint": conversation_text[:120],
        "onset": "",
        "severity": "",
        "associated_symptoms": [],
        "risk_factors": [],
        "vitals": {}
    }
