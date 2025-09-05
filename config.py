"""
Configuration settings for Telegram eBook Downloader
"""
import os
from pathlib import Path

# Telegram API Configuration
TELEGRAM_API_ID = int(os.getenv('TELEGRAM_API_ID', '0'))
TELEGRAM_API_HASH = os.getenv('TELEGRAM_API_HASH', '')

# Database Configuration
DATABASE_PATH = "telegram_downloader.db"

# Download Configuration
DOWNLOAD_DIR = Path("downloads")
SESSION_DIR = Path("sessions")
TEMP_DIR = Path("temp")

# Supported file extensions
SUPPORTED_EXTENSIONS = {
    '.pdf', '.epub', '.mobi', '.azw3', '.djvu', '.fb2', 
    '.txt', '.doc', '.docx', '.rtf', '.lit', '.pdb'
}

# Download limits
DEFAULT_MAX_CONCURRENT_DOWNLOADS = 3
DEFAULT_CHUNK_SIZE = 1024 * 1024  # 1MB chunks
DEFAULT_TIMEOUT = 30  # seconds

# WebSocket Configuration
WEBSOCKET_HEARTBEAT_INTERVAL = 30  # seconds
WEBSOCKET_MAX_CONNECTIONS = 100

# Logging Configuration
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_FILE = "telegram_downloader.log"

# Server Configuration
HOST = os.getenv('HOST', '0.0.0.0')
PORT = int(os.getenv('PORT', '3000'))
DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'

# Ensure directories exist
DOWNLOAD_DIR.mkdir(exist_ok=True)
SESSION_DIR.mkdir(exist_ok=True)
TEMP_DIR.mkdir(exist_ok=True)