import os
import requests

ASSEMBLYAI_API_KEY = os.getenv("ASSEMBLYAI_API_KEY", "your_assemblyai_api_key_here")

def transcribe_audio(audio_file_path: str) -> str:
    headers = {"authorization": ASSEMBLYAI_API_KEY}

    with open(audio_file_path, "rb") as f:
        upload_resp = requests.post("https://api.assemblyai.com/v2/upload", headers=headers, data=f)
    audio_url = upload_resp.json()["upload_url"]

    transcript_resp = requests.post(
        "https://api.assemblyai.com/v2/transcript",
        headers=headers,
        json={"audio_url": audio_url}
    )
    transcript_id = transcript_resp.json()["id"]

    polling_url = f"https://api.assemblyai.com/v2/transcript/{transcript_id}"
    while True:
        result = requests.get(polling_url, headers=headers).json()
        if result["status"] == "completed":
            return result["text"]
        if result["status"] == "error":
            raise Exception(result["error"])
