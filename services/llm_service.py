import requests
import os
from typing import List, Dict
import logging

# Setup logger
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
        self.base_url = base_url or os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.request_timeout = 60

    def generate_response(self, prompt: str) -> str:
        """Generate response using Gemini API."""
        url = f"{self.base_url}/models/gemini-2.5-flash:generateContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [
                {
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": {
                "temperature": 0.7,
                "topK": 40,
                "topP": 0.95,
                "maxOutputTokens": 1024
            }
        }

        try:
            logger.info(f"Generating LLM response for prompt: {prompt[:100]}...")
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=self.request_timeout
            )
            response.raise_for_status()

            response_data = response.json()
            
            # Check if response has candidates
            if not response_data.get("candidates"):
                logger.error("No candidates in response")
                raise Exception("No response generated from LLM")
                
            generated_text = response_data["candidates"][0]["content"]["parts"][0]["text"]

            logger.info(f"LLM response generated: {generated_text[:100]}...")
            return generated_text

        except Exception as e:
            logger.error(f"Failed to generate LLM response: {str(e)}")
            raise

    def format_conversation_prompt(self, messages: List[Dict]) -> str:
        """Format conversation history into a prompt."""
        conversation_prompt = """You are a helpful AI voice assistant. Provide natural, conversational responses that are appropriate for voice interaction. Keep your responses concise but informative. Here's the conversation history:

"""
        
        for message in messages[-5:]:  # Only use last 5 messages to avoid token limits
            role = message["role"].capitalize()
            content = message["content"]
            conversation_prompt += f"{role}: {content}\n"

        conversation_prompt += "\nPlease provide a helpful and natural response as the Assistant:"
        return conversation_prompt

    def generate_chat_response(self, messages: List[Dict]) -> str:
        """Generate response for a conversation."""
        try:
            prompt = self.format_conversation_prompt(messages)
            response = self.generate_response(prompt)
            return response
        except Exception as e:
            logger.error(f"Failed to generate chat response: {str(e)}")
            return "I'm sorry, I'm having trouble processing your request right now. Please try again."