# summary_agent.py
import requests
import json

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "mistral:latest"  

def generate_summary(conversation):
    """
    Takes a list of messages (dicts) and returns a short, structured medical summary.
    """
    try:
        if not conversation or not isinstance(conversation, list):
            return "No valid conversation to summarize."

        # Combine conversation into readable text
        dialogue = "\n".join(
            [f"{m.get('role', 'unknown').capitalize()}: {m.get('message', '')}" for m in conversation]
        )

        prompt = f"""
        Summarize the following doctor-patient conversation clearly and concisely.

        Focus on:
        - Patient's key symptoms
        - Possible causes or differential diagnosis
        - Recommended next steps

        Conversation:
        {dialogue}

        Summary:
        """

        payload = {
            "model": MODEL_NAME,
            "prompt": prompt,
            "stream": False
        }

        res = requests.post(OLLAMA_URL, json=payload)
        res.raise_for_status()
        data = res.json()

        return data.get("response", "No summary generated.")

    except Exception as e:
        print(f"❌ Summary generation error: {e}")
        return f"Error generating summary: {e}"
