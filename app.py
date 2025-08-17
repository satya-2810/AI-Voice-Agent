from fastapi import FastAPI, File, UploadFile, Request, HTTPException, WebSocket
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import json
import logging
import tempfile
import base64
import requests
import os
import time
from typing import List, Optional
import time
import wave

# Import configuration and services
from config import settings
from services.chat_service import ChatService
from services.stt_service import STTService
from services.llm_service import LLMService
from services.tts_service import TTSService

# Setup logging
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="AI Voice Chat Agent",
    version="1.0.0",
    description="AI-powered voice chat application with STT, LLM, and TTS capabilities"
)

# Mount static files and templates
app.mount("/static", StaticFiles(directory=settings.static_dir), name="static")
templates = Jinja2Templates(directory=settings.templates_dir)

# Initialize services
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

@app.post("/agent/chat/{session_id}")
async def process_voice_chat(session_id: str, file: UploadFile = File(...)):
    """Process voice chat request through the AI pipeline."""
    try:
        # Validate file
        if not file.filename.lower().endswith(('.wav', '.mp3', '.m4a', '.ogg')):
            raise HTTPException(status_code=400, detail="Unsupported audio format")
        
        # Save uploaded file temporarily
        temp_file_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
                temp_file_path = temp_file.name
                content = await file.read()
                temp_file.write(content)
            
            logger.info(f"Processing voice chat for session: {session_id}")
            logger.info(f"Audio file size: {len(content)} bytes")
            
            # STT: Transcribe audio to text
            try:
                user_text = stt_service.transcribe_audio(temp_file_path)
                logger.info(f"Transcription successful: {user_text}")
            except Exception as e:
                logger.error(f"STT failed: {str(e)}")
                user_text = "Sorry, I couldn't understand the audio. Please try again."
            
            # Add user message to chat history using ChatService
            chat_service.add_message(session_id, "user", user_text)
            
            # LLM: Generate AI response
            try:
                # Get recent conversation history from ChatService
                conversation_history = chat_service.get_recent_messages(
                    session_id, 
                    limit=settings.max_conversation_history
                )
                conversation_prompt = llm_service.format_conversation_prompt(conversation_history)
                ai_response = llm_service.generate_response(conversation_prompt)
                logger.info(f"LLM response generated: {ai_response[:100]}...")
            except Exception as e:
                logger.error(f"LLM failed: {str(e)}")
                ai_response = "I'm sorry, I encountered an issue processing your request. Please try again."
            
            # Add AI response to chat history using ChatService
            chat_service.add_message(session_id, "assistant", ai_response)
            
            # TTS: Convert AI response to audio
            try:
                audio_base64 = await tts_service.generate_audio(
                    ai_response, 
                    voice_id=settings.default_voice_id
                )

                if audio_base64:
                    logger.info("TTS audio generated successfully")
                else:
                    logger.warning("TTS returned empty audio")

            except Exception as e:
                logger.error(f"TTS failed: {str(e)}")
                audio_base64 = ""

            logger.info(f"Generated response for session {session_id}")

            return JSONResponse(content={
                "audio_base64": audio_base64,
                "transcription": user_text,
                "ai_response": ai_response,
                "session_id": session_id,
                "status": "success" if audio_base64 else "tts_failed"
            })
            
        finally:
            # Cleanup temp file
            if temp_file_path and os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
                
    except Exception as e:
        logger.error(f"Error processing voice chat: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Processing error: {str(e)}")

@app.get("/agent/history/{session_id}")
async def get_chat_history(session_id: str):
    """Get chat history for a session."""
    messages = chat_service.get_messages_as_dict(session_id)
    return {
        "session_id": session_id,
        "messages": messages,
        "total_messages": len(messages)
    }

@app.delete("/agent/session/{session_id}")
async def clear_session(session_id: str):
    """Clear chat session."""
    chat_service.clear_session(session_id)
    return {"message": f"Session {session_id} cleared"}

@app.get("/agent/sessions")
async def get_active_sessions():
    """Get information about active sessions."""
    return {
        "active_sessions": chat_service.get_session_count(),
        "status": "active"
    }

@app.post("/agent/test/{service}")
async def test_service(service: str):
    """Test individual services."""
    try:
        if service == "stt":
            # This would need a test audio file
            return {"service": "stt", "status": "Service initialized", "available": bool(settings.assemblyai_api_key)}
        elif service == "llm":
            test_response = llm_service.generate_response("Say hello")
            return {"service": "llm", "status": "working", "response": test_response[:100]}
        elif service == "tts":
            # Test TTS without actually generating audio
            return {"service": "tts", "status": "Service initialized", "available": bool(settings.murf_api_key)}
        else:
            raise HTTPException(status_code=400, detail="Invalid service name")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Service test failed: {str(e)}")

@app.on_event("startup")
async def startup_event():
    """Application startup event"""
    logger.info("AI Voice Chat Agent starting up...")
    logger.info(f"Environment: {'Production' if settings.is_production() else 'Development'}")
    logger.info(f"Host: {settings.host}:{settings.port}")
    logger.info(f"Temp directory: {settings.temp_dir}")
    
    # Log API key status
    api_status = settings.get_api_key_status()
    logger.info(f"API Keys Status: {api_status}")
    
    # Initialize services
    logger.info("Initializing services...")
    logger.info("✓ Chat Service initialized")
    logger.info("✓ STT Service initialized")
    logger.info("✓ LLM Service initialized") 
    logger.info("✓ TTS Service initialized")
    
    logger.info("Application started successfully!")

@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown event"""
    logger.info("AI Voice Chat Agent shutting down...")
    
    # Cleanup temp files
    temp_dir = settings.temp_dir
    if os.path.exists(temp_dir):
        cleaned_files = 0
        for file in os.listdir(temp_dir):
            file_path = os.path.join(temp_dir, file)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
                    cleaned_files += 1
            except Exception as e:
                logger.error(f"Error cleaning up file {file_path}: {e}")
        
        if cleaned_files > 0:
            logger.info(f"Cleaned up {cleaned_files} temporary files")
    
    logger.info("Application shutdown complete!")

# Error handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions"""
    return JSONResponse(
        status_code=exc.status_code,
        content={"message": exc.detail, "status": "error"}
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions"""
    logger.error(f"Unhandled exception: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={"message": "Internal server error", "status": "error"}
    )
    
# Add these debug endpoints to your existing app.py file (after your existing routes)

@app.post("/debug/test-tts")
async def debug_test_tts():
    """Debug endpoint to test TTS service directly"""
    try:
        test_text = "Hello, this is a test of the Murf AI text to speech service."
        
        logger.info("=== TTS DEBUG TEST ===")
        logger.info(f"API Key present: {bool(settings.murf_api_key)}")
        logger.info(f"API Key length: {len(settings.murf_api_key) if settings.murf_api_key else 0}")
        logger.info(f"Base URL: {settings.murf_base_url}")
        logger.info(f"Test text: {test_text}")
        
        # Test TTS service
        audio_base64 = await tts_service.generate_audio(test_text)
        
        result = {
            "service": "tts",
            "test_text": test_text,
            "api_key_present": bool(settings.murf_api_key),
            "api_key_length": len(settings.murf_api_key) if settings.murf_api_key else 0,
            "base_url": settings.murf_base_url,
            "audio_generated": bool(audio_base64),
            "audio_length": len(audio_base64) if audio_base64 else 0,
            "status": "success" if audio_base64 else "failed"
        }
        
        if audio_base64:
            result["audio_base64_preview"] = audio_base64[:100] + "..." if len(audio_base64) > 100 else audio_base64
        
        logger.info(f"TTS Test Result: {result}")
        return result
        
    except Exception as e:
        logger.error(f"TTS debug test failed: {str(e)}")
        logger.exception("TTS Debug Exception:")
        return {
            "service": "tts",
            "status": "error",
            "error": str(e),
            "api_key_present": bool(settings.murf_api_key) if hasattr(settings, 'murf_api_key') else False
        }

@app.get("/debug/voices")
async def debug_get_voices():
    """Debug endpoint to get available Murf voices"""
    try:
        voices = await tts_service.get_available_voices()
        return {
            "voices": voices,
            "count": len(voices.get('voices', [])) if isinstance(voices, dict) else 0,
            "status": "success"
        }
    except Exception as e:
        logger.error(f"Get voices debug failed: {str(e)}")
        return {
            "status": "error",
            "error": str(e)
        }

@app.get("/debug/config")
async def debug_config():
    """Debug endpoint to check configuration"""
    try:
        config_info = {
            "murf_api_key_present": bool(getattr(settings, 'murf_api_key', None)),
            "murf_api_key_length": len(getattr(settings, 'murf_api_key', '')) if getattr(settings, 'murf_api_key', None) else 0,
            "murf_base_url": getattr(settings, 'murf_base_url', 'Not set'),
            "default_voice_id": getattr(settings, 'default_voice_id', 'Not set'),
            "temp_dir": getattr(settings, 'temp_dir', 'Not set'),
            "temp_dir_exists": os.path.exists(getattr(settings, 'temp_dir', '')),
        }
        
        # Test TTS service connection
        config_info["tts_connection_test"] = tts_service.test_connection()
        
        return config_info
        
    except Exception as e:
        logger.error(f"Config debug failed: {str(e)}")
        return {
            "status": "error",
            "error": str(e)
        }

@app.post("/debug/minimal-tts")
async def debug_minimal_tts():
    """Minimal TTS test with hardcoded values"""
    try:
        import aiohttp
        import json
        
        # Use your actual API key and endpoint
        api_key = settings.murf_api_key
        if not api_key:
            return {"error": "No API key found"}
        
        # Murf AI API endpoint (update this to the correct one)
        url = "https://api.murf.ai/v1/speech/generate"
        
        payload = {
            "voiceId": "en-IN-rohan",
            "text": "Hello world test",
            "format": "MP3"
        }
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        logger.info(f"Making direct request to: {url}")
        logger.info(f"Payload: {json.dumps(payload)}")
        logger.info(f"Headers: {dict(headers)}")
        
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload, headers=headers) as response:
                status = response.status
                response_text = await response.text()
                
                logger.info(f"Response Status: {status}")
                logger.info(f"Response Text: {response_text}")
                
                return {
                    "url": url,
                    "status_code": status,
                    "response_text": response_text,
                    "headers_sent": dict(headers),
                    "payload_sent": payload
                }
                
    except Exception as e:
        logger.error(f"Minimal TTS test failed: {str(e)}")
        logger.exception("Exception details:")
        return {
            "error": str(e),
            "type": type(e).__name__
        }

@app.websocket("/ws/audio")
async def websocket_audio(websocket: WebSocket):
    # Accept the connection
    await websocket.accept()
    print("Audio WebSocket connection accepted")
    
    OUTPUT_FILE = "received audio.wav"
    
    wf = wave.open(OUTPUT_FILE, 'wb')
    wf.setnchannels(1)
    wf.setsampwidth(2)
    wf.setframerate(44100)
    
    try:
        while True:
            # Receive a message from the client
            data = await websocket.receive_bytes()
            print(f"Received: {len(data)} bytes")
            
            wf.writeframes(data)

    except Exception as e:
        print(f"WebSocket disconnected: {e}")
    finally:
        wf.close()
        print(f"Audio saved to {OUTPUT_FILE}")