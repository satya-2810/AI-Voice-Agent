from pydantic import BaseModel

class TextQuery(BaseModel):
    text: str

class ChatResponse(BaseModel):
    text: str
    audio_base64: str
