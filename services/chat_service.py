from typing import Dict, List
import logging

# Setup logger
logger = logging.getLogger(__name__)

class ChatMessage:
    """Simple ChatMessage class for compatibility."""
    def __init__(self, role: str, content: str):
        self.role = role
        self.content = content
    
    def to_dict(self) -> dict:
        """Convert to dictionary format."""
        return {"role": self.role, "content": self.content}

class ChatHistory:
    """Simple ChatHistory class for compatibility."""
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.messages: List[ChatMessage] = []
    
    def to_dict_list(self) -> List[dict]:
        """Convert messages to list of dictionaries."""
        return [msg.to_dict() for msg in self.messages]

class ChatService:
    """Service for managing chat histories."""
    
    def __init__(self):
        self.chat_histories: Dict[str, ChatHistory] = {}
    
    def get_or_create_session(self, session_id: str) -> ChatHistory:
        """Get existing session or create new one."""
        if session_id not in self.chat_histories:
            logger.info(f"Creating new chat session: {session_id}")
            self.chat_histories[session_id] = ChatHistory(session_id=session_id)
        
        return self.chat_histories[session_id]
    
    def add_message(self, session_id: str, role: str, content: str) -> None:
        """Add message to session history."""
        session = self.get_or_create_session(session_id)
        message = ChatMessage(role=role, content=content)
        session.messages.append(message)
        
        logger.info(f"Added {role} message to session {session_id}: {content[:100]}...")
    
    def get_messages(self, session_id: str) -> List[ChatMessage]:
        """Get all messages for a session."""
        session = self.get_or_create_session(session_id)
        return session.messages
    
    def get_messages_as_dict(self, session_id: str) -> List[dict]:
        """Get all messages for a session as dictionaries."""
        session = self.get_or_create_session(session_id)
        return session.to_dict_list()
    
    def clear_session(self, session_id: str) -> None:
        """Clear session history."""
        if session_id in self.chat_histories:
            del self.chat_histories[session_id]
            logger.info(f"Cleared session: {session_id}")
    
    def get_session_count(self) -> int:
        """Get total number of active sessions."""
        return len(self.chat_histories)
    
    def get_recent_messages(self, session_id: str, limit: int = 5) -> List[dict]:
        """Get recent messages for a session (useful for LLM context)."""
        messages = self.get_messages_as_dict(session_id)
        return messages[-limit:] if messages else []