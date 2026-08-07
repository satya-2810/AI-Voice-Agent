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
        connection_manager,
    ):
        self.chat_service = chat_service
        self.llm_service = llm_service
        self.tts_service = tts_service
        self.connection_manager = connection_manager

    def save_user_message(self, session_id: str, transcript: str):
        self.chat_service.add_message(session_id, "user", transcript)

    def save_assistant_message(self, session_id: str, response: str):
        self.chat_service.add_message(
            session_id,
            "assistant",
            response,
        )

    async def stream_llm(self, session):
        messages = self.chat_service.get_recent_messages(
            session.session_id,
            limit=10,
        )

        async for chunk in self.llm_service.stream_chat_response(messages):
            yield chunk

    def validate_llm(self):
        self.llm_service.generate_response("ping")

    async def stream_llm_and_tts(self, session, transcript, websocket):
        logger.info(f"🚀 Starting VoicePipeline for: {transcript}")

        self.save_user_message(
            session.session_id,
            transcript,
        )

        murf_ws = None
        audio_receiver_task = None
        audio_send_queue = asyncio.Queue()

        try:
            murf_ws = await self.tts_service.open_murf_ws(
                voice_id=None, context_id="static_context_123"
            )
            print("✅ Murf WebSocket connected")
        except Exception as murf_err:
            print(f"❌ Murf WebSocket connection failed: {murf_err}")
            if websocket:
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
                        if websocket:
                            await websocket.send_text(json.dumps({"type": "tts_done"}))
                        break
                    if websocket:
                        await websocket.send_text(json.dumps(audio_message))
            except Exception as send_err:
                print(f"❌ Audio sender error: {send_err}")

        audio_receiver_task = asyncio.create_task(pump_murf_audio_buffered())
        audio_sender_task = asyncio.create_task(send_audio_to_client())

        start_time = time.perf_counter()
        first_chunk = True

        full_response = ""
        text_buffer = ""
        chunk_count = 0

        try:
            async for chunk in self.stream_llm(session):
                if first_chunk:
                    logger.info(
                        f"⚡ First Gemini chunk after {time.perf_counter() - start_time:.2f}s"
                    )
                    first_chunk = False

                chunk_count += 1
                full_response += chunk
                text_buffer += chunk

                if websocket:
                    await websocket.send_text(
                        json.dumps({"type": "llm_chunk", "content": chunk})
                    )

                if len(text_buffer) >= 20 or any(p in text_buffer for p in ".!?"):
                    logger.info(f"➡ Sending to Murf: {text_buffer}")

                    await self.tts_service.send_text_event(
                        murf_ws,
                        text_buffer.strip(),
                    )

                    text_buffer = ""

            if text_buffer.strip():
                await self.tts_service.send_text_event(murf_ws, text_buffer.strip())

            if websocket:
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "llm_final_response",
                            "content": full_response,
                        }
                    )
                )

                self.save_assistant_message(
                    session.session_id,
                    full_response,
                )
                await self.tts_service.close_murf_ws(murf_ws)

                if audio_receiver_task:
                    await audio_receiver_task
                if audio_sender_task:
                    await audio_sender_task

        except Exception as llm_stream_err:
            logger.error(f"❌ LLM streaming error: {llm_stream_err}")
            if websocket:
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
            if "audio_sender_task" in locals() and not audio_sender_task.done():
                audio_sender_task.cancel()
