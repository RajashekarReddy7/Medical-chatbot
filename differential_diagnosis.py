import requests
import json

def generate_differential_diagnosis(conversation):
    """
    Takes a list of conversation messages (role + message)
    and returns the top 5 possible diagnoses using Ollama.
    """
    try:
        # ✅ Step 1: Build conversation context
        convo_text = "\n".join([f"{m['role']}: {m['message']}" for m in conversation])

        # ✅ Step 2: Build prompt
        prompt = f"""
You are a highly accurate clinical AI assistant.

Analyze the following doctor-patient conversation and generate the **Top 5 differential diagnoses**
that best explain the patient's symptoms and discussion context.

Conversation:
{convo_text}

Instructions:
- Output only a numbered list (1–5)
- Each line: "Disease — 1-line reasoning"
- Keep it concise and professional.
- Do NOT include disclaimers.
"""

        payload = {
            "model": "mistral:latest",
            "prompt": prompt,
            "stream": False
        }

        # ✅ Step 3: Call Ollama
        try:
            res = requests.post("http://localhost:11434/api/generate", json=payload, timeout=120)
            res.raise_for_status()
        except requests.exceptions.ConnectionError:
            print("❌ Ollama connection error — is Ollama running?")
            return "Ollama server not reachable. Please start it using `ollama serve`."

        # ✅ Step 4: Parse response safely
        try:
            data = res.json()
            diagnosis_text = data.get("response", "") or data.get("text", "")
        except json.JSONDecodeError:
            diagnosis_text = res.text

        # ✅ Step 5: Handle empty results
        if not diagnosis_text.strip():
            return "No diagnoses generated. Please provide more detailed conversation."

        return diagnosis_text.strip()

    except Exception as e:
        print(f"❌ Differential Diagnosis Agent Error: {e}")
        return f"Unable to generate differential diagnoses: {str(e)}"
