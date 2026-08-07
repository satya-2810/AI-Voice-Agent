import asyncio
import base64
import logging
import time
from typing import Optional, AsyncGenerator
import json
import websockets
from collections import deque

logger = logging.getLogger(__name__)


class TTSService:
    """Murf AI Text-to-Speech Service with Enhanced Audio Buffering"""

    def __init__(self, api_key: str, base_url: str = None):
        self.api_key = api_key
        self.base_url = base_url or "https://api.murf.ai/v1"
        self.default_voice_id = "en-US-amara"

        self.audio_buffer = deque()
        self.buffer_size = 5
        self.chunk_delay = 0.05
        logger.info(f"TTS Service initialized with base URL: {self.base_url}")

    @property
    def _ws_url(self) -> str:
        return "wss://api.murf.ai/v1/speech/stream-input"

    async def open_murf_ws(
        self, voice_id: Optional[str] = None, context_id: str = "static_context_123"
    ):
        """Open Murf WebSocket with correct URL format and send voice config."""
        if not self.api_key:
            raise RuntimeError("Murf API key not provided")
        voice_id = voice_id or self.default_voice_id

        ws_url_with_params = f"{self._ws_url}?api-key={self.api_key}&sample_rate=44100&channel_type=MONO&format=WAV"

        ws = await websockets.connect(ws_url_with_params)

        voice_config_msg = {
            "voice_config": {
                "voiceId": voice_id,
                "style": "Conversational",
                "rate": 0,
                "pitch": 0,
                "variation": 1,
            }
        }
        await ws.send(json.dumps(voice_config_msg))
        logger.info("📡 Connected to Murf WebSocket (voice config sent)")

        self.audio_buffer.clear()

        return ws

    async def send_text_event(self, ws, text: str):
        """Send a text chunk to Murf WS (streaming approach)."""
        if not text:
            return

        payload = {"text": text, "end": False}
        await ws.send(json.dumps(payload))

    async def close_murf_ws(self, ws):
        """Signal Murf that no more text is coming by sending final empty text with end=True."""
        try:
            final_payload = {"text": "", "end": True}
            await ws.send(json.dumps(final_payload))
            logger.info("📤 Sent Murf close payload (end=True)")
        except Exception as e:
            logger.debug(e)

    async def recv_audio_buffered(self, ws) -> AsyncGenerator[str, None]:
        """
        Receive audio events from Murf WS with enhanced buffering,
        yielding base64 audio chunks with optimal timing.
        """
        first_chunk = True
        chunk_count = 0
        buffer_start_time = None

        try:
            async for message in ws:
                try:
                    data = json.loads(message)
                except Exception:
                    logger.warning("Murf WS: non-JSON message ignored")
                    continue

                if "audio" in data:
                    audio_b64 = data["audio"]
                    if audio_b64:
                        chunk_count += 1

                        if first_chunk:
                            audio_bytes = base64.b64decode(audio_b64)
                            if len(audio_bytes) > 44:
                                audio_bytes = audio_bytes[44:]  # Skip WAV header
                            audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
                            first_chunk = False
                            buffer_start_time = time.time()

                        self.audio_buffer.append(
                            {
                                "audio": audio_b64,
                                "timestamp": time.time(),
                                "chunk_id": chunk_count,
                            }
                        )

                        time_since_start = time.time() - (
                            buffer_start_time or time.time()
                        )

                        if (
                            len(self.audio_buffer) >= self.buffer_size
                            or time_since_start > 0.5
                        ):

                            while self.audio_buffer:
                                buffered_chunk = self.audio_buffer.popleft()
                                yield buffered_chunk["audio"]

                                if self.audio_buffer:
                                    await asyncio.sleep(self.chunk_delay)

                if data.get("final"):
                    logger.info("✅ Murf WS signaled final")

                    while self.audio_buffer:
                        buffered_chunk = self.audio_buffer.popleft()
                        yield buffered_chunk["audio"]
                        if self.audio_buffer:
                            await asyncio.sleep(self.chunk_delay)
                    break

        except websockets.exceptions.ConnectionClosed:
            logger.info("✅ Murf WS connection closed normally")
            while self.audio_buffer:
                buffered_chunk = self.audio_buffer.popleft()
                yield buffered_chunk["audio"]
        except Exception as e:
            logger.error(f"❌ Murf WS recv error: {e}")
        finally:
            try:
                if not ws.closed:
                    await ws.close()
            except Exception:
                pass
