#!/usr/bin/env python3
"""
AI Voice Chat Agent - Application Runner
"""
import uvicorn
import sys
import os
import logging
from pathlib import Path

# Add the current directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

from config import settings

# Setup logging for runner
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_dependencies():
    """Check if all required dependencies are available."""
    required_packages = [
        'fastapi',
        'uvicorn',
        'requests',
        'python-multipart'
    ]
    
    missing_packages = []
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        logger.error(f"Missing required packages: {', '.join(missing_packages)}")
        logger.error("Please install missing packages using: pip install " + " ".join(missing_packages))
        return False
    
    return True

def check_directories():
    """Check if required directories exist."""
    required_dirs = [
        settings.temp_dir,
        settings.static_dir,
        settings.templates_dir
    ]
    
    for directory in required_dirs:
        if not os.path.exists(directory):
            logger.warning(f"Directory '{directory}' does not exist, creating...")
            try:
                os.makedirs(directory, exist_ok=True)
                logger.info(f"✓ Created directory: {directory}")
            except Exception as e:
                logger.error(f"✗ Failed to create directory {directory}: {e}")
                return False
        else:
            logger.info(f"✓ Directory exists: {directory}")
    
    return True

def check_files():
    """Check if required files exist."""
    required_files = [
        'app.py',
        'config.py',
        'chat_service.py',
        'stt_services.py',
        'llm_services.py',
        'tts_services.py'
    ]
    
    missing_files = []
    for file in required_files:
        if not os.path.exists(file):
            missing_files.append(file)
        else:
            logger.info(f"✓ Found: {file}")
    
    if missing_files:
        logger.error(f"Missing required files: {', '.join(missing_files)}")
        return False
    
    return True

def validate_environment():
    """Validate environment and configuration."""
    logger.info("🔍 Validating environment...")
    
    # Check dependencies
    if not check_dependencies():
        return False
    
    # Check directories
    if not check_directories():
        return False
    
    # Check files
    if not check_files():
        return False
    
    # Check API keys
    api_status = settings.get_api_key_status()
    logger.info(f"🔑 API Keys Status: {api_status}")
    
    if not any(api_status.values()):
        logger.warning("⚠️  No API keys configured. Some features may not work.")
    
    logger.info("✅ Environment validation complete!")
    return True

def run_development():
    """Run the application in development mode."""
    logger.info("🚀 Starting AI Voice Chat Agent in DEVELOPMENT mode...")
    logger.info(f"📍 Server will be available at: http://{settings.host}:{settings.port}")
    logger.info("🔄 Auto-reload is enabled")
    logger.info("📝 Debug mode is enabled")
    
    try:
        uvicorn.run(
            "app:app",
            host=settings.host,
            port=settings.port,
            reload=settings.reload,
            log_level=settings.log_level.lower(),
            access_log=True,
            reload_dirs=["./"]
        )
    except KeyboardInterrupt:
        logger.info("🛑 Application stopped by user")
    except Exception as e:
        logger.error(f"❌ Failed to start server: {e}")
        sys.exit(1)

def run_production():
    """Run the application in production mode."""
    logger.info("🚀 Starting AI Voice Chat Agent in PRODUCTION mode...")
    logger.info(f"📍 Server will be available at: http://{settings.host}:{settings.port}")
    logger.info("🔒 Auto-reload is disabled")
    
    try:
        uvicorn.run(
            "app:app",
            host=settings.host,
            port=settings.port,
            reload=False,
            log_level=settings.log_level.lower(),
            access_log=True,
            workers=1  # Can be increased based on requirements
        )
    except KeyboardInterrupt:
        logger.info("🛑 Application stopped by user")
    except Exception as e:
        logger.error(f"❌ Failed to start server: {e}")
        sys.exit(1)

def main():
    """Main entry point."""
    logger.info("=" * 60)
    logger.info("🎙️  AI Voice Chat Agent - Starting Up")
    logger.info("=" * 60)
    
    # Validate environment
    if not validate_environment():
        logger.error("❌ Environment validation failed!")
        sys.exit(1)
    
    # Run based on environment
    if settings.is_production():
        run_production()
    else:
        run_development()

if __name__ == "__main__":
    main()