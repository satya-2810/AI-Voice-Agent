import os
import logging
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

class Settings:
    """Application configuration settings."""
    
    def __init__(self):
        # API Keys
        self.gemini_api_key: Optional[str] = os.getenv("GEMINI_API_KEY")
        self.murf_api_key: Optional[str] = os.getenv("MURF_API_KEY") 
        self.assemblyai_api_key: Optional[str] = os.getenv("ASSEMBLYAI_API_KEY")
        
        # API URLs
        self.gemini_base_url: str = os.getenv(
            "GEMINI_BASE_URL", 
            "https://generativelanguage.googleapis.com/v1beta"
        )
        self.murf_base_url: str = os.getenv(
            "MURF_BASE_URL",
            "https://api.murf.ai/v1"
        )
        self.assemblyai_base_url: str = os.getenv(
            "ASSEMBLYAI_BASE_URL",
            "https://api.assemblyai.com/v2"
        )
        
        # Server Configuration
        self.host: str = os.getenv("HOST", "127.0.0.1")
        self.port: int = int(os.getenv("PORT", "8000"))
        self.reload: bool = os.getenv("RELOAD", "True").lower() == "true"
        self.debug: bool = os.getenv("DEBUG", "True").lower() == "true"
        
        # Request Configuration
        self.request_timeout: int = int(os.getenv("REQUEST_TIMEOUT", "60"))
        self.stt_polling_interval: int = int(os.getenv("STT_POLLING_INTERVAL", "2"))
        
        # Directory Configuration
        self.temp_dir: str = os.getenv("TEMP_DIR", "temp")
        self.static_dir: str = os.getenv("STATIC_DIR", "static")
        self.templates_dir: str = os.getenv("TEMPLATES_DIR", "templates")
        
        # Logging Configuration
        self.log_level: str = os.getenv("LOG_LEVEL", "INFO")
        self.log_format: str = os.getenv(
            "LOG_FORMAT",
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        
        # Voice Configuration
        self.default_voice_id: str = os.getenv("DEFAULT_VOICE_ID", "en-IN-rohan")
        self.audio_format: str = os.getenv("AUDIO_FORMAT", "MP3")
        self.sample_rate: int = int(os.getenv("SAMPLE_RATE", "22050"))
        self.bit_rate: int = int(os.getenv("BIT_RATE", "32"))
        
        # LLM Configuration
        self.max_conversation_history: int = int(os.getenv("MAX_CONVERSATION_HISTORY", "5"))
        self.llm_temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.7"))
        self.llm_max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "1024"))
        
        # Create required directories
        self._create_directories()
        
        # Setup logging
        self._setup_logging()
        
        # Validate configuration
        self._validate_config()
    
    def _create_directories(self):
        """Create required directories if they don't exist."""
        directories = [self.temp_dir, self.static_dir, self.templates_dir]
        for directory in directories:
            os.makedirs(directory, exist_ok=True)
    
    def _setup_logging(self):
        """Configure application logging."""
        logging.basicConfig(
            level=getattr(logging, self.log_level.upper()),
            format=self.log_format,
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler('app.log') if not self.debug else logging.NullHandler()
            ]
        )
    
    def _validate_config(self):
        """Validate critical configuration settings."""
        logger = logging.getLogger(__name__)
        
        # Check API keys
        missing_keys = []
        if not self.gemini_api_key:
            missing_keys.append("GEMINI_API_KEY")
        if not self.murf_api_key:
            missing_keys.append("MURF_API_KEY")
        if not self.assemblyai_api_key:
            missing_keys.append("ASSEMBLYAI_API_KEY")
        
        if missing_keys:
            logger.warning(f"Missing API keys: {', '.join(missing_keys)}")
            logger.warning("Some features may not work properly without all API keys")
        else:
            logger.info("All API keys configured successfully")
    
    def get_api_key_status(self) -> dict:
        """Get status of all API keys."""
        return {
            "gemini": bool(self.gemini_api_key),
            "murf": bool(self.murf_api_key),
            "assemblyai": bool(self.assemblyai_api_key)
        }
    
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return os.getenv("ENVIRONMENT", "development").lower() == "production"

# Global settings instance
settings = Settings()