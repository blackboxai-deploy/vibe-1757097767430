"""
Database manager for SQLite operations
"""
import aiosqlite
import json
from typing import List, Optional, Dict, Any
from datetime import datetime
from models import DownloadInfo, FileInfo, DownloadStatus, FileStatus, TelegramSession
import logging

logger = logging.getLogger(__name__)

DATABASE_PATH = "telegram_downloader.db"

async def init_database():
    """Initialize the SQLite database with required tables"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Downloads table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS downloads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_name TEXT NOT NULL,
                channel_id INTEGER,
                status TEXT NOT NULL DEFAULT 'pending',
                total_files INTEGER DEFAULT 0,
                completed_files INTEGER DEFAULT 0,
                failed_files INTEGER DEFAULT 0,
                skipped_files INTEGER DEFAULT 0,
                total_size INTEGER DEFAULT 0,
                downloaded_size INTEGER DEFAULT 0,
                progress REAL DEFAULT 0.0,
                file_types TEXT,
                max_files INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                completed_at DATETIME,
                error_message TEXT
            )
        """)
        
        # Files table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                download_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                filename TEXT NOT NULL,
                file_type TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                file_hash TEXT,
                download_path TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                progress REAL DEFAULT 0.0,
                bytes_downloaded INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                error_message TEXT,
                FOREIGN KEY (download_id) REFERENCES downloads (id),
                UNIQUE(file_hash) ON CONFLICT IGNORE
            )
        """)
        
        # Sessions table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone_number TEXT UNIQUE NOT NULL,
                session_data TEXT NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_used DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create indexes for performance
        await db.execute("CREATE INDEX IF NOT EXISTS idx_files_download_id ON files(download_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_files_hash ON files(file_hash)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_downloads_status ON downloads(status)")
        
        await db.commit()
        logger.info("Database initialized successfully")

class DatabaseManager:
    """Manages all database operations"""
    
    def __init__(self):
        self.db_path = DATABASE_PATH
    
    async def create_download(self, download_info: DownloadInfo) -> int:
        """Create a new download record"""
        async with aiosqlite.connect(self.db_path) as db:
            file_types_json = json.dumps(download_info.file_types) if download_info.file_types else None
            
            cursor = await db.execute("""
                INSERT INTO downloads 
                (channel_name, channel_id, status, file_types, max_files)
                VALUES (?, ?, ?, ?, ?)
            """, (
                download_info.channel_name,
                download_info.channel_id,
                download_info.status.value,
                file_types_json,
                download_info.max_files
            ))
            
            download_id = cursor.lastrowid
            await db.commit()
            logger.info(f"Created download record with ID: {download_id}")
            return download_id
    
    async def update_download(self, download_id: int, **kwargs) -> bool:
        """Update download record"""
        if not kwargs:
            return False
        
        async with aiosqlite.connect(self.db_path) as db:
            # Build dynamic update query
            set_clauses = []
            values = []
            
            for key, value in kwargs.items():
                if key == 'file_types' and isinstance(value, list):
                    value = json.dumps(value)
                set_clauses.append(f"{key} = ?")
                values.append(value)
            
            values.append(datetime.now().isoformat())
            values.append(download_id)
            
            query = f"""
                UPDATE downloads 
                SET {', '.join(set_clauses)}, updated_at = ?
                WHERE id = ?
            """
            
            await db.execute(query, values)
            await db.commit()
            return True
    
    async def get_download(self, download_id: int) -> Optional[DownloadInfo]:
        """Get download by ID"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM downloads WHERE id = ?", (download_id,))
            row = await cursor.fetchone()
            
            if row:
                return self._row_to_download_info(row)
            return None
    
    async def get_all_downloads(self, limit: Optional[int] = None) -> List[DownloadInfo]:
        """Get all downloads"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            query = "SELECT * FROM downloads ORDER BY created_at DESC"
            if limit:
                query += f" LIMIT {limit}"
            
            cursor = await db.execute(query)
            rows = await cursor.fetchall()
            
            return [self._row_to_download_info(row) for row in rows]
    
    async def create_file(self, file_info: FileInfo) -> int:
        """Create a new file record"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                INSERT INTO files 
                (download_id, message_id, filename, file_type, file_size, file_hash, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                file_info.download_id,
                file_info.message_id,
                file_info.filename,
                file_info.file_type,
                file_info.file_size,
                file_info.file_hash,
                file_info.status.value
            ))
            
            file_id = cursor.lastrowid
            await db.commit()
            return file_id
    
    async def update_file(self, file_id: int, **kwargs) -> bool:
        """Update file record"""
        if not kwargs:
            return False
        
        async with aiosqlite.connect(self.db_path) as db:
            set_clauses = []
            values = []
            
            for key, value in kwargs.items():
                set_clauses.append(f"{key} = ?")
                values.append(value)
            
            values.append(datetime.now().isoformat())
            values.append(file_id)
            
            query = f"""
                UPDATE files 
                SET {', '.join(set_clauses)}, updated_at = ?
                WHERE id = ?
            """
            
            await db.execute(query, values)
            await db.commit()
            return True
    
    async def get_files_by_download(self, download_id: int) -> List[FileInfo]:
        """Get all files for a download"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT * FROM files WHERE download_id = ? ORDER BY created_at
            """, (download_id,))
            rows = await cursor.fetchall()
            
            return [self._row_to_file_info(row) for row in rows]
    
    async def check_file_exists(self, file_hash: str) -> bool:
        """Check if file already exists by hash"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT id FROM files WHERE file_hash = ? AND status = 'completed'
            """, (file_hash,))
            row = await cursor.fetchone()
            return row is not None
    
    async def save_session(self, session: TelegramSession) -> int:
        """Save or update Telegram session"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                INSERT OR REPLACE INTO sessions 
                (phone_number, session_data, is_active, last_used)
                VALUES (?, ?, ?, ?)
            """, (
                session.phone_number,
                session.session_data,
                session.is_active,
                datetime.now().isoformat()
            ))
            
            session_id = cursor.lastrowid
            await db.commit()
            return session_id
    
    async def get_session(self, phone_number: str) -> Optional[TelegramSession]:
        """Get Telegram session by phone number"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT * FROM sessions WHERE phone_number = ? AND is_active = TRUE
            """, (phone_number,))
            row = await cursor.fetchone()
            
            if row:
                return TelegramSession(
                    id=row['id'],
                    phone_number=row['phone_number'],
                    session_data=row['session_data'],
                    is_active=row['is_active'],
                    created_at=row['created_at'],
                    last_used=row['last_used']
                )
            return None
    
    def _row_to_download_info(self, row) -> DownloadInfo:
        """Convert database row to DownloadInfo"""
        file_types = json.loads(row['file_types']) if row['file_types'] else None
        
        return DownloadInfo(
            id=row['id'],
            channel_name=row['channel_name'],
            channel_id=row['channel_id'],
            status=DownloadStatus(row['status']),
            total_files=row['total_files'],
            completed_files=row['completed_files'],
            failed_files=row['failed_files'],
            skipped_files=row['skipped_files'],
            total_size=row['total_size'],
            downloaded_size=row['downloaded_size'],
            progress=row['progress'],
            file_types=file_types,
            max_files=row['max_files'],
            created_at=row['created_at'],
            updated_at=row['updated_at'],
            completed_at=row['completed_at'],
            error_message=row['error_message']
        )
    
    def _row_to_file_info(self, row) -> FileInfo:
        """Convert database row to FileInfo"""
        return FileInfo(
            id=row['id'],
            download_id=row['download_id'],
            message_id=row['message_id'],
            filename=row['filename'],
            file_type=row['file_type'],
            file_size=row['file_size'],
            file_hash=row['file_hash'],
            download_path=row['download_path'],
            status=FileStatus(row['status']),
            progress=row['progress'],
            bytes_downloaded=row['bytes_downloaded'],
            created_at=row['created_at'],
            updated_at=row['updated_at'],
            error_message=row['error_message']
        )