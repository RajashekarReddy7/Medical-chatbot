import requests, json

url = "http://localhost:11434/api/generate"
payload = {
    "model": "mistral:latest",
    "prompt": "Hello doctor, how are you?",
    "stream": False
}

try:
    r = requests.post(url, json=payload, timeout=60)
    print("Status code:", r.status_code)
    print("Response text:", r.text)
except Exception as e:
    print("Error:", e)
