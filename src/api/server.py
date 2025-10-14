"""
FastAPI Server for Aiden
REST API + WebSocket for real-time communication with dashboard
"""
import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.utils.config import get_settings
from src.utils.logger import get_logger
from src.database.neon_client import get_db_client, close_db_client
from src.database.redis_client import get_redis_client, close_redis_client
from src.ai.groq_client import get_groq_client, close_groq_client
from src.smart_home.esp32_client import get_esp32_client, close_esp32_client

logger = get_logger(__name__)


# Pydantic models for requests/responses
class MessageRequest(BaseModel):
    message: str
    input_type: str = "text"


class CommandRequest(BaseModel):
    command_type: str
    params: Dict[str, Any]


class ConfigUpdateRequest(BaseModel):
    settings: Dict[str, Any]


class ESP32ControlRequest(BaseModel):
    action: str  # turn_on, turn_off, toggle, change_mode


# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.info(f"WebSocket client disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: Dict[str, Any]):
        """Broadcast message to all connected clients"""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting to client: {e}")
                disconnected.append(connection)
        
        # Remove disconnected clients
        for conn in disconnected:
            if conn in self.active_connections:
                self.active_connections.remove(conn)

    async def send_to_client(self, websocket: WebSocket, message: Dict[str, Any]):
        """Send message to specific client"""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Error sending to client: {e}")


manager = ConnectionManager()


# Lifespan context manager for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events"""
    logger.info("Starting Aiden API server...")
    
    # Initialize services
    try:
        logger.info("Initializing Neon DB client...")
        await get_db_client()
        
        logger.info("Initializing Redis client...")
        await get_redis_client()
        
        logger.info("Initializing Groq AI client...")
        await get_groq_client()
        
        logger.info("Initializing ESP32 client...")
        esp32_client = await get_esp32_client()
        
        # Connect ESP32 to command executor
        from src.execution.command_executor import get_command_executor
        executor = get_command_executor()
        executor.set_esp32_client(esp32_client)
        logger.info("ESP32 client connected to command executor")
        
        logger.info("All services initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing services: {e}")
        import traceback
        logger.error(traceback.format_exc())
    
    yield
    
    # Cleanup on shutdown
    logger.info("Shutting down Aiden API server...")
    try:
        await close_db_client()
        await close_redis_client()
        await close_groq_client()
        await close_esp32_client()
        logger.info("All services closed successfully")
    except Exception as e:
        logger.error(f"Error closing services: {e}")


# Create FastAPI app
app = FastAPI(
    title="Aiden AI Assistant API",
    description="API for Aiden voice assistant with context-aware conversations",
    version="2.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===== REST API Endpoints =====

@app.get("/")
async def root():
    """Root endpoint - health check"""
    return {
        "status": "online",
        "app": "Aiden AI Assistant",
        "version": "2.0.0",
        "timestamp": datetime.now().isoformat()
    }


@app.get("/api/v1/health")
async def health_check():
    """Health check endpoint"""
    settings = get_settings()
    
    # Check service health
    services_health = {
        "database": False,
        "redis": False,
        "ai": False,
        "esp32": False
    }
    
    try:
        db = await get_db_client()
        services_health["database"] = True
    except:
        pass
    
    try:
        redis = await get_redis_client()
        services_health["redis"] = True
    except:
        pass
    
    try:
        groq = await get_groq_client()
        services_health["ai"] = True
    except:
        pass
    
    try:
        esp32 = await get_esp32_client()
        services_health["esp32"] = settings.esp32.enabled
    except:
        pass
    
    return {
        "status": "healthy" if all(services_health.values()) else "degraded",
        "services": services_health,
        "timestamp": datetime.now().isoformat()
    }


@app.post("/api/v1/conversation/message")
async def send_message(request: MessageRequest):
    """
    Process a user message (text or voice)
    This will be the main entry point for command processing
    """
    try:
        # This will be implemented with the main orchestrator
        # For now, return a placeholder
        return {
            "success": True,
            "message": "Message received",
            "input": request.message,
            "response": "Processing not yet implemented - orchestrator needed"
        }
    except Exception as e:
        logger.error(f"Error processing message: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/conversation/history")
async def get_conversation_history(limit: int = 50):
    """Get conversation history from database"""
    try:
        db = await get_db_client()
        messages = await db.get_recent_messages(limit=limit)
        
        return {
            "success": True,
            "messages": [msg.to_dict() for msg in messages],
            "count": len(messages)
        }
    except Exception as e:
        logger.error(f"Error getting conversation history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/system/status")
async def get_system_status():
    """Get system status including stats"""
    try:
        import psutil
        
        # System stats
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        
        # Redis stats
        redis = await get_redis_client()
        cache_stats = await redis.get_stats()
        
        # Database stats
        db = await get_db_client()
        # Get conversation count (simplified)
        
        return {
            "success": True,
            "system": {
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "memory_used_gb": memory.used / 1024 / 1024 / 1024,
                "memory_total_gb": memory.total / 1024 / 1024 / 1024
            },
            "cache": cache_stats,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting system status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/config")
async def get_config():
    """Get current configuration"""
    try:
        settings = get_settings()
        
        # Return safe config (no secrets)
        return {
            "success": True,
            "config": {
                "app": {
                    "name": settings.app.name,
                    "user_name": settings.app.user_name,
                    "wake_word": settings.app.wake_word
                },
                "esp32": {
                    "enabled": settings.esp32.enabled,
                    "ip_address": settings.esp32.ip_address
                },
                "speech": {
                    "tts_voice": settings.speech.tts_voice,
                    "tts_rate": settings.speech.tts_rate,
                    "stt_language": settings.speech.stt_language
                },
                "cache": {
                    "enabled": settings.cache.enable_caching
                }
            }
        }
    except Exception as e:
        logger.error(f"Error getting config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/v1/config")
async def update_config(request: ConfigUpdateRequest):
    """Update configuration"""
    try:
        # This will update .env or database settings
        # For now, return placeholder
        return {
            "success": True,
            "message": "Config update not yet fully implemented"
        }
    except Exception as e:
        logger.error(f"Error updating config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/esp32/status")
async def get_esp32_status():
    """Get ESP32 device status"""
    try:
        esp32 = await get_esp32_client()
        
        if not esp32.enabled:
            return {
                "success": False,
                "error": "ESP32 is disabled in configuration"
            }
        
        status = await esp32.get_status()
        connected = await esp32.check_connection()
        
        return {
            "success": True,
            "connected": connected,
            "status": status,
            "ip_address": esp32.ip_address
        }
    except Exception as e:
        logger.error(f"Error getting ESP32 status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/esp32/control")
async def control_esp32(request: ESP32ControlRequest):
    """Control ESP32 device"""
    try:
        esp32 = await get_esp32_client()
        
        if not esp32.enabled:
            raise HTTPException(status_code=400, detail="ESP32 is disabled")
        
        result = False
        message = ""
        
        match request.action:
            case "turn_on":
                result = await esp32.turn_on()
                message = "Fan turned on"
            case "turn_off":
                result = await esp32.turn_off()
                message = "Fan turned off"
            case "toggle":
                result = await esp32.toggle()
                message = "Fan toggled"
            case "change_mode":
                result = await esp32.change_mode()
                message = "Fan mode changed"
            case _:
                raise HTTPException(status_code=400, detail="Invalid action")
        
        # Broadcast to WebSocket clients
        await manager.broadcast({
            "type": "esp32_update",
            "action": request.action,
            "success": result,
            "message": message,
            "timestamp": datetime.now().isoformat()
        })
        
        return {
            "success": result,
            "message": message
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error controlling ESP32: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/command/history")
async def get_command_history(limit: int = 100):
    """Get command execution history"""
    try:
        db = await get_db_client()
        commands = await db.get_command_history(limit=limit)
        
        return {
            "success": True,
            "commands": [cmd.to_dict() for cmd in commands],
            "count": len(commands)
        }
    except Exception as e:
        logger.error(f"Error getting command history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== WebSocket Endpoint =====

@app.websocket("/api/v1/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time communication
    Sends status updates, voice status, command execution, etc.
    """
    await manager.connect(websocket)
    
    try:
        # Send initial connection message
        await manager.send_to_client(websocket, {
            "type": "connected",
            "message": "Connected to Aiden API",
            "timestamp": datetime.now().isoformat()
        })
        
        # Keep connection alive and listen for messages
        while True:
            data = await websocket.receive_json()
            
            # Handle different message types from client
            message_type = data.get("type")
            
            match message_type:
                case "ping":
                    await manager.send_to_client(websocket, {
                        "type": "pong",
                        "timestamp": datetime.now().isoformat()
                    })
                
                case "subscribe":
                    # Client wants to subscribe to specific events
                    pass
                
                case _:
                    logger.warning(f"Unknown WebSocket message type: {message_type}")
    
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info("WebSocket client disconnected")
    
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


# ===== Static Files (Dashboard) =====

# Serve React dashboard (if built)
try:
    app.mount("/static", StaticFiles(directory="dashboard/build/static"), name="static")
    
    @app.get("/dashboard")
    async def serve_dashboard():
        """Serve React dashboard"""
        return FileResponse("dashboard/build/index.html")
except:
    logger.warning("Dashboard build not found - dashboard will not be served")


# Global function to broadcast updates (can be called from other modules)
async def broadcast_update(update_type: str, data: Dict[str, Any]):
    """
    Broadcast update to all WebSocket clients
    Can be called from other parts of the application
    """
    await manager.broadcast({
        "type": update_type,
        "data": data,
        "timestamp": datetime.now().isoformat()
    })


# ===== Server Lifecycle Functions =====

# Global server instance
_server: Optional["uvicorn.Server"] = None


async def start_api_server():
    """Start the FastAPI server"""
    import uvicorn
    
    global _server
    
    settings = get_settings()
    
    config = uvicorn.Config(
        app=app,
        host=settings.api.host,
        port=settings.api.port,
        log_level="warning",  # Reduce noise
        access_log=False
    )
    
    _server = uvicorn.Server(config)
    
    logger.info(f"Starting API server on {settings.api.host}:{settings.api.port}")
    await _server.serve()


async def stop_api_server():
    """Stop the API server"""
    global _server
    
    if _server:
        logger.info("Stopping API server...")
        _server.should_exit = True
        _server = None


# Export for use in other modules
__all__ = ["app", "broadcast_update", "manager", "start_api_server", "stop_api_server"]

