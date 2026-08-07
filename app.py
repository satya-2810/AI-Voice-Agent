from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
from managers.connection_manager import manager
from managers.session_manager import session_manager
from pipelines.voice_pipeline import VoicePipeline
import logging
import os
import uuid
import asyncio
import json
import assemblyai as aai
from assemblyai.streaming.v3 import (
    BeginEvent,
    StreamingClient,
    StreamingClientOptions,
    StreamingError,
    StreamingEvents,
    StreamingParameters,
    TerminationEvent,
    TurnEvent,
)
from typing import Type
import uvicorn
from config import settings
from services.chat_service import ChatService
from services.stt_service import STTService
from services.llm_service import LLMService
from services.tts_service import TTSService

# Store runtime API keys provided by user
user_api_keys = {"murf": None, "assembly": None, "gemini": None, "tavily": None}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

aai.settings.api_key = settings.assemblyai_api_key


app = FastAPI(
    title="Lady Victoria - AI Voice Chat Agent",
    version="1.0.0",
    description="AI-powered voice chat application with STT, LLM, and TTS capabilities",
)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

# Mount static files and templates
app.mount("/static", StaticFiles(directory=settings.static_dir), name="static")
templates = Jinja2Templates(directory=settings.templates_dir)

chat_service = ChatService()
stt_service = STTService(
    api_key=settings.assemblyai_api_key, base_url=settings.assemblyai_base_url
)
llm_service = LLMService(
    api_key=settings.gemini_api_key, base_url=settings.gemini_base_url
)
tts_service = TTSService(api_key=settings.murf_api_key, base_url=settings.murf_base_url)

voice_pipeline = VoicePipeline(
    chat_service,
    llm_service,
    tts_service,
    manager,
)

OUTPUT_DIR = os.path.join("Agent", "Output")
os.makedirs(OUTPUT_DIR, exist_ok=True)


@app.get("/")
async def home(request: Request):
    """Serve the main interface"""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    api_status = settings.get_api_key_status()
    return {
        "status": "healthy",
        "service": "AI Voice Chat Agent",
        "version": "1.0.0",
        "api_keys": api_status,
        "session_count": chat_service.get_session_count(),
    }


@app.get("/debug/llm")
async def debug_llm():
    try:
        result = await llm_service.generate_response_async(
            "Introduce yourself in one sentence."
        )

        return {
            "status": "success",
            "response": result,
        }

    except Exception as e:
        logger.exception(e)
        return {
            "status": "failed",
            "error": str(e),
        }


@app.post("/config")
async def update_config(request: Request):
    """Receive API keys from frontend and store them in memory"""
    data = await request.json()
    user_api_keys["murf"] = data.get("murfKey") or settings.murf_api_key
    user_api_keys["assembly"] = data.get("assemblyKey") or settings.assemblyai_api_key
    user_api_keys["gemini"] = data.get("geminiKey") or settings.gemini_api_key
    user_api_keys["tavily"] = data.get("tavilyKey")
    logger.info(
        f"🔑 Updated API keys (murf={bool(user_api_keys['murf'])}, "
        f"assembly={bool(user_api_keys['assembly'])}, gemini={bool(user_api_keys['gemini'])}, "
        f"tavily={bool(user_api_keys['tavily'])})"
    )
    return {"status": "ok", "keys": {k: bool(v) for k, v in user_api_keys.items()}}


# Global WebSocket reference for turn detection
current_session_id = None


# AssemblyAI streaming event handlers
def on_begin(client: Type[StreamingClient], event: BeginEvent):
    logger.info(f"🎤 AssemblyAI Session started: {event.id}")


def on_terminated(client: Type[StreamingClient], event: TerminationEvent):
    logger.info(
        f"🔌 AssemblyAI Session terminated: {event.audio_duration_seconds} seconds processed"
    )


def on_error(client: Type[StreamingClient], error: StreamingError):
    logger.error(f"❌ AssemblyAI error: {error}")


async def process_session_events(session, websocket):
    while True:
        event = await session.event_queue.get()

        if event["type"] == "partial":
            logger.info("QUEUE -> partial")
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "partial_transcription",
                        "transcript": event["transcript"],
                        "end_of_turn": False,
                    }
                )
            )

        elif event["type"] == "final":
            logger.info("QUEUE -> final")
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "final_transcription",
                        "transcript": event["transcript"],
                        "end_of_turn": True,
                    }
                )
            )

            await voice_pipeline.stream_llm_and_tts(
                session,
                event["transcript"],
                websocket,
            )


def create_turn_handler(session):
    def handler(client, event):
        logger.info(
            f"TURN EVENT: transcript={event.transcript!r}, end_of_turn={event.end_of_turn}"
        )
        if event.transcript:

            if not event.end_of_turn:
                session.llm_triggered = False
                session.event_queue.put_nowait(
                    {
                        "type": "partial",
                        "transcript": event.transcript,
                    }
                )
                return

            if session.llm_triggered:
                return

            if not any(c in event.transcript for c in ".!?,:;"):
                return

            session.llm_triggered = True

            session.event_queue.put_nowait(
                {
                    "type": "final",
                    "transcript": event.transcript,
                }
            )

    return handler


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global current_session_id

    current_session_id = uuid.uuid4().hex
    current_session = session_manager.create(current_session_id)
    await manager.connect(current_session_id, websocket)

    event_processor = asyncio.create_task(
        process_session_events(
            current_session,
            websocket,
        )
    )

    file_path = os.path.join(OUTPUT_DIR, "recorded_audio.raw")
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception:
            pass

    # Use user-provided AssemblyAI key
    aai_key = user_api_keys["assembly"] or settings.assemblyai_api_key
    streaming_client = StreamingClient(
        StreamingClientOptions(
            api_key=aai_key,
            api_host="streaming.assemblyai.com",
        )
    )

    streaming_client.on(StreamingEvents.Begin, on_begin)
    streaming_client.on(StreamingEvents.Turn, create_turn_handler(current_session))
    streaming_client.on(StreamingEvents.Termination, on_terminated)
    streaming_client.on(StreamingEvents.Error, on_error)

    try:
        streaming_client.connect(
            StreamingParameters(
                sample_rate=16000,
                format_turns=True,
                enable_turn_detection=True,
            )
        )
        logger.info("✅ Connected to AssemblyAI v3 streaming API with turn detection")

        with open(file_path, "ab") as f:
            while True:
                data = await websocket.receive_bytes()
                f.write(data)
                try:
                    streaming_client.stream(data)
                except Exception as e:
                    logger.error(f"Error streaming chunk: {e}")

    except WebSocketDisconnect:
        logger.info("⚠️ WebSocket connection closed by client")
    except Exception as e:
        logger.error(f"⚠️ WebSocket error: {e}")
    finally:
        event_processor.cancel()

        try:
            await event_processor
        except asyncio.CancelledError:
            pass

        manager.disconnect(current_session_id)
        session_manager.remove(current_session_id)
        current_session_id = None
        logger.info("Cleaned up session")
        try:
            streaming_client.disconnect(terminate=True)
        except Exception:
            pass
        logger.info(f"✅ Audio saved at {file_path}")
