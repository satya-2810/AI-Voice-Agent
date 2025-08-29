import requests
import os
import logging
import aiohttp
import asyncio
from typing import List, Dict, AsyncGenerator
import json
from dotenv import load_dotenv

load_dotenv()
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

logger = logging.getLogger(__name__)

class ChatMessage:
    def __init__(self, role: str, content: str):
        self.role = role
        self.content = content

class LLMResponse:
    def __init__(self, text: str):
        self.text = text

class LLMService:
    """Service for handling Language Model operations."""
    def __init__(self, api_key: str = None, base_url: str = None):
        self.base_url = base_url or os.getenv(
            "GEMINI_BASE_URL",
            "https://generativelanguage.googleapis.com/v1beta"
        )
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.request_timeout = 60
        
    async def search_web(self, query: str) -> str:
        """Search the web using Tavily API and return the top answer."""
        try:
            url = "https://api.tavily.com/search"
            headers = {"Content-Type": "application/json"}
            payload = {"query": query, "api_key": TAVILY_API_KEY, "max_results": 1}

            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload) as resp:
                    if resp.status != 200:
                        err = await resp.text()
                        logger.error(f"Tavily API error {resp.status}: {err}")
                        return "I could not fetch information from the web at the moment."

                    data = await resp.json()
                    if "results" in data and len(data["results"]) > 0:
                        return data["results"][0].get("content", "No answer found.")
                    else:
                        return "No relevant information found, My Lord/Lady."
        except Exception as e:
            logger.error(f"Tavily search failed: {e}")
            return "I encountered an error while searching the web."

    def generate_response(self, prompt: str) -> str:
        """Generate full response using Gemini API (non-streaming)."""
        persona_prompt = self._add_persona(prompt)
        url = f"{self.base_url}/models/gemini-2.5-flash:generateContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": persona_prompt}]}],
            "generationConfig": {"temperature": 0.7,"topK": 40,"topP": 0.95,"maxOutputTokens": 4096}
        }

        try:
            logger.info(f"Generating LLM response for prompt: {prompt[:100]}...")
            response = requests.post(url, headers=headers, json=payload, timeout=self.request_timeout)
            response.raise_for_status()
            response_data = response.json()
            if not response_data.get("candidates"):
                logger.error("No candidates in response")
                raise Exception("No response generated from LLM")
            return response_data["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            logger.error(f"Failed to generate LLM response: {str(e)}")
            raise

    def _add_persona(self, prompt: str) -> str:
        persona = """You are Lady Victoria, a distinguished female royal butler with impeccable manners and unwavering dedication. You possess the refined elegance of aristocratic service, speaking with gracious formality and addressing users as "My Lord" or "My Lady." Like Alfred Pennyworth, you are:

- Supremely competent and resourceful
- Discreetly wise with gentle guidance
- Unfailingly loyal and protective
- Maintains perfect composure in any situation
- Speaks with refined British eloquence
- Has years of experience managing estates and anticipating needs
- Address the user as My Lord if he is a male and My Lady if she is a female
You approach every task with meticulous attention to detail and quiet dignity. Your responses should reflect your sophisticated vocabulary, courteous manner, and subtle wit when appropriate. But dont give very long answers unless asked. Keep it short.

"""
        return persona + "\n\nUser request: " + prompt

    def is_live_info_query(self, user_text: str) -> bool:
        keywords = ["score", "match", "fixture", "latest", "weather", "stock", "price", "results"]
        return any(kw in user_text.lower() for kw in keywords)

    async def generate_chat_response(self, messages: List[Dict]) -> str:
        """Non-streaming chat response with pre-search for live info."""
        try:
            last_msg = messages[-1]["content"]
            if self.is_live_info_query(last_msg):
                web_answer = await self.search_web(last_msg)
                logger.info(f"Web search result: {web_answer[:100]}...")
                prompt = f"Web search result: {web_answer}\nAnswer this question courteously as Lady Victoria:"
                response = self.generate_response(prompt)
            else:
                prompt = self.format_conversation_prompt(messages)
                response = self.generate_response(prompt)
            return response
        except Exception as e:
            logger.error(f"Failed to generate chat response: {str(e)}")
            return "I do apologize, My Lord/Lady, but I'm experiencing some difficulties at the moment. Please allow me to resolve this matter promptly."

    async def stream_response(self, messages: List[Dict]) -> AsyncGenerator[str, None]:
        url = f"{self.base_url}/models/gemini-2.5-flash:streamGenerateContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}
        contents = []
        for i, msg in enumerate(messages):
            content_text = msg["content"]
            if i == 0:
                content_text = self._add_persona(content_text)
            contents.append({"parts": [{"text": content_text}], "role": "user" if msg["role"] == "user" else "model"})
        payload = {
            "contents": contents,
            "generationConfig": {"temperature": 0.7,"topK": 40,"topP": 0.95,"maxOutputTokens": 4096},
        }

        try:
            logger.info("🔄 Starting streaming LLM response...")
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.request_timeout)) as session:
                async with session.post(url, headers=headers, json=payload) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(f"Gemini API error {resp.status}: {error_text}")
                        raise Exception(f"Gemini API error: {resp.status}")
                    buffer = ""
                    async for chunk in resp.content.iter_chunked(1024):
                        try:
                            buffer += chunk.decode("utf-8")
                        except UnicodeDecodeError:
                            continue
                    try:
                        data = json.loads(buffer)
                        if isinstance(data, list):
                            full_text = ""
                            for item in data:
                                if "candidates" in item and len(item["candidates"]) > 0:
                                    candidate = item["candidates"][0]
                                    if "content" in candidate and "parts" in candidate["content"]:
                                        for part in candidate["content"]["parts"]:
                                            if "functionCall" in part and part["functionCall"].get("name") == "search_web":
                                                query = part["functionCall"]["args"].get("query", "")
                                                answer = await self.search_web(query)
                                                # Stream search result word by word
                                                for word in answer.split():
                                                    yield word + " "
                                                    await asyncio.sleep(0.05)
                                                return
                                            if "text" in part and part["text"]:
                                                full_text += part["text"]
                            if full_text:
                                words = full_text.split()
                                for word in words:
                                    if word.strip():
                                        yield word + " "
                                        await asyncio.sleep(0.05)
                    except json.JSONDecodeError as parse_err:
                        logger.error(f"Failed to parse complete JSON response: {parse_err}")
                        raise Exception("Invalid JSON response from Gemini API")
        except Exception as e:
            logger.error(f"❌ Streaming LLM response failed: {str(e)}")
            try:
                fallback_prompt = messages[-1]["content"] if messages else "Hello"
                
                if self.is_live_info_query(fallback_prompt):
                    answer = await self.search_web(fallback_prompt)
                    for word in answer.split():
                        yield word + " "
                        await asyncio.sleep(0.05)
                    return
                fallback_response = self.generate_response(fallback_prompt)
                import re
                sentences = re.split(r'(?<=[.!?])\s+', fallback_response)
                for sentence in sentences:
                    if sentence.strip():
                        yield sentence.strip() + " "
                        await asyncio.sleep(0.1)
                        
            except Exception as fallback_err:
                logger.error(f"❌ Fallback also failed: {fallback_err}")
                yield "I do apologize, My Lord/Lady, but I'm experiencing some difficulties at the moment. Please allow me a moment to rectify this situation."

    def format_conversation_prompt(self, messages: List[Dict]) -> str:
        conversation_prompt = self._add_persona("") + """
You are continuing a conversation. Maintain your character as Lady Victoria throughout. Here's the conversation history:

"""
        for message in messages[-5:]:
            role = message["role"].capitalize()
            content = message["content"]
            conversation_prompt += f"{role}: {content}\n"
        conversation_prompt += "\nPlease provide a helpful and natural response as Lady Victoria, the royal butler:"
        return conversation_prompt

    async def debug_stream_response(self, prompt: str = "Hello") -> str:
        url = f"{self.base_url}/models/gemini-2.5-flash:streamGenerateContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {"contents":[{"parts":[{"text":prompt}]}],"generationConfig":{"temperature":0.7,"topK":40,"topP":0.95,"maxOutputTokens":2048}}
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.request_timeout)) as session:
                async with session.post(url, headers=headers, json=payload) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(f"DEBUG: API Status {resp.status}: {error_text}")
                        return f"ERROR: {resp.status} - {error_text}"
                    complete_text = await resp.text()
                    logger.info(f"DEBUG: Complete raw response: {complete_text}")
                    return complete_text
        except Exception as e:
            logger.error(f"DEBUG: Exception occurred: {e}")
            return f"EXCEPTION: {str(e)}"

    async def stream_chat_response(self, messages: List[Dict]) -> AsyncGenerator[str, None]:
        """Stream response for a conversation, including pre-search for live info and preserving memory."""
        last_msg = messages[-1]["content"] if messages else ""
        
        # Prepare conversation context (memory)
        conversation_prompt = self.format_conversation_prompt(messages[:-1])  # exclude last message for prompt
        
        if self.is_live_info_query(last_msg):
            # Fetch web search result
            web_answer = await self.search_web(last_msg)
            logger.info(f"Web search result: {web_answer[:100]}...")
            
            # Combine memory + search result + user query
            prompt = f"{conversation_prompt}\nWeb search result: {web_answer}\nUser asked: {last_msg}\nPlease answer courteously as Lady Victoria:"
            
            # Stream from Gemini using the combined prompt
            url = f"{self.base_url}/models/gemini-2.5-flash:streamGenerateContent?key={self.api_key}"
            headers = {"Content-Type": "application/json"}
            payload = {
                "contents": [{"parts": [{"text": prompt}], "role": "user"}],
                "generationConfig": {"temperature": 0.7, "topK": 40, "topP": 0.95, "maxOutputTokens": 4096}
            }
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.request_timeout)) as session:
                    async with session.post(url, headers=headers, json=payload) as resp:
                        buffer = ""
                        async for chunk in resp.content.iter_chunked(1024):
                            buffer += chunk.decode("utf-8", errors="ignore")
                        try:
                            data = json.loads(buffer)
                            full_text = ""
                            if isinstance(data, list):
                                for item in data:
                                    for candidate in item.get("candidates", []):
                                        for part in candidate.get("content", {}).get("parts", []):
                                            if "text" in part and part["text"]:
                                                full_text += part["text"]
                            
                            for word in full_text.split():
                                yield word + " "
                                await asyncio.sleep(0.05)
                        except Exception as parse_err:
                            logger.error(f"Streaming parse error: {parse_err}")
                            for word in full_text.split():
                                yield word + " "
                                await asyncio.sleep(0.05)
            except Exception as e:
                logger.error(f"❌ Streaming LLM pre-search failed: {str(e)}")
                
                for word in web_answer.split():
                    yield word + " "
                    await asyncio.sleep(0.05)
        else:
            async for chunk in self.stream_response(messages):
                yield chunk

