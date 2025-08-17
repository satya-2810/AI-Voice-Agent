import requests
import time
import os
from typing import Optional
import logging

# Setup logger
logger = logging.getLogger(__name__)

class STTResponse:
    def __init__(self, transcript: str, confidence: Optional[float] = None):
        self.transcript = transcript
        self.confidence = confidence

class STTService:
    """Service for handling Speech-to-Text operations."""
    
    def __init__(self, api_key: str = None, base_url: str = None):
        self.base_url = base_url or os.getenv("ASSEMBLYAI_BASE_URL", "https://api.assemblyai.com/v2")
        self.api_key = api_key or os.getenv("ASSEMBLYAI_API_KEY")
        self.headers = {"authorization": self.api_key}
        self.request_timeout = 60
        self.polling_interval = 2
    
    def upload_audio(self, audio_file_path: str) -> str:
        """Upload audio file and return the upload URL."""
        upload_url = f"{self.base_url}/upload"
        
        try:
            with open(audio_file_path, "rb") as f:
                logger.info(f"Uploading audio file: {audio_file_path}")
                response = requests.post(
                    upload_url, 
                    headers=self.headers, 
                    data=f,
                    timeout=self.request_timeout
                )
                response.raise_for_status()
                
            upload_data = response.json()
            audio_url = upload_data["upload_url"]
            logger.info(f"Audio uploaded successfully: {audio_url}")
            return audio_url
            
        except Exception as e:
            logger.error(f"Failed to upload audio: {str(e)}")
            raise
    
    def start_transcription(self, audio_url: str) -> str:
        """Start transcription job and return transcript ID."""
        transcript_endpoint = f"{self.base_url}/transcript"
        transcript_request = {"audio_url": audio_url}
        
        try:
            logger.info("Starting transcription job")
            response = requests.post(
                transcript_endpoint,
                headers=self.headers,
                json=transcript_request,
                timeout=self.request_timeout
            )
            response.raise_for_status()
            
            transcript_data = response.json()
            transcript_id = transcript_data["id"]
            logger.info(f"Transcription job started: {transcript_id}")
            return transcript_id
            
        except Exception as e:
            logger.error(f"Failed to start transcription: {str(e)}")
            raise
    
    def poll_transcription(self, transcript_id: str) -> STTResponse:
        """Poll for transcription completion and return result."""
        polling_endpoint = f"{self.base_url}/transcript/{transcript_id}"
        
        logger.info(f"Polling for transcription completion: {transcript_id}")
        
        while True:
            try:
                response = requests.get(
                    polling_endpoint,
                    headers=self.headers,
                    timeout=self.request_timeout
                )
                response.raise_for_status()
                
                polling_data = response.json()
                status = polling_data["status"]
                
                if status == "completed":
                    transcript = polling_data["text"]
                    confidence = polling_data.get("confidence")
                    logger.info(f"Transcription completed: {transcript[:50]}...")
                    return STTResponse(transcript=transcript, confidence=confidence)
                    
                elif status == "error":
                    error_msg = polling_data.get("error", "Unknown transcription error")
                    logger.error(f"Transcription failed: {error_msg}")
                    raise Exception(f"Transcription error: {error_msg}")
                
                else:
                    logger.debug(f"Transcription status: {status}")
                    time.sleep(self.polling_interval)
                    
            except Exception as e:
                logger.error(f"Error polling transcription: {str(e)}")
                raise
    
    def transcribe_audio(self, audio_file_path: str) -> str:
        """Complete transcription workflow."""
        try:
            # Upload audio
            audio_url = self.upload_audio(audio_file_path)
            
            # Start transcription
            transcript_id = self.start_transcription(audio_url)
            
            # Poll for completion
            stt_response = self.poll_transcription(transcript_id)
            
            return stt_response.transcript
            
        except Exception as e:
            logger.error(f"Transcription workflow failed: {str(e)}")
            raise