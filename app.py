from fastapi import FastAPI, File, UploadFile, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import base64
import logging
import os

from services.stt_service import transcribe_audio
from services.tts_service import generate_murf_audio
from services.llm_service import query_gemini
from models.schemas import TextQuery, ChatResponse

app = FastAPI()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

@app.get("/")
def serve_ui(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

chat_histories = {}

@app.post("/agent/chat/{session_id}", response_model=ChatResponse)
async def agent_chat(session_id: str, file: UploadFile = File(...)):
    temp_file_path = f"temp_{session_id}.wav"
    
    try:
        # Save uploaded audio temporarily
        with open(temp_file_path, "wb") as f:
            f.write(await file.read())

        # STT
        transcript = transcribe_audio(temp_file_path)

        # Maintain history
        if session_id not in chat_histories:
            chat_histories[session_id] = []
        chat_histories[session_id].append({"role": "user", "content": transcript})

        # Prepare conversation
        conversation_prompt = "\n".join(
            [f"{m['role'].capitalize()}: {m['content']}" for m in chat_histories[session_id]]
        )

        # LLM
        llm_response = query_gemini(conversation_prompt)
        chat_histories[session_id].append({"role": "assistant", "content": llm_response})

        # TTS
        murf_audio = generate_murf_audio(llm_response)
        audio_b64 = base64.b64encode(murf_audio).decode("utf-8")

        return ChatResponse(text=llm_response, audio_base64=audio_b64)

    except Exception as e:
        logging.ecxeption("Error in chat processing")
        return ChatResponse(text="Sorry, something went wrong.", audio_base64="")
    
    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)


@app.post("/llm/query")
async def llm_query(payload: TextQuery):
    response_text = query_gemini(payload.text)
    return ChatResponse(text=response_text, audio_base64="")
