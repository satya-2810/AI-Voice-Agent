import aiohttp
import asyncio
import base64
import logging
import time
from typing import Optional, Dict, Any
import json
import os
from dotenv import load_dotenv
load_dotenv()

MURF_API_KEY = os.getenv("MURF_API_KEY")

logger = logging.getLogger(__name__)

class TTSService:
    """Murf AI Text-to-Speech Service"""
    
    def __init__(self, api_key: str, base_url: str = None):
        self.api_key = api_key
        # Murf AI API endpoints
        self.base_url = base_url or "https://api.murf.ai/v1"
        self.render_url = f"{self.base_url}/speech/generate"
        self.voices_url = f"{self.base_url}/speech/voices"
        
        # Default configuration
        self.default_voice_id = "en-IN-rohan"  # Default Murf voice
        self.timeout = 30  # seconds
        
        logger.info(f"TTS Service initialized with base URL: {self.base_url}")
    
    async def generate_audio(self, text: str, voice_id: Optional[str] = None) -> str:
        """
        Generate audio from text using Murf AI
        Returns base64 encoded audio data
        """
        if not text or not text.strip():
            logger.warning("Empty text provided to TTS")
            return ""
        
        if not self.api_key:
            logger.error("Murf API key not provided")
            return ""
        
        voice_id = voice_id or self.default_voice_id
        
        try:
            logger.info(f"Generating TTS audio for text: '{text[:50]}...' with voice: {voice_id}")
            
            # Prepare the request payload for Murf AI
            payload = {
                "voiceId": voice_id,
                "text": text.strip(),
                "format": "MP3",  # Murf supports MP3, WAV
                "sampleRate": 24000.0,
                "bitRate": 128
            }
            
            headers = {
                "api-key": MURF_API_KEY or self.api_key,
                "Content-Type": "application/json",
            }
            
            # Make async request to Murf AI
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                logger.debug(f"Sending request to: {self.render_url}")
                logger.debug(f"Payload: {json.dumps(payload, indent=2)}")
                
                async with session.post(self.render_url, json=payload, headers=headers) as response:
                    logger.info(f"Murf API response status: {response.status}")
                    
                    if response.status == 200:
                        response_data = await response.json()
                        logger.debug(f"Response data keys: {list(response_data.keys())}")
                        
                        # Check different possible response formats from Murf
                        audio_data = None
                        
                        # Method 1: Direct audio data in response
                        if 'audioContent' in response_data:
                            audio_data = response_data['audioContent']
                        elif 'audio' in response_data:
                            audio_data = response_data['audio']
                        elif 'data' in response_data:
                            audio_data = response_data['data']
                        # Method 2: URL to download audio (including audioFile)
                        elif 'audioFile' in response_data:
                            audio_url = response_data['audioFile']
                            logger.info(f"Downloading audio from audioFile URL: {audio_url}")
                            audio_data = await self._download_audio(session, audio_url)
                        elif 'audioUrl' in response_data or 'url' in response_data:
                            audio_url = response_data.get('audioUrl') or response_data.get('url')
                            logger.info(f"Downloading audio from URL: {audio_url}")
                            audio_data = await self._download_audio(session, audio_url)
                        
                        if audio_data:
                            # If audio_data is already base64, return it
                            if isinstance(audio_data, str):
                                logger.info("TTS audio generated successfully (base64 string)")
                                return audio_data
                            # If it's bytes, encode to base64
                            elif isinstance(audio_data, bytes):
                                audio_base64 = base64.b64encode(audio_data).decode('utf-8')
                                logger.info(f"TTS audio generated successfully (converted {len(audio_data)} bytes to base64)")
                                return audio_base64
                        else:
                            logger.error(f"No audio data found in response: {response_data}")
                            return ""
                    
                    elif response.status == 401:
                        logger.error("Murf API authentication failed - check your API key")
                        response_text = await response.text()
                        logger.error(f"Auth error response: {response_text}")
                        return ""
                    
                    elif response.status == 400:
                        logger.error("Bad request to Murf API")
                        response_text = await response.text()
                        logger.error(f"Bad request response: {response_text}")
                        return ""
                    
                    else:
                        logger.error(f"Murf API error: {response.status}")
                        response_text = await response.text()
                        logger.error(f"Error response: {response_text}")
                        return ""
                        
        except asyncio.TimeoutError:
            logger.error(f"TTS request timed out after {self.timeout} seconds")
            return ""
        except aiohttp.ClientError as e:
            logger.error(f"HTTP client error during TTS: {str(e)}")
            return ""
        except Exception as e:
            logger.error(f"Unexpected error during TTS generation: {str(e)}")
            logger.exception("TTS Exception details:")
            return ""
    
    async def _download_audio(self, session: aiohttp.ClientSession, url: str) -> Optional[bytes]:
        """Download audio from URL"""
        try:
            async with session.get(url) as response:
                if response.status == 200:
                    audio_bytes = await response.read()
                    logger.info(f"Downloaded {len(audio_bytes)} bytes of audio")
                    return audio_bytes
                else:
                    logger.error(f"Failed to download audio: {response.status}")
                    return None
        except Exception as e:
            logger.error(f"Error downloading audio: {str(e)}")
            return None
    
    async def get_available_voices(self) -> Dict[str, Any]:
        """Get list of available voices from Murf AI"""
        if not self.api_key:
            logger.error("Murf API key not provided")
            return {}
        
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json"
            }
            
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(self.voices_url, headers=headers) as response:
                    if response.status == 200:
                        voices_data = await response.json()
                        logger.info(f"Retrieved {len(voices_data.get('voices', []))} voices")
                        return voices_data
                    else:
                        logger.error(f"Failed to get voices: {response.status}")
                        response_text = await response.text()
                        logger.error(f"Voices API response: {response_text}")
                        return {}
        except Exception as e:
            logger.error(f"Error getting voices: {str(e)}")
            return {}
    
    def test_connection(self) -> bool:
        """Test if the TTS service is properly configured"""
        if not self.api_key:
            logger.error("TTS Test Failed: No API key provided")
            return False
        
        if not self.base_url:
            logger.error("TTS Test Failed: No base URL provided")
            return False
        
        logger.info("TTS Service configuration test passed")
        return True
    
    # Synchronous wrapper for backward compatibility
    def generate_audio_sync(self, text: str, voice_id: Optional[str] = None) -> str:
        """Synchronous wrapper for generate_audio"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(self.generate_audio(text, voice_id))
        except Exception as e:
            logger.error(f"Error in sync TTS generation: {str(e)}")
            return ""
        finally:
            loop.close()