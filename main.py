"""
Telegram eBook Downloader - Main FastAPI Application
"""
import os
import asyncio
from pathlib import Path
from typing import List, Optional
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import logging

from database import DatabaseManager, init_database
from telegram_client import TelegramClientManager
from download_manager import DownloadManager
from models import DownloadRequest, DownloadStatus, FileInfo

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(title="Telegram eBook Downloader", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create directories
os.makedirs("static", exist_ok=True)
os.makedirs("templates", exist_ok=True)
os.makedirs("downloads", exist_ok=True)

# Mount static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Global managers
db_manager = DatabaseManager()
telegram_manager = TelegramClientManager()
download_manager = DownloadManager(db_manager, telegram_manager)

# WebSocket connections for real-time updates
active_connections: List[WebSocket] = []

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
    
    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass

manager = ConnectionManager()

@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    await init_database()
    logger.info("Application started successfully")

@app.get("/")
async def root(request: Request):
    """Serve the main application page"""
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/api/authenticate")
async def authenticate_telegram(phone_number: str):
    """Authenticate with Telegram"""
    try:
        result = await telegram_manager.authenticate(phone_number)
        return {"success": True, "message": "Authentication code sent", "data": result}
    except Exception as e:
        logger.error(f"Authentication error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/verify-code")
async def verify_code(phone_number: str, code: str):
    """Verify Telegram authentication code"""
    try:
        result = await telegram_manager.verify_code(phone_number, code)
        return {"success": True, "message": "Authentication successful", "data": result}
    except Exception as e:
        logger.error(f"Code verification error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/start-download")
async def start_download(request: DownloadRequest):
    """Start downloading from a Telegram channel"""
    try:
        download_id = await download_manager.start_download(
            channel_name=request.channel_name,
            file_types=request.file_types,
            max_files=request.max_files
        )
        
        # Broadcast update to all connected clients
        await manager.broadcast({
            "type": "download_started",
            "download_id": download_id,
            "channel": request.channel_name
        })
        
        return {
            "success": True, 
            "message": "Download started successfully", 
            "download_id": download_id
        }
    except Exception as e:
        logger.error(f"Download start error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/pause-download/{download_id}")
async def pause_download(download_id: int):
    """Pause an active download"""
    try:
        await download_manager.pause_download(download_id)
        
        await manager.broadcast({
            "type": "download_paused",
            "download_id": download_id
        })
        
        return {"success": True, "message": "Download paused successfully"}
    except Exception as e:
        logger.error(f"Download pause error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/resume-download/{download_id}")
async def resume_download(download_id: int):
    """Resume a paused download"""
    try:
        await download_manager.resume_download(download_id)
        
        await manager.broadcast({
            "type": "download_resumed",
            "download_id": download_id
        })
        
        return {"success": True, "message": "Download resumed successfully"}
    except Exception as e:
        logger.error(f"Download resume error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.delete("/api/cancel-download/{download_id}")
async def cancel_download(download_id: int):
    """Cancel an active download"""
    try:
        await download_manager.cancel_download(download_id)
        
        await manager.broadcast({
            "type": "download_cancelled",
            "download_id": download_id
        })
        
        return {"success": True, "message": "Download cancelled successfully"}
    except Exception as e:
        logger.error(f"Download cancel error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/download-status")
async def get_download_status():
    """Get status of all downloads"""
    try:
        status = await download_manager.get_all_downloads_status()
        return {"success": True, "data": status}
    except Exception as e:
        logger.error(f"Status retrieval error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/download-status/{download_id}")
async def get_specific_download_status(download_id: int):
    """Get status of a specific download"""
    try:
        status = await download_manager.get_download_status(download_id)
        if not status:
            raise HTTPException(status_code=404, detail="Download not found")
        return {"success": True, "data": status}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Status retrieval error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/download-history")
async def get_download_history(limit: Optional[int] = 50):
    """Get download history"""
    try:
        history = await download_manager.get_download_history(limit)
        return {"success": True, "data": history}
    except Exception as e:
        logger.error(f"History retrieval error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/files/{download_id}")
async def get_download_files(download_id: int):
    """Get files for a specific download"""
    try:
        files = await download_manager.get_download_files(download_id)
        return {"success": True, "data": files}
    except Exception as e:
        logger.error(f"Files retrieval error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates"""
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive and listen for client messages
            data = await websocket.receive_text()
            # Echo back or handle client messages if needed
            await websocket.send_text(f"Message received: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000)