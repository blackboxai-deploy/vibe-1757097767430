"""
Data models for the Telegram eBook Downloader
"""
from typing import List, Optional
from pydantic import BaseModel
from enum import Enum
from datetime import datetime

class DownloadStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class FileStatus(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"
    SKIPPED = "skipped"

class FileType(str, Enum):
    PDF = "pdf"
    EPUB = "epub"
    MOBI = "mobi"
    AZW3 = "azw3"
    DJVU = "djvu"
    FB2 = "fb2"
    TXT = "txt"
    DOC = "doc"
    DOCX = "docx"

class DownloadRequest(BaseModel):
    channel_name: str
    file_types: Optional[List[FileType]] = None
    max_files: Optional[int] = None
    skip_duplicates: bool = True

class FileInfo(BaseModel):
    id: Optional[int] = None
    download_id: int
    message_id: int
    filename: str
    file_type: str
    file_size: int
    file_hash: Optional[str] = None
    download_path: Optional[str] = None
    status: FileStatus = FileStatus.PENDING
    progress: float = 0.0
    bytes_downloaded: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    error_message: Optional[str] = None

class DownloadInfo(BaseModel):
    id: Optional[int] = None
    channel_name: str
    channel_id: Optional[int] = None
    status: DownloadStatus = DownloadStatus.PENDING
    total_files: int = 0
    completed_files: int = 0
    failed_files: int = 0
    skipped_files: int = 0
    total_size: int = 0
    downloaded_size: int = 0
    progress: float = 0.0
    file_types: Optional[List[str]] = None
    max_files: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None

class ProgressUpdate(BaseModel):
    download_id: int
    file_id: Optional[int] = None
    filename: Optional[str] = None
    progress: float
    bytes_downloaded: int
    total_bytes: int
    download_speed: Optional[float] = None
    eta: Optional[int] = None
    status: str

class AuthenticationRequest(BaseModel):
    phone_number: str

class CodeVerificationRequest(BaseModel):
    phone_number: str
    code: str

class ChannelInfo(BaseModel):
    id: int
    title: str
    username: Optional[str] = None
    participants_count: Optional[int] = None
    about: Optional[str] = None

class TelegramSession(BaseModel):
    id: Optional[int] = None
    phone_number: str
    session_data: str
    is_active: bool = True
    created_at: Optional[datetime] = None
    last_used: Optional[datetime] = None