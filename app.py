from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import logging
import os
import asyncio
import assemblyai as aai
from assemblyai.streaming.v3 import (
    BeginEvent,
    StreamingClient,
    StreamingClientOptions,
    StreamingError,
    StreamingEvents,
    StreamingParameters,
    StreamingSessionParameters,
    TerminationEvent,
    TurnEvent,
)
from typing import Type

# Import configuration and services
from config import settings
from services.chat_service import ChatService
from services.stt_service import STTService
from services.llm_service import LLMService
from services.tts_service import TTSService

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Set AssemblyAI API key
aai.settings.api_key = settings.assemblyai_api_key

# Create FastAPI app
app = FastAPI(
    title="AI Voice Chat Agent",
    version="1.0.0",
    description="AI-powered voice chat application with STT, LLM, and TTS capabilities"
)

# Mount static files and templates
app.mount("/static", StaticFiles(directory=settings.static_dir), name="static")
templates = Jinja2Templates(directory=settings.templates_dir)

# Initialize services (kept for future endpoints, but not used in strict mode)
chat_service = ChatService()
stt_service = STTService(
    api_key=settings.assemblyai_api_key,
    base_url=settings.assemblyai_base_url
)
llm_service = LLMService(
    api_key=settings.gemini_api_key,
    base_url=settings.gemini_base_url
)
tts_service = TTSService(
    api_key=settings.murf_api_key,
    base_url=settings.murf_base_url
)

# Output directory for saved audio
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
        "session_count": chat_service.get_session_count()
    }


# AssemblyAI v3 streaming event handlers
def on_begin(client: Type[StreamingClient], event: BeginEvent):
    logger.info(f"🎤 AssemblyAI Session started: {event.id}")

def on_turn(client: Type[StreamingClient], event: TurnEvent):
    if event.transcript:
        if event.end_of_turn:
            logger.info(f"🎯 FINAL TRANSCRIPTION: {event.transcript}")
        else:
            logger.info(f"⚡ PARTIAL TRANSCRIPTION: {event.transcript}")

def on_terminated(client: Type[StreamingClient], event: TerminationEvent):
    logger.info(f"🔌 AssemblyAI Session terminated: {event.audio_duration_seconds} seconds processed")

def on_error(client: Type[StreamingClient], error: StreamingError):
    logger.error(f"❌ AssemblyAI error: {error}")


# ================================
# STRICT CHALLENGE: Replace old logic with /ws only
# ================================
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    Strict challenge:
    - Client streams raw PCM16 (16kHz) audio
    - Server saves it to disk (recorded_audio.raw)
    - Server forwards it to AssemblyAI Universal Streaming
    - Transcriptions are logged in Python console only
    """
    await websocket.accept()
    logger.info("🎤 Client connected to /ws")

    file_path = os.path.join(OUTPUT_DIR, "recorded_audio.raw")

    # Reset file
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception:
            pass

    # Create AssemblyAI v3 streaming client
    streaming_client = StreamingClient(
        StreamingClientOptions(
            api_key=settings.assemblyai_api_key,
            api_host="streaming.assemblyai.com",
        )
    )

    # Set up event handlers
    streaming_client.on(StreamingEvents.Begin, on_begin)
    streaming_client.on(StreamingEvents.Turn, on_turn)
    streaming_client.on(StreamingEvents.Termination, on_terminated)
    streaming_client.on(StreamingEvents.Error, on_error)

    try:
        # Connect to AssemblyAI
        streaming_client.connect(
            StreamingParameters(
                sample_rate=16000,
                format_turns=True,
            )
        )
        logger.info("✅ Connected to AssemblyAI v3 streaming API")

        with open(file_path, "ab") as f:
            while True:
                data = await websocket.receive_bytes()
                f.write(data)
                
                try:
                    # Stream audio data to AssemblyAI
                    streaming_client.stream(data)
                except Exception as e:
                    logger.error(f"Error streaming chunk: {e}")

    except WebSocketDisconnect:
        logger.info("⚠️ WebSocket connection closed by client")
    except Exception as e:
        logger.error(f"⚠️ WebSocket error: {e}")
    finally:
        try:
            streaming_client.disconnect(terminate=True)
        except Exception:
            pass
        logger.info(f"✅ Audio saved at {file_path}")