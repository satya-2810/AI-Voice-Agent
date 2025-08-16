import requests
import os
import base64

MURF_API_KEY = os.getenv("MURF_API_KEY", "your_murf_api_key_here")

def generate_murf_audio(text: str) -> bytes:
    url = "https://api.murf.ai/v1/speech/generate"
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "api-key": MURF_API_KEY
    }
    payload = {
        "voiceId": "en-US-Wavenet-D",
        "text": text,
        "format": "MP3"
    }
    response = requests.post(url, headers=headers, json=payload)
    audio_base64 = response.json()["audioFile"]
    return base64.b64decode(audio_base64)
