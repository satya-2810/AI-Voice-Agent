import logging
import asyncio
import json
import time

logger = logging.getLogger(__name__)


class VoicePipeline:

    def __init__(
        self,
        chat_service,
        llm_service,
        tts_service,
    ):
        self.chat_service = chat_service
        self.llm_service = llm_service
        self.tts_service = tts_service

    def save_user_message(self, session_id: str, transcript: str):
        self.chat_service.add_message(session_id, "user", transcript)

    def save_assistant_message(self, session_id: str, response: str):
        self.chat_service.add_message(session_id, "assistant", response)

    async def stream_llm(self, session, tavily_key=None):
        messages = self.chat_service.get_recent_messages(
            session.session_id,
            limit=10,
        )

        async for chunk in self.llm_service.stream_chat_response(
            messages, tavily_key=tavily_key
        ):
            yield chunk

    async def stream_llm_and_tts(self, session, transcript, websocket):
        logger.info(f"🚀 Starting VoicePipeline for: {transcript}")
        tavily_key = getattr(session, "tavily_key", None)
        self.save_user_message(session.session_id, transcript)

        murf_ws = None
        audio_receiver_task = None
        audio_sender_task = None
        audio_send_queue = asyncio.Queue()

        try:
            murf_ws = await self.tts_service.open_murf_ws(
                voice_id=None, context_id="static_context_123"
            )
            logger.info("✅ Murf WebSocket connected")
        except Exception as murf_err:
            logger.error(f"❌ Murf WebSocket connection failed: {murf_err}")

            await websocket.send_text(
                json.dumps(
                    {
                        "type": "error",
                        "message": f"TTS service connection failed: {str(murf_err)}",
                    }
                )
            )
            return

        async def pump_murf_audio_buffered():
            chunk_index = 0
            try:
                async for audio_b64 in self.tts_service.recv_audio_buffered(murf_ws):
                    chunk_index += 1
                    await audio_send_queue.put(
                        {
                            "type": "tts_audio_chunk",
                            "audio_base64": audio_b64,
                            "chunk_index": chunk_index,
                        }
                    )
            finally:
                await audio_send_queue.put({"type": "tts_done"})

        async def send_audio_to_client():
            try:
                while True:
                    audio_message = await audio_send_queue.get()
                    if audio_message["type"] == "tts_done":
                        await websocket.send_text(json.dumps({"type": "tts_done"}))
                        break
                    await websocket.send_text(json.dumps(audio_message))
            except Exception as send_err:
                logger.error(f"❌ Audio sender error: {send_err}")

        audio_receiver_task = asyncio.create_task(pump_murf_audio_buffered())
        audio_sender_task = asyncio.create_task(send_audio_to_client())

        start_time = time.perf_counter()
        first_chunk = True

        full_response = ""
        text_buffer = ""

        try:
            async for chunk in self.stream_llm(session, tavily_key=tavily_key):
                if first_chunk:
                    logger.info(
                        f"⚡ First Gemini chunk after {time.perf_counter() - start_time:.2f}s"
                    )
                    first_chunk = False

                full_response += chunk
                text_buffer += chunk

                await websocket.send_text(
                    json.dumps({"type": "llm_chunk", "content": chunk})
                )

                ready = (
                    len(text_buffer) >= 20
                    or text_buffer.endswith(".")
                    or text_buffer.endswith("?")
                    or text_buffer.endswith("!")
                )

                if ready:
                    logger.info(f"➡ Sending to Murf: {text_buffer}")

                    await self.tts_service.send_text_event(
                        murf_ws,
                        text_buffer.strip(),
                    )

                    text_buffer = ""

            if text_buffer.strip():
                await self.tts_service.send_text_event(murf_ws, text_buffer.strip())

            await websocket.send_text(
                json.dumps(
                    {
                        "type": "llm_final_response",
                        "content": full_response,
                    }
                )
            )

            self.save_assistant_message(session.session_id, full_response)
            await self.tts_service.close_murf_ws(murf_ws)

            if audio_receiver_task:
                await audio_receiver_task
            if audio_sender_task:
                await audio_sender_task

        except Exception as llm_stream_err:
            logger.error(f"❌ LLM streaming error: {llm_stream_err}")
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "error",
                        "message": f"LLM streaming failed: {str(llm_stream_err)}",
                    }
                )
            )
            return

        finally:
            if murf_ws:
                try:
                    await murf_ws.close()
                except Exception:
                    pass
            if audio_receiver_task and not audio_receiver_task.done():
                audio_receiver_task.cancel()
            if audio_sender_task and not audio_sender_task.done():
                audio_sender_task.cancel()
