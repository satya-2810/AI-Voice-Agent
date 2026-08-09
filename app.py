from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from managers.connection_manager import manager
from managers.session_manager import session_manager
from pipelines.voice_pipeline import VoicePipeline
import logging
import os
import uuid
import asyncio
import json
from assemblyai.streaming.v3 import (
    BeginEvent,
    StreamingClient,
    StreamingClientOptions,
    StreamingError,
    StreamingEvents,
    StreamingParameters,
    TerminationEvent,
)
import uvicorn
from config import settings
from services.chat_service import ChatService
from services.llm_service import LLMService
from services.tts_service import TTSService

user_api_keys = {"murf": None, "assembly": None, "gemini": None, "tavily": None}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


app = FastAPI(
    title="Lady Victoria - AI Voice Chat Agent",
    version="1.0.0",
    description="AI-powered voice chat application with STT, LLM, and TTS capabilities",
)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

app.mount("/static", StaticFiles(directory=settings.static_dir), name="static")
templates = Jinja2Templates(directory=settings.templates_dir)

chat_service = ChatService()

llm_service = LLMService(api_key=None, base_url=settings.gemini_base_url)
tts_service = TTSService(api_key=None, base_url=settings.murf_base_url)

voice_pipeline = VoicePipeline(chat_service, llm_service, tts_service)


@app.get("/")
async def home(request: Request):
    """Serve the main interface"""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/session")
async def session_page(request: Request):
    """Serve the voice agent session page"""
    return templates.TemplateResponse("session.html", {"request": request})


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    api_status = {
        "gemini": bool(user_api_keys["gemini"]),
        "murf": bool(user_api_keys["murf"]),
        "assemblyai": bool(user_api_keys["assembly"]),
        "tavily": bool(user_api_keys["tavily"]),
    }
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

    required = ["geminiKey", "murfKey", "assemblyKey"]

    missing = [key for key in required if not data.get(key)]

    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing API keys: {', '.join(missing)}",
        )

    user_api_keys["murf"] = data.get("murfKey")
    user_api_keys["assembly"] = data.get("assemblyKey")
    user_api_keys["gemini"] = data.get("geminiKey")
    user_api_keys["tavily"] = data.get("tavilyKey")

    llm_service.api_key = user_api_keys["gemini"]
    tts_service.api_key = user_api_keys["murf"]

    logger.info(
        f"🔑 Updated API keys (murf={bool(user_api_keys['murf'])}, "
        f"assembly={bool(user_api_keys['assembly'])}, gemini={bool(user_api_keys['gemini'])}, "
        f"tavily={bool(user_api_keys['tavily'])})"
    )

    return {"status": "ok", "keys": {k: bool(v) for k, v in user_api_keys.items()}}


# AssemblyAI streaming event handlers
def on_begin(_, event: BeginEvent):
    logger.info(f"🎤 AssemblyAI Session started: {event.id}")


def on_terminated(_, event: TerminationEvent):
    logger.info(
        f"🔌 AssemblyAI Session terminated: {event.audio_duration_seconds} seconds processed"
    )


def on_error(_, error: StreamingError):
    logger.error(f"❌ AssemblyAI error: {error}")


async def process_session_events(session, websocket):
    while True:
        event = await session.event_queue.get()

        if event["type"] == "partial":
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
    def handler(_, event):
        if not event.transcript:
            return

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
    session_id = uuid.uuid4().hex
    session = session_manager.create(session_id)
    session.tavily_key = user_api_keys["tavily"]
    await manager.connect(session_id, websocket)

    event_processor = asyncio.create_task(
        process_session_events(
            session,
            websocket,
        )
    )

    aai_key = user_api_keys["assembly"]
    streaming_client = StreamingClient(
        StreamingClientOptions(
            api_key=aai_key,
            api_host="streaming.assemblyai.com",
        )
    )

    streaming_client.on(StreamingEvents.Begin, on_begin)
    streaming_client.on(StreamingEvents.Turn, create_turn_handler(session))
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

        while True:
            data = await websocket.receive_bytes()
            streaming_client.stream(data)

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

        manager.disconnect(session_id)
        session_manager.remove(session_id)
        logger.info("Cleaned up session")
        try:
            streaming_client.disconnect(terminate=True)
        except Exception as e:
            logger.debug(e)
