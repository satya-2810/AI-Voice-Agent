from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from datetime import datetime

class TextQuery(BaseModel):
    """Model for text query requests."""
    text: str = Field(..., min_length=1, max_length=5000, description="Text to process")

class ChatMessage(BaseModel):
    """Model for individual chat messages."""
    role: Literal["user", "assistant"] = Field(..., description="Message role")
    content: str = Field(..., min_length=1, description="Message content")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Message timestamp")

class ChatHistory(BaseModel):
    """Model for chat session history."""
    session_id: str = Field(..., description="Unique session identifier")
    messages: List[ChatMessage] = Field(default_factory=list, description="List of messages")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Session creation time")

class STTRequest(BaseModel):
    """Model for Speech-to-Text requests."""
    audio_url: str = Field(..., description="URL of audio file to transcribe")

class STTResponse(BaseModel):
    """Model for Speech-to-Text responses."""
    transcript: str = Field(..., description="Transcribed text")
    confidence: Optional[float] = Field(None, description="Confidence score")

class LLMRequest(BaseModel):
    """Model for Language Model requests."""
    prompt: str = Field(..., min_length=1, description="Prompt for the language model")
    max_tokens: Optional[int] = Field(1000, description="Maximum tokens to generate")

class LLMResponse(BaseModel):
    """Model for Language Model responses."""
    response: str = Field(..., description="Generated response")
    tokens_used: Optional[int] = Field(None, description="Number of tokens used")

class TTSRequest(BaseModel):
    """Model for Text-to-Speech requests."""
    text: str = Field(..., min_length=1, max_length=2000, description="Text to convert to speech")
    voice_id: str = Field("en-US-Wavenet-D", description="Voice ID to use")
    format: str = Field("MP3", description="Audio format")

class TTSResponse(BaseModel):
    """Model for Text-to-Speech responses."""
    audio_base64: str = Field(..., description="Base64 encoded audio data")
    format: str = Field(..., description="Audio format")

class AgentChatResponse(BaseModel):
    """Model for agent chat responses."""
    text: str = Field(..., description="Response text")
    audio_base64: str = Field(..., description="Base64 encoded audio response")
    session_id: str = Field(..., description="Session identifier")

class ErrorResponse(BaseModel):
    """Model for error responses."""
    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Detailed error information")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Error timestamp")