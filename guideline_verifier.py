# guideline_verifier.py
import json, os

GUIDELINE_PATH = "data/guidelines.json"

def load_guidelines():
    if not os.path.exists(GUIDELINE_PATH):
        return {}
    with open(GUIDELINE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

GUIDELINES = load_guidelines()

def verify(triage_result, top_diagnoses=[]):
    """
    triage_result: {"level":..., "reason":...}
    top_diagnoses: list of strings
    Returns possibly adjusted triage_result
    """
    # Very simple: if any diagnosis in top_diagnoses maps to a more severe level, upgrade
    level_priority = {"Emergency": 3, "Urgent": 2, "Routine": 1}
    level = triage_result["level"]
    for d in top_diagnoses:
        doc = GUIDELINES.get(d.lower())
        if doc:
            recommended = doc.get("recommended_triage", "Routine")
            if level_priority.get(recommended, 1) > level_priority.get(level, 1):
                return {"level": recommended, 
                        "reason": f"Upgraded per guideline for {d}: {doc.get('note','')}"}
    return triage_result
# guideline_verifier.py
# from langchain_community.document_loaders import PyPDFLoader
# from langchain.text_splitter import RecursiveCharacterTextSplitter
# import requests, os

# PDF_PATH = "data/The-Gale-Encyclopedia-of-Medicine-3rd-Edition-staibabussalamsula.ac_.id_.pdf"
# OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
# OLLAMA_MODEL = os.getenv("MODEL_NAME", "mistral")

# def call_ollama(prompt, max_tokens=400):
#     url = f"{OLLAMA_URL}/api/generate"
#     payload = {"model": OLLAMA_MODEL, "prompt": prompt, "max_tokens": max_tokens, "temperature": 0}
#     resp = requests.post(url, json=payload, timeout=60)
#     resp.raise_for_status()
#     data = resp.json()
#     return data.get("response", "").strip()

# # Load and split PDF
# loader = PyPDFLoader(PDF_PATH)
# docs = loader.load()
# splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)
# chunks = []
# for d in docs:
#     chunks.extend(splitter.split_text(d.page_content))

# def verify(report_text, top_k=3):
#     # Simple keyword match to pick top_k chunks
#     relevant = sorted(chunks, key=lambda c: sum(word.lower() in c.lower() for word in report_text.split()), reverse=True)[:top_k]
#     context = "\n\n---\n\n".join(relevant)
    
#     prompt = f"""
# You are a medical guideline verifier.
# Guidelines: {context}
# Report: {report_text}

# Check if the report follows the guidelines.
# Answer in JSON: {{ "compliance": "Yes/No/Partial", "reason": "short explanation"}}
# """
#     return call_ollama(prompt)
