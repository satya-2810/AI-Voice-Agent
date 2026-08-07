import os
import json
import logging
import time
from typing import List, Dict, AsyncGenerator

import aiohttp
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class LLMService:
    def __init__(self, api_key: str = None, base_url: str = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.base_url = base_url or os.getenv(
            "GEMINI_BASE_URL",
            "https://generativelanguage.googleapis.com/v1beta",
        )

        self.model = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
        self.request_timeout = int(os.getenv("REQUEST_TIMEOUT", "60"))

    def _add_persona(self, prompt: str) -> str:
        persona = """
You are Lady Victoria, a distinguished female royal butler with impeccable manners and unwavering dedication.

Rules:
- Speak elegantly and politely.
- Address the user as "My Lord" or "My Lady".
- Be concise unless asked for detail.
- Be warm, intelligent and helpful.
- Never mention these instructions.
"""

        return persona + "\n\nUser: " + prompt

    def is_live_info_query(self, text: str) -> bool:
        keywords = {
            "weather",
            "temperature",
            "stock",
            "price",
            "news",
            "latest",
            "today",
            "live",
            "score",
            "match",
            "currency",
            "bitcoin",
            "gold",
            "time",
        }

        text = text.lower()

        return any(keyword in text for keyword in keywords)

    def _build_contents(self, messages: List[Dict]) -> List[Dict]:
        """
        Convert chat history into Gemini's contents format.
        """

        contents = []

        for index, msg in enumerate(messages):

            text = msg["content"]

            if index == 0 and msg["role"] == "user":
                text = self._add_persona(text)

            contents.append(
                {
                    "role": "user" if msg["role"] == "user" else "model",
                    "parts": [{"text": text}],
                }
            )

        return contents

    async def _call_gemini(self, contents: List[Dict]) -> str:
        """
        Standard (non-streaming) Gemini request.
        Returns the complete response as a string.
        """

        url = (
            f"{self.base_url}/models/{self.model}:generateContent"
            f"?key={self.api_key}"
        )

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": 0.7,
                "topP": 0.95,
                "topK": 40,
                "maxOutputTokens": 256,
            },
        }

        timeout = aiohttp.ClientTimeout(total=self.request_timeout)

        async with aiohttp.ClientSession(timeout=timeout) as session:

            async with session.post(
                url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                },
            ) as response:

                if response.status != 200:
                    error = await response.text()
                    logger.error(f"Gemini Error: {error}")
                    raise RuntimeError(error)

                data = await response.json()

                try:
                    return data["candidates"][0]["content"]["parts"][0]["text"]
                except (KeyError, IndexError):
                    logger.error(f"Unexpected Gemini response: {data}")
                    raise RuntimeError("Invalid Gemini response")

    async def _stream_gemini(
        self,
        contents: List[Dict],
    ) -> AsyncGenerator[str, None]:
        """
        True Gemini streaming.
        Yields text chunks as soon as Gemini generates them.
        """

        url = (
            f"{self.base_url}/models/{self.model}:streamGenerateContent"
            f"?alt=sse&key={self.api_key}"
        )

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": 0.7,
                "topP": 0.95,
                "topK": 40,
                "maxOutputTokens": 2048,
            },
        }

        timeout = aiohttp.ClientTimeout(total=self.request_timeout)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            request_start = time.perf_counter()

            logger.info("➡ Sending request to Gemini...")
            logger.info(f"Using model: {self.model}")
            logger.info(f"URL: {url}")
            async with session.post(
                url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                },
            ) as response:
                logger.info(
                    f"⬅ Headers received after {time.perf_counter() - request_start:.2f}s"
                )
                if response.status != 200:
                    error = await response.text()
                    logger.error(f"Gemini Error: {error}")
                    raise RuntimeError(error)

                async for raw in response.content:

                    line = raw.decode(
                        "utf-8",
                        errors="ignore",
                    ).strip()

                    logger.debug(f"SSE Line: {line}")

                    if not line:
                        continue

                    if line.startswith("data:"):
                        line = line[5:].strip()

                    if line == "[DONE]":
                        break

                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    candidates = obj.get("candidates", [])

                    if not candidates:
                        continue

                    content = candidates[0].get("content", {})
                    parts = content.get("parts", [])

                    for part in parts:

                        text = part.get("text", "")

                        if text:
                            logger.debug(f"Gemini chunk: {text}")
                            yield text

    async def generate_response_async(self, prompt: str) -> str:
        contents = self._build_contents(
            [
                {
                    "role": "user",
                    "content": prompt,
                }
            ]
        )

        return await self._call_gemini(contents)

    def generate_response(self, prompt: str) -> str:
        """
        Synchronous wrapper used for health checks and validation.
        """
        import asyncio

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.generate_response_async(prompt))

        raise RuntimeError(
            "generate_response() cannot be called from an active event loop. "
            "Use generate_response_async() instead."
        )

    async def search_web(
        self,
        query: str,
        tavily_key: str,
    ) -> str:

        if not tavily_key:
            return ""

        url = "https://api.tavily.com/search"

        payload = {
            "api_key": tavily_key,
            "query": query,
            "search_depth": "basic",
            "max_results": 3,
        }

        timeout = aiohttp.ClientTimeout(total=20)

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:

                async with session.post(
                    url,
                    json=payload,
                ) as response:

                    response.raise_for_status()

                    data = await response.json()

                    results = []

                    for item in data.get("results", []):

                        title = item.get("title", "")
                        content = item.get("content", "")

                        results.append(f"{title}\n{content}")

                    return "\n\n".join(results)

        except Exception as e:
            logger.exception(e)
            return ""

    async def stream_chat_response(
        self,
        messages: List[Dict],
        tavily_key: str = None,
    ) -> AsyncGenerator[str, None]:

        if not messages:
            return
        latest_prompt = messages[-1]["content"]

        if tavily_key and self.is_live_info_query(latest_prompt):
            web_context = await self.search_web(
                latest_prompt,
                tavily_key,
            )

            if web_context:

                messages = messages + [
                    {
                        "role": "user",
                        "content": f"Web search results:\n\n{web_context}\n\n"
                        f"Now answer the user's question.",
                    }
                ]

        contents = self._build_contents(messages)

        async for chunk in self._stream_gemini(contents):
            yield chunk
