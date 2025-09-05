"""
Telegram client manager using Telethon
"""
import os
import hashlib
from typing import List, Optional, AsyncGenerator
from telethon import TelegramClient, events
from telethon.tl.types import DocumentAttributeFilename, Document
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError
from pathlib import Path
import logging

from models import FileInfo, ChannelInfo, TelegramSession
from database import DatabaseManager

logger = logging.getLogger(__name__)

# Telegram API credentials - These should be in environment variables
API_ID = int(os.getenv('TELEGRAM_API_ID', '0'))
API_HASH = os.getenv('TELEGRAM_API_HASH', '')

# Supported file extensions for eBooks
SUPPORTED_EXTENSIONS = {
    '.pdf', '.epub', '.mobi', '.azw3', '.djvu', '.fb2', 
    '.txt', '.doc', '.docx', '.rtf', '.lit', '.pdb'
}

class TelegramClientManager:
    """Manages Telegram client connections and operations"""
    
    def __init__(self):
        self.clients = {}  # phone_number -> TelegramClient
        self.db_manager = None
        
        if not API_ID or not API_HASH:
            logger.warning("Telegram API credentials not found in environment variables")
    
    def set_db_manager(self, db_manager: DatabaseManager):
        """Set database manager reference"""
        self.db_manager = db_manager
    
    async def get_client(self, phone_number: str) -> TelegramClient:
        """Get or create Telegram client for phone number"""
        if phone_number in self.clients:
            return self.clients[phone_number]
        
        # Create session file path
        session_name = f"sessions/{phone_number.replace('+', '')}"
        os.makedirs("sessions", exist_ok=True)
        
        client = TelegramClient(session_name, API_ID, API_HASH)
        self.clients[phone_number] = client
        
        return client
    
    async def authenticate(self, phone_number: str) -> dict:
        """Start Telegram authentication process"""
        try:
            client = await self.get_client(phone_number)
            await client.connect()
            
            if await client.is_user_authorized():
                return {
                    "authenticated": True,
                    "message": "Already authenticated"
                }
            
            # Send code request
            sent_code = await client.send_code_request(phone_number)
            
            return {
                "authenticated": False,
                "code_sent": True,
                "phone_code_hash": sent_code.phone_code_hash,
                "message": "Verification code sent"
            }
            
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            raise Exception(f"Failed to authenticate: {str(e)}")
    
    async def verify_code(self, phone_number: str, code: str) -> dict:
        """Verify the authentication code"""
        try:
            client = await self.get_client(phone_number)
            
            if not client.is_connected():
                await client.connect()
            
            # Try to sign in with the code
            await client.sign_in(phone=phone_number, code=code)
            
            if await client.is_user_authorized():
                # Save session to database
                if self.db_manager:
                    session_data = client.session.save()
                    session = TelegramSession(
                        phone_number=phone_number,
                        session_data=str(session_data),
                        is_active=True
                    )
                    await self.db_manager.save_session(session)
                
                return {
                    "authenticated": True,
                    "message": "Authentication successful"
                }
            else:
                return {
                    "authenticated": False,
                    "message": "Authentication failed"
                }
                
        except PhoneCodeInvalidError:
            raise Exception("Invalid verification code")
        except SessionPasswordNeededError:
            raise Exception("Two-factor authentication is enabled. Please disable it or implement 2FA support")
        except Exception as e:
            logger.error(f"Code verification error: {e}")
            raise Exception(f"Failed to verify code: {str(e)}")
    
    async def get_channel_info(self, phone_number: str, channel_name: str) -> Optional[ChannelInfo]:
        """Get information about a Telegram channel"""
        try:
            client = await self.get_client(phone_number)
            
            if not client.is_connected():
                await client.connect()
            
            if not await client.is_user_authorized():
                raise Exception("Client not authenticated")
            
            # Get channel entity
            channel = await client.get_entity(channel_name)
            
            return ChannelInfo(
                id=channel.id,
                title=channel.title,
                username=getattr(channel, 'username', None),
                participants_count=getattr(channel, 'participants_count', None),
                about=getattr(channel, 'about', None)
            )
            
        except Exception as e:
            logger.error(f"Error getting channel info: {e}")
            raise Exception(f"Failed to get channel info: {str(e)}")
    
    async def scan_channel_files(
        self, 
        phone_number: str, 
        channel_name: str, 
        file_types: Optional[List[str]] = None,
        limit: Optional[int] = None
    ) -> AsyncGenerator[FileInfo, None]:
        """Scan channel for eBook files"""
        try:
            client = await self.get_client(phone_number)
            
            if not client.is_connected():
                await client.connect()
            
            if not await client.is_user_authorized():
                raise Exception("Client not authenticated")
            
            # Get channel entity
            channel = await client.get_entity(channel_name)
            file_count = 0
            
            # Iterate through messages
            async for message in client.iter_messages(channel):
                if limit and file_count >= limit:
                    break
                
                if not message.document:
                    continue
                
                document = message.document
                if not isinstance(document, Document):
                    continue
                
                # Get filename
                filename = None
                for attr in document.attributes:
                    if isinstance(attr, DocumentAttributeFilename):
                        filename = attr.file_name
                        break
                
                if not filename:
                    continue
                
                # Check if it's a supported file type
                file_ext = Path(filename).suffix.lower()
                if file_ext not in SUPPORTED_EXTENSIONS:
                    continue
                
                # Filter by file types if specified
                if file_types and file_ext.lstrip('.') not in [ft.lower() for ft in file_types]:
                    continue
                
                # Calculate file hash for duplicate detection
                file_hash = hashlib.md5(f"{channel.id}_{message.id}_{filename}".encode()).hexdigest()
                
                file_info = FileInfo(
                    download_id=0,  # Will be set later
                    message_id=message.id,
                    filename=filename,
                    file_type=file_ext.lstrip('.'),
                    file_size=document.size,
                    file_hash=file_hash
                )
                
                file_count += 1
                yield file_info
                
        except Exception as e:
            logger.error(f"Error scanning channel: {e}")
            raise Exception(f"Failed to scan channel: {str(e)}")
    
    async def download_file(
        self, 
        phone_number: str, 
        channel_name: str, 
        message_id: int, 
        download_path: str,
        progress_callback=None
    ) -> bool:
        """Download a specific file from channel"""
        try:
            client = await self.get_client(phone_number)
            
            if not client.is_connected():
                await client.connect()
            
            if not await client.is_user_authorized():
                raise Exception("Client not authenticated")
            
            # Get channel and message
            channel = await client.get_entity(channel_name)
            message = await client.get_messages(channel, ids=message_id)
            
            if not message or not message.document:
                return False
            
            # Create download directory
            os.makedirs(os.path.dirname(download_path), exist_ok=True)
            
            # Download the file
            await client.download_media(
                message.document,
                file=download_path,
                progress_callback=progress_callback
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error downloading file: {e}")
            return False
    
    async def disconnect_all(self):
        """Disconnect all clients"""
        for client in self.clients.values():
            if client.is_connected():
                await client.disconnect()
        
        self.clients.clear()
        logger.info("All Telegram clients disconnected")
    
    def get_file_hash(self, channel_id: int, message_id: int, filename: str) -> str:
        """Generate consistent hash for file identification"""
        return hashlib.md5(f"{channel_id}_{message_id}_{filename}".encode()).hexdigest()