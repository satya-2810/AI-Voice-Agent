from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
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

from config import settings
from services.chat_service import ChatService
from services.stt_service import STTService
from services.llm_service import LLMService
from services.tts_service import TTSService 

# Store runtime API keys provided by user
user_api_keys = {
    "murf": None,
    "assembly": None,
    "gemini": None,
    "tavily": None
}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

aai.settings.api_key = settings.assemblyai_api_key

app = FastAPI(
    title="AI Voice Chat Agent",
    version="1.0.0",
    description="AI-powered voice chat application with STT, LLM, and TTS capabilities"
)
main_loop = asyncio.get_running_loop()

# Mount static files and templates
app.mount("/static", StaticFiles(directory=settings.static_dir), name="static")
templates = Jinja2Templates(directory=settings.templates_dir)

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


@app.get("/debug/llm")
async def debug_llm():
    """Debug endpoint to test LLM service and see raw response"""
    try:
        logger.info("Testing non-streaming LLM...")
        non_streaming_result = llm_service.generate_response("Hello, how are you?")

        logger.info("Testing streaming LLM debug...")
        streaming_debug = await llm_service.debug_stream_response("Hello, how are you?")

        return {
            "status": "debug_complete",
            "non_streaming_result": non_streaming_result,
            "streaming_debug": streaming_debug,
            "api_key_present": bool(settings.gemini_api_key),
            "base_url": settings.gemini_base_url
        }
    except Exception as e:
        logger.error(f"Debug LLM error: {e}")
        return {
            "status": "debug_failed",
            "error": str(e),
            "api_key_present": bool(settings.gemini_api_key),
            "base_url": settings.gemini_base_url
        }


@app.post("/config")
async def update_config(request: Request):
    """Receive API keys from frontend and store them in memory"""
    data = await request.json()
    user_api_keys["murf"] = data.get("murfKey") or settings.murf_api_key
    user_api_keys["assembly"] = data.get("assemblyKey") or settings.assemblyai_api_key
    user_api_keys["gemini"] = data.get("geminiKey") or settings.gemini_api_key
    user_api_keys["tavily"] = data.get("tavilyKey")
    logger.info(f"🔑 Updated API keys (murf={bool(user_api_keys['murf'])}, "
                f"assembly={bool(user_api_keys['assembly'])}, gemini={bool(user_api_keys['gemini'])}, " f"tavily={bool(user_api_keys['tavily'])})")
    return {"status": "ok", "keys": {k: bool(v) for k, v in user_api_keys.items()}}


# Global WebSocket reference for turn detection
current_websocket = None
current_session_id = None
llm_triggered = False  

# AssemblyAI streaming event handlers
def on_begin(client: Type[StreamingClient], event: BeginEvent):
    logger.info(f"🎤 AssemblyAI Session started: {event.id}")


def on_turn(client: Type[StreamingClient], event: TurnEvent):
    global current_websocket, llm_triggered

    if event.transcript:
        loop = main_loop

        if not event.end_of_turn:
            llm_triggered = False
            logger.info(f"⚡ PARTIAL TRANSCRIPTION: {event.transcript}")

            if current_websocket:
                asyncio.run_coroutine_threadsafe(
                    current_websocket.send_text(
                        json.dumps({
                            "type": "partial_transcription",
                            "transcript": event.transcript,
                            "end_of_turn": False
                        })
                    ),
                    main_loop
                )
            return

        # Handle final transcript
        if event.end_of_turn:
            if llm_triggered:
                return

            if not any(char in event.transcript for char in '.!?,:;'):
                logger.info(f"⏭️ Skipping non-punctuated transcript: {event.transcript}")
                return

            llm_triggered = True
            logger.info(f"🎯 FINAL TRANSCRIPTION: {event.transcript}")

            if current_websocket:
                asyncio.run_coroutine_threadsafe(
                    current_websocket.send_text(
                        json.dumps({
                            "type": "final_transcription",
                            "transcript": event.transcript,
                            "end_of_turn": True
                        })
                    ),
                    main_loop
                )

            try:
                chat_service.add_message(current_session_id, "user", event.transcript)
            except Exception as _e:
                logger.warning(f"Could not save user message: {_e}")

            # Use user-provided API keys 
            llm_service.api_key = user_api_keys["gemini"] or settings.gemini_api_key
            tts_service.api_key = user_api_keys["murf"] or settings.murf_api_key

            async def stream_llm_and_tts(transcript: str):
                murf_ws = None
                audio_receiver_task = None
                audio_chunks = []
                audio_send_queue = asyncio.Queue()

                try:
                    print(f"🔍 Testing LLM with prompt: '{transcript}'")

                    try:
                        _ = llm_service.generate_response("ping")
                        print("✅ LLM non-streaming ping OK")
                    except Exception as test_err:
                        print(f"❌ LLM non-streaming ping failed: {test_err}")
                        if current_websocket:
                            await current_websocket.send_text(json.dumps({
                                "type": "error",
                                "message": f"LLM service unavailable: {str(test_err)}"
                            }))
                        return

                    try:
                        murf_ws = await tts_service.open_murf_ws(
                            voice_id=None,
                            context_id="static_context_123"
                        )
                        print("✅ Murf WebSocket connected")
                    except Exception as murf_err:
                        print(f"❌ Murf WebSocket connection failed: {murf_err}")
                        if current_websocket:
                            await current_websocket.send_text(json.dumps({
                                "type": "error",
                                "message": f"TTS service connection failed: {str(murf_err)}"
                            }))
                        return

                    async def pump_murf_audio_buffered():
                        chunk_index = 0
                        try:
                            async for audio_b64 in tts_service.recv_audio_buffered(murf_ws):
                                audio_chunks.append(audio_b64)
                                chunk_index += 1
                                await audio_send_queue.put({
                                    "type": "tts_audio_chunk",
                                    "audio_base64": audio_b64,
                                    "chunk_index": chunk_index
                                })
                        finally:
                            await audio_send_queue.put({"type": "tts_done"})

                    async def send_audio_to_client():
                        try:
                            while True:
                                audio_message = await audio_send_queue.get()
                                if audio_message["type"] == "tts_done":
                                    if current_websocket:
                                        await current_websocket.send_text(json.dumps({
                                            "type": "tts_done"
                                        }))
                                    break
                                if current_websocket:
                                    await current_websocket.send_text(json.dumps(audio_message))
                                await asyncio.sleep(0.05)
                        except Exception as send_err:
                            print(f"❌ Audio sender error: {send_err}")

                    audio_receiver_task = asyncio.create_task(pump_murf_audio_buffered())
                    audio_sender_task = asyncio.create_task(send_audio_to_client())

                    messages = chat_service.get_recent_messages(current_session_id, limit=10)
                    full_response = ""
                    text_buffer = ""
                    chunk_count = 0

                    try:
                        async for chunk in llm_service.stream_chat_response(messages):
                            chunk_count += 1
                            full_response += chunk
                            text_buffer += chunk

                            if current_websocket:
                                await current_websocket.send_text(json.dumps({
                                    "type": "llm_chunk",
                                    "content": chunk
                                }))

                            if (len(text_buffer) > 50 or
                                any(punct in chunk for punct in '.!?') or
                                chunk_count % 10 == 0):
                                await tts_service.send_text_event(murf_ws, text_buffer.strip())
                                text_buffer = ""

                        if text_buffer.strip():
                            await tts_service.send_text_event(murf_ws, text_buffer.strip())

                        if current_websocket:
                            await current_websocket.send_text(json.dumps({
                                "type": "llm_final_response",
                                "content": full_response
                            }))

                        chat_service.add_message(current_session_id, "assistant", full_response)
                        await tts_service.close_murf_ws(murf_ws)

                        if audio_receiver_task:
                            await audio_receiver_task
                        if audio_sender_task:
                            await audio_sender_task

                    except Exception as llm_stream_err:
                        logger.error(f"❌ LLM streaming error: {llm_stream_err}")
                        if current_websocket:
                            await current_websocket.send_text(json.dumps({
                                "type": "error",
                                "message": f"LLM streaming failed: {str(llm_stream_err)}"
                            }))
                        return

                finally:
                    if murf_ws:
                        try:
                            await murf_ws.close()
                        except Exception:
                            pass
                    if audio_receiver_task and not audio_receiver_task.done():
                        audio_receiver_task.cancel()
                    if 'audio_sender_task' in locals() and not audio_sender_task.done():
                        audio_sender_task.cancel()

            asyncio.run_coroutine_threadsafe(stream_llm_and_tts(event.transcript), main_loop)

            if current_websocket:
                asyncio.run_coroutine_threadsafe(
                    current_websocket.send_text(
                        json.dumps({
                            "type": "turn_end",
                            "message": "Turn ended - ready for next turn"
                        })
                    ),
                    main_loop
                )


def on_terminated(client: Type[StreamingClient], event: TerminationEvent):
    logger.info(f"🔌 AssemblyAI Session terminated: {event.audio_duration_seconds} seconds processed")


def on_error(client: Type[StreamingClient], error: StreamingError):
    logger.error(f"❌ AssemblyAI error: {error}")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global current_websocket, current_session_id

    await websocket.accept()
    current_websocket = websocket
    current_session_id = uuid.uuid4().hex
    logger.info(f"🎤 Client connected to /ws (session={current_session_id})")

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
    streaming_client.on(StreamingEvents.Turn, on_turn)
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
        current_websocket = None
        current_session_id = None
        logger.info("Cleaned up session")
        try:
            streaming_client.disconnect(terminate=True)
        except Exception:
            pass
        logger.info(f"✅ Audio saved at {file_path}")
