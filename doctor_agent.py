# # doctor_agent.py
# import requests
# from utils import OLLAMA_URL, MODEL_NAME
# import json
# import re

# SYSTEM_PROMPT = """You are a compassionate general practice physician.
# Your replies must be short, clear, and focused — no more than 3–4 sentences.
# Ask open-ended questions first, then clarifying questions.
# Use empathetic, non-alarming language. Avoid jargon or explain it simply.
# Do not give a definitive diagnosis — focus on understanding symptoms, severity, timing, and red flags.
# When provided a triage_context, deliver it clearly and explain next steps.
# Avoid unnecessary repetition or filler words.
# If you believe the consultation is complete, end your response with the token <END_CONVO>.
# """

# def _call_ollama(prompt, max_tokens=180):
#     """Call the Ollama model with a given prompt."""
#     url = f"{OLLAMA_URL}/api/generate"
#     payload = {
#         "model": MODEL_NAME,
#         "prompt": prompt,
#         "max_tokens": max_tokens,
#         "temperature": 0.25,
#         "stream": False
#     }
#     r = requests.post(url, json=payload, timeout=60)
#     r.raise_for_status()
#     resp = r.json()
#     return resp.get("response", "")

# def _shorten_reply(text, max_sentences=4):
#     """Trim reply to a limited number of sentences."""
#     sentences = re.split(r'(?<=[.!?]) +', text.strip())
#     return " ".join(sentences[:max_sentences])

# def build_prompt(message_history, triage_context=None):
#     """Build the full conversation prompt."""
#     prompt = SYSTEM_PROMPT + "\n\nThe following is a conversation between a doctor and a patient.\n\n"

#     for m in message_history:
#         role = m.get("role", "user").capitalize()
#         content = m.get("content") or m.get("message") or ""
#         prompt += f"{role}: {content}\n"

#     if triage_context:
#         prompt += f"\nTriage context: {triage_context}\n"

#     prompt += "Doctor:"
#     return prompt

# def doctor_reply(message_history, triage_context=None):
#     """Generate a doctor reply using Ollama and detect if the conversation should end."""
#     prompt = build_prompt(message_history, triage_context)
#     raw_reply = _call_ollama(prompt)
#     reply = _shorten_reply(raw_reply)
    
#     # Detect if conversation should end
#     end_convo = "<END_CONVO>" in reply
#     reply = reply.replace("<END_CONVO>", "").strip()
    
#     return reply, end_convo
# doctor_agent.py
import requests
from utils import OLLAMA_URL, MODEL_NAME
import json
import re

# System-level guidance for doctor replies
SYSTEM_PROMPT = """You are a compassionate and knowledgeable general physician.
Your tone should be calm, reassuring, and human-like.
Keep your replies short — 3 to 4 sentences maximum.
Always ask open-ended questions first to clarify symptoms and severity.
Avoid medical jargon unless clearly explained in simple terms.
If a triage context is provided, respond with awareness of urgency.
End the consultation with <END_CONVO> if the conversation feels complete.
"""

# -----------------------------
# Core API Call with Safe Fallback
# -----------------------------
def _call_ollama(prompt, model=None, max_tokens=180):
    """
    Call the Ollama API safely with retry & fallback logic.
    """
    url = f"{OLLAMA_URL}/api/generate"
    model = model or MODEL_NAME
    payload = {
        "model": model,
        "prompt": prompt,
        "max_tokens": max_tokens,
        "temperature": 0.25,
        "stream": False
    }

    try:
        r = requests.post(url, json=payload, timeout=180)
        r.raise_for_status()
        data = r.json()
        return data.get("response", "").strip()

    except requests.exceptions.ConnectionError:
        print("❌ Ollama connection error — Is `ollama serve` running?")
        return "⚠️ The doctor AI is currently offline. Please start the model server."

    except requests.exceptions.HTTPError as e:
        print(f"❌ Ollama returned HTTP error: {e}")
        # Retry once with fallback model
        if model != "mistral":
            print("🔄 Retrying with fallback model: mistral")
            return _call_ollama(prompt, model="mistral")
        return "⚠️ Unable to generate a doctor reply. Please try again later."

    except requests.exceptions.Timeout:
        print("⏰ Ollama request timed out.")
        return "⚠️ The doctor is taking too long to respond. Please try again."

    except Exception as e:
        print(f"❌ Unexpected error in _call_ollama: {e}")
        return "⚠️ Something went wrong while contacting the AI model."


# -----------------------------
# Helper: Trim reply to 3–4 sentences
# -----------------------------
def _shorten_reply(text, max_sentences=4):
    if not text:
        return "I’m here to help — could you please describe your symptoms again?"
    sentences = re.split(r'(?<=[.!?]) +', text.strip())
    return " ".join(sentences[:max_sentences])


# -----------------------------
# Build Doctor Prompt
# -----------------------------
def build_prompt(message_history, triage_context=None):
    prompt = SYSTEM_PROMPT + "\n\nThe following is a conversation between a doctor and a patient:\n\n"

    for m in message_history:
        role = m.get("role", "user").capitalize()
        content = m.get("content") or m.get("message") or ""
        prompt += f"{role}: {content}\n"

    if triage_context:
        prompt += f"\nTriage context: {triage_context}\n"

    prompt += "\nDoctor:"
    return prompt


# -----------------------------
# Main Function: Doctor Reply
# -----------------------------
def doctor_reply(message_history, triage_context=None):
    """
    Generate a doctor reply using Ollama with safety and fallbacks.
    Returns (reply, end_convo_flag)
    """
    try:
        prompt = build_prompt(message_history, triage_context)
        raw_reply = _call_ollama(prompt)
        reply = _shorten_reply(raw_reply)

        # Detect conversation end token
        end_convo = "<END_CONVO>" in reply
        reply = reply.replace("<END_CONVO>", "").strip()

        # Default fallback if no meaningful text
        if not reply or len(reply) < 5:
            reply = "I'm here to help. Can you share more details about your symptoms?"

        return reply, end_convo

    except Exception as e:
        print(f"❌ Doctor agent error in doctor_reply(): {e}")
        return "⚠️ The doctor AI is currently unavailable. Please try again later.", False
