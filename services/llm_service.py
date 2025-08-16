import requests
import os

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "your_gemini_api_key_here")

def query_gemini(prompt: str) -> str:
    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-pro:generateContent?key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [
            {"parts": [{"text": prompt}]}
        ]
    }
    response = requests.post(url, headers=headers, json=payload)
    response_json = response.json()
    
    return response_json["candidates"][0]["content"]["parts"][0]["text"]
