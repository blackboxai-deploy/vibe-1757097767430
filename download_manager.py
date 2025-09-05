"""
Download manager for handling file downloads with pause/resume functionality
"""
import os
import asyncio
from typing import List, Optional, Dict, Any
from pathlib import Path
from datetime import datetime
import logging
import aiofiles

from models import (
    DownloadInfo, FileInfo, DownloadStatus, FileStatus, 
    FileType, ProgressUpdate
)
from database import DatabaseManager
from telegram_client import TelegramClientManager

logger = logging.getLogger(__name__)

class DownloadManager:
    """Manages download operations with pause/resume capabilities"""
    
    def __init__(self, db_manager: DatabaseManager, telegram_manager: TelegramClientManager):
        self.db_manager = db_manager
        self.telegram_manager = telegram_manager
        self.active_downloads: Dict[int, asyncio.Task] = {}
        self.download_controls: Dict[int, Dict[str, Any]] = {}  # Control flags for each download
        self.progress_callbacks: List[callable] = []
        
        # Set database manager reference in telegram manager
        self.telegram_manager.set_db_manager(db_manager)
        
        # Download directory
        self.download_dir = Path("downloads")
        self.download_dir.mkdir(exist_ok=True)
    
    def add_progress_callback(self, callback):
        """Add a progress callback function"""
        self.progress_callbacks.append(callback)
    
    async def _notify_progress(self, update: ProgressUpdate):
        """Notify all progress callbacks"""
        for callback in self.progress_callbacks:
            try:
                await callback(update)
            except Exception as e:
                logger.error(f"Error in progress callback: {e}")
    
    async def start_download(
        self, 
        channel_name: str, 
        file_types: Optional[List[FileType]] = None,
        max_files: Optional[int] = None,
        phone_number: str = "+1234567890"  # Default for demo, should be configurable
    ) -> int:
        """Start downloading from a Telegram channel"""
        try:
            # Create download record
            download_info = DownloadInfo(
                channel_name=channel_name,
                status=DownloadStatus.PENDING,
                file_types=[ft.value for ft in file_types] if file_types else None,
                max_files=max_files
            )
            
            download_id = await self.db_manager.create_download(download_info)
            
            # Initialize download control
            self.download_controls[download_id] = {
                'paused': False,
                'cancelled': False,
                'phone_number': phone_number
            }
            
            # Start download task
            task = asyncio.create_task(self._download_worker(download_id))
            self.active_downloads[download_id] = task
            
            logger.info(f"Started download {download_id} for channel {channel_name}")
            return download_id
            
        except Exception as e:
            logger.error(f"Error starting download: {e}")
            raise
    
    async def pause_download(self, download_id: int):
        """Pause an active download"""
        if download_id in self.download_controls:
            self.download_controls[download_id]['paused'] = True
            await self.db_manager.update_download(download_id, status=DownloadStatus.PAUSED.value)
            logger.info(f"Paused download {download_id}")
    
    async def resume_download(self, download_id: int):
        """Resume a paused download"""
        if download_id in self.download_controls:
            self.download_controls[download_id]['paused'] = False
            await self.db_manager.update_download(download_id, status=DownloadStatus.ACTIVE.value)
            logger.info(f"Resumed download {download_id}")
    
    async def cancel_download(self, download_id: int):
        """Cancel an active download"""
        if download_id in self.download_controls:
            self.download_controls[download_id]['cancelled'] = True
            
            # Cancel the task if it's running
            if download_id in self.active_downloads:
                task = self.active_downloads[download_id]
                task.cancel()
                del self.active_downloads[download_id]
            
            await self.db_manager.update_download(download_id, status=DownloadStatus.CANCELLED.value)
            logger.info(f"Cancelled download {download_id}")
    
    async def _download_worker(self, download_id: int):
        """Main download worker that processes files"""
        try:
            controls = self.download_controls[download_id]
            phone_number = controls['phone_number']
            
            # Update status to active
            await self.db_manager.update_download(download_id, status=DownloadStatus.ACTIVE.value)
            
            # Get download info
            download_info = await self.db_manager.get_download(download_id)
            if not download_info:
                return
            
            # Get channel info
            channel_info = await self.telegram_manager.get_channel_info(
                phone_number, download_info.channel_name
            )
            
            if channel_info:
                await self.db_manager.update_download(download_id, channel_id=channel_info.id)
            
            # Scan for files
            file_types = download_info.file_types if download_info.file_types else None
            files_found = []
            total_size = 0
            
            async for file_info in self.telegram_manager.scan_channel_files(
                phone_number=phone_number,
                channel_name=download_info.channel_name,
                file_types=file_types,
                limit=download_info.max_files
            ):
                # Check if cancelled
                if controls['cancelled']:
                    break
                
                # Check for duplicates
                if await self.db_manager.check_file_exists(file_info.file_hash):
                    continue
                
                file_info.download_id = download_id
                file_id = await self.db_manager.create_file(file_info)
                file_info.id = file_id
                files_found.append(file_info)
                total_size += file_info.file_size
            
            # Update download statistics
            await self.db_manager.update_download(
                download_id,
                total_files=len(files_found),
                total_size=total_size
            )
            
            # Download files
            completed_files = 0
            failed_files = 0
            downloaded_size = 0
            
            for file_info in files_found:
                # Check control flags
                if controls['cancelled']:
                    break
                
                # Wait if paused
                while controls['paused'] and not controls['cancelled']:
                    await asyncio.sleep(1)
                
                if controls['cancelled']:
                    break
                
                # Download file
                success = await self._download_single_file(
                    download_id, file_info, phone_number
                )
                
                if success:
                    completed_files += 1
                    downloaded_size += file_info.file_size
                else:
                    failed_files += 1
                
                # Update progress
                progress = (completed_files + failed_files) / len(files_found) * 100
                await self.db_manager.update_download(
                    download_id,
                    completed_files=completed_files,
                    failed_files=failed_files,
                    downloaded_size=downloaded_size,
                    progress=progress
                )
                
                # Notify progress
                await self._notify_progress(ProgressUpdate(
                    download_id=download_id,
                    file_id=file_info.id,
                    filename=file_info.filename,
                    progress=progress,
                    bytes_downloaded=downloaded_size,
                    total_bytes=total_size,
                    status="downloading"
                ))
            
            # Mark as completed or failed
            final_status = DownloadStatus.COMPLETED if not controls['cancelled'] else DownloadStatus.CANCELLED
            await self.db_manager.update_download(
                download_id,
                status=final_status.value,
                completed_at=datetime.now().isoformat() if final_status == DownloadStatus.COMPLETED else None
            )
            
            logger.info(f"Download {download_id} completed: {completed_files} files, {failed_files} failed")
            
        except asyncio.CancelledError:
            logger.info(f"Download {download_id} was cancelled")
            await self.db_manager.update_download(download_id, status=DownloadStatus.CANCELLED.value)
        except Exception as e:
            logger.error(f"Error in download worker {download_id}: {e}")
            await self.db_manager.update_download(
                download_id,
                status=DownloadStatus.FAILED.value,
                error_message=str(e)
            )
        finally:
            # Clean up
            if download_id in self.active_downloads:
                del self.active_downloads[download_id]
            if download_id in self.download_controls:
                del self.download_controls[download_id]
    
    async def _download_single_file(
        self, 
        download_id: int, 
        file_info: FileInfo, 
        phone_number: str
    ) -> bool:
        """Download a single file with progress tracking"""
        try:
            # Update file status
            await self.db_manager.update_file(file_info.id, status=FileStatus.DOWNLOADING.value)
            
            # Create download path
            channel_dir = self.download_dir / f"channel_{download_id}"
            channel_dir.mkdir(exist_ok=True)
            
            file_path = channel_dir / file_info.filename
            file_info.download_path = str(file_path)
            
            # Progress callback
            async def progress_callback(current, total):
                if file_info.id:
                    progress = (current / total) * 100 if total > 0 else 0
                    await self.db_manager.update_file(
                        file_info.id,
                        progress=progress,
                        bytes_downloaded=current
                    )
                    
                    # Notify progress
                    await self._notify_progress(ProgressUpdate(
                        download_id=download_id,
                        file_id=file_info.id,
                        filename=file_info.filename,
                        progress=progress,
                        bytes_downloaded=current,
                        total_bytes=total,
                        status="downloading"
                    ))
            
            # Download the file
            download_info = await self.db_manager.get_download(download_id)
            success = await self.telegram_manager.download_file(
                phone_number=phone_number,
                channel_name=download_info.channel_name,
                message_id=file_info.message_id,
                download_path=str(file_path),
                progress_callback=progress_callback
            )
            
            if success:
                await self.db_manager.update_file(
                    file_info.id,
                    status=FileStatus.COMPLETED.value,
                    progress=100.0,
                    bytes_downloaded=file_info.file_size,
                    download_path=str(file_path)
                )
                logger.info(f"Downloaded: {file_info.filename}")
                return True
            else:
                await self.db_manager.update_file(
                    file_info.id,
                    status=FileStatus.FAILED.value,
                    error_message="Download failed"
                )
                logger.error(f"Failed to download: {file_info.filename}")
                return False
                
        except Exception as e:
            logger.error(f"Error downloading file {file_info.filename}: {e}")
            if file_info.id:
                await self.db_manager.update_file(
                    file_info.id,
                    status=FileStatus.FAILED.value,
                    error_message=str(e)
                )
            return False
    
    async def get_download_status(self, download_id: int) -> Optional[DownloadInfo]:
        """Get status of a specific download"""
        return await self.db_manager.get_download(download_id)
    
    async def get_all_downloads_status(self) -> List[DownloadInfo]:
        """Get status of all downloads"""
        return await self.db_manager.get_all_downloads()
    
    async def get_download_history(self, limit: Optional[int] = 50) -> List[DownloadInfo]:
        """Get download history"""
        return await self.db_manager.get_all_downloads(limit)
    
    async def get_download_files(self, download_id: int) -> List[FileInfo]:
        """Get files for a specific download"""
        return await self.db_manager.get_files_by_download(download_id)
    
    async def resume_interrupted_downloads(self):
        """Resume downloads that were interrupted by restart"""
        try:
            downloads = await self.db_manager.get_all_downloads()
            
            for download in downloads:
                if download.status in [DownloadStatus.ACTIVE, DownloadStatus.PAUSED]:
                    logger.info(f"Resuming interrupted download {download.id}")
                    
                    # Set up control structure
                    self.download_controls[download.id] = {
                        'paused': download.status == DownloadStatus.PAUSED,
                        'cancelled': False,
                        'phone_number': "+1234567890"  # Should be stored/configured
                    }
                    
                    # Restart download task
                    task = asyncio.create_task(self._download_worker(download.id))
                    self.active_downloads[download.id] = task
                    
        except Exception as e:
            logger.error(f"Error resuming interrupted downloads: {e}")
    
    async def cleanup(self):
        """Clean up resources"""
        # Cancel all active downloads
        for download_id in list(self.active_downloads.keys()):
            await self.cancel_download(download_id)
        
        # Wait for all tasks to complete
        if self.active_downloads:
            await asyncio.gather(*self.active_downloads.values(), return_exceptions=True)
        
        # Disconnect Telegram clients
        await self.telegram_manager.disconnect_all()
        
        logger.info("Download manager cleaned up")