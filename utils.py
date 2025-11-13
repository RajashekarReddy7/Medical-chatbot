# utils.py
import os, json
from dotenv import load_dotenv
load_dotenv()

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
MODEL_NAME = os.getenv("MODEL_NAME", "mistral:latest")
APP_PORT = int(os.getenv("APP_PORT", 8000))

# simple logger
def log_session(session_id, data):
    import time, os
    os.makedirs("logs", exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    filename = f"logs/{session_id}-{ts}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
