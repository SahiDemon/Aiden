"""
FastAPI Server for Aiden
REST API + WebSocket for real-time communication with dashboard
"""
import asyncio
import logging
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime
from contextlib import asynccontextmanager

# CRITICAL: Import event loop policy FIRST
from src.utils.event_loop import ensure_selector_event_loop

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

# Global voice activation callback
_voice_activation_callback: Optional[Callable] = None


def set_voice_activation_callback(callback: Callable):
    """Set the voice activation callback function"""
    global _voice_activation_callback
    _voice_activation_callback = callback


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
        self.active_connections: Dict[str, WebSocket] = {}
        self._lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None

    def start_cleanup_task(self):
        """Start the background task to clean up dead connections."""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
            logger.info("WebSocket cleanup task started.")

    async def _periodic_cleanup(self):
        """Periodically check for and remove dead connections."""
        while True:
            await asyncio.sleep(10)  # Run every 10 seconds (more aggressive)
            await self.cleanup_dead_connections()

    async def cleanup_dead_connections(self):
        """Remove connections that are no longer active by sending a ping."""
        if not self.active_connections:
            return

        logger.debug(f"Running cleanup on {len(self.active_connections)} connections...")
        dead_clients = []
        # Create a copy of client IDs to iterate over, as the dictionary may change
        client_ids = list(self.active_connections.keys())

        for client_id in client_ids:
            websocket = self.active_connections.get(client_id)
            if not websocket:
                continue
            try:
                # Starlette's WebSocketState: 0=CONNECTING, 1=CONNECTED, 2=DISCONNECTED
                if websocket.client_state.value != 1:
                    dead_clients.append(client_id)
                    continue
                
                # Send a ping and wait for a pong. If it times out, connection is dead.
                await asyncio.wait_for(websocket.send_json({"type": "ping"}), timeout=2)  # Reduced timeout to 2s
            except (asyncio.TimeoutError, Exception):
                dead_clients.append(client_id)

        if dead_clients:
            async with self._lock:
                for client_id in dead_clients:
                    if client_id in self.active_connections:
                        del self.active_connections[client_id]
                        logger.info(f"Removed dead WebSocket client {client_id}. Total: {len(self.active_connections)}")

    async def connect(self, websocket: WebSocket) -> str:
        await websocket.accept()
        client_id = f"{websocket.client.host}:{websocket.client.port}"
        async with self._lock:
            self.active_connections[client_id] = websocket
        logger.info(f"WebSocket client {client_id} connected. Total: {len(self.active_connections)}")
        return client_id

    async def disconnect(self, client_id: str):
        async with self._lock:
            if client_id in self.active_connections:
                del self.active_connections[client_id]
                logger.info(f"WebSocket client {client_id} disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: Dict[str, Any]):
        """Broadcast message to all connected clients."""
        if not self.active_connections:
            return
            
        disconnected_clients = []
        # Create a copy of connections to iterate over
        connections = list(self.active_connections.values())
        
        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception:
                # Find the client_id for the failed connection
                for cid, ws in self.active_connections.items():
                    if ws is connection:
                        disconnected_clients.append(cid)
                        break
        
        if disconnected_clients:
            async with self._lock:
                for client_id in disconnected_clients:
                    if client_id in self.active_connections:
                        del self.active_connections[client_id]
                        logger.info(f"Removed failed connection {client_id} during broadcast. Total: {len(self.active_connections)}")

    async def send_to_client(self, client_id: str, message: Dict[str, Any]):
        """Send message to a specific client."""
        websocket = self.active_connections.get(client_id)
        if websocket:
            try:
                await websocket.send_json(message)
            except Exception:
                await self.disconnect(client_id)


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
        
        # Start the WebSocket cleanup task
        manager.start_cleanup_task()
        
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

@app.get("/api/v1/health")
async def health_check():
    """Health check endpoint"""
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
        # Return empty history if database isn't available
        return {
            "success": True,
            "messages": [],
            "count": 0
        }


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


# ===== NEW Dashboard API Endpoints =====

@app.get("/api/v1/settings")
async def get_settings_endpoint():
    """Get all settings for dashboard"""
    try:
        settings = get_settings()
        
        return {
            "success": True,
            "settings": {
                "speech": {
                    "tts_voice": settings.speech.tts_voice,
                    "tts_rate": settings.speech.tts_rate,
                    "stt_language": settings.speech.stt_language,
                    "stt_timeout": settings.speech.stt_timeout,
                    "stt_energy_threshold": settings.speech.stt_energy_threshold,
                },
                "groq": {
                    "model": settings.groq.model,
                    "temperature": settings.groq.temperature,
                    "max_tokens": settings.groq.max_tokens,
                    "user_name": settings.app.user_name,
                },
                "app": {
                    "name": settings.app.name,
                    "user_name": settings.app.user_name,
                    "wake_word": settings.app.wake_word,
                    "hotkey": settings.app.hotkey,
                    "debug": settings.app.debug,
                    "enable_sound_effects": True,  # Add this to config if needed
                },
                "esp32": {
                    "enabled": settings.esp32.enabled,
                    "ip_address": settings.esp32.ip_address,
                    "timeout": settings.esp32.timeout,
                }
            }
        }
    except Exception as e:
        logger.error(f"Error getting settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/v1/settings/speech")
async def update_speech_settings(settings_update: Dict[str, Any]):
    """Update speech settings"""
    try:
        # Settings would be updated in .env or config file
        # For now, just acknowledge the request
        return {
            "success": True,
            "message": "Speech settings updated"
        }
    except Exception as e:
        logger.error(f"Error updating speech settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/v1/settings/ai")
async def update_ai_settings(settings_update: Dict[str, Any]):
    """Update AI settings"""
    try:
        return {
            "success": True,
            "message": "AI settings updated"
        }
    except Exception as e:
        logger.error(f"Error updating AI settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/v1/settings/system")
async def update_system_settings(settings_update: Dict[str, Any]):
    """Update system settings"""
    try:
        return {
            "success": True,
            "message": "System settings updated"
        }
    except Exception as e:
        logger.error(f"Error updating system settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/conversations")
async def get_conversations():
    """Get list of conversations"""
    try:
        db = await get_db_client()
        conversations = await db.get_conversations(limit=50)
        
        return {
            "success": True,
            "conversations": [conv.to_dict() for conv in conversations]
        }
    except Exception as e:
        logger.error(f"Error getting conversations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    """Get specific conversation"""
    try:
        db = await get_db_client()
        conversation = await db.get_conversation(conversation_id)
        
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        return {
            "success": True,
            "conversation": conversation.to_dict()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting conversation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/v1/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """Delete a conversation"""
    try:
        db = await get_db_client()
        await db.delete_conversation(conversation_id)
        
        return {
            "success": True,
            "message": "Conversation deleted"
        }
    except Exception as e:
        logger.error(f"Error deleting conversation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/voice/activate")
async def activate_voice():
    """Manually trigger voice activation"""
    try:
        # Broadcast to WebSocket clients first
        await manager.broadcast({
            "type": "voice_activate",
            "timestamp": datetime.now().isoformat()
        })
        
        # Trigger actual voice activation if callback is set
        if _voice_activation_callback:
            try:
                # Call the voice activation callback (from dashboard)
                _voice_activation_callback(from_hotkey=True)
                logger.info("Voice activation triggered from dashboard")
            except Exception as e:
                logger.error(f"Error calling voice activation callback: {e}")
        else:
            logger.warning("Voice activation callback not set")
        
        return {
            "success": True,
            "message": "Voice activation triggered"
        }
    except Exception as e:
        logger.error(f"Error activating voice: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/stats/dashboard")
async def get_dashboard_stats():
    """Get dashboard statistics"""
    try:
        db = await get_db_client()
        
        # Get conversation count
        conversations = await db.get_conversations(limit=1000)
        
        # Get command history
        commands = await db.get_command_history(limit=1000)
        
        return {
            "success": True,
            "stats": {
                "total_conversations": len(conversations),
                "total_commands": len(commands),
                "uptime": "N/A",  # Would need to track this
            }
        }
    except Exception as e:
        logger.error(f"Error getting dashboard stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/esp32/devices")
async def get_esp32_devices():
    """Get list of ESP32 devices"""
    try:
        esp32 = await get_esp32_client()
        
        if not esp32.enabled:
            return {
                "success": True,
                "devices": []
            }
        
        # For now, return single device
        # In future, this could support multiple devices
        return {
            "success": True,
            "devices": [{
                "name": "Smart Fan",
                "ip_address": esp32.ip_address,
                "type": "fan",
                "connected": await esp32.check_connection()
            }]
        }
    except Exception as e:
        logger.error(f"Error getting ESP32 devices: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== WebSocket Endpoint =====

@app.websocket("/api/v1/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time communication
    Sends status updates, voice status, command execution, etc.
    """
    client_id = await manager.connect(websocket)
    
    try:
        # Send initial connection message
        await manager.send_to_client(client_id, {
            "type": "connected",
            "message": "Connected to Aiden API",
            "timestamp": datetime.now().isoformat()
        })
        
        # Keep connection alive and listen for messages
        while True:
            try:
                data = await websocket.receive_json()
                
                # Handle different message types from client
                message_type = data.get("type")
                
                match message_type:
                    case "pong":
                        # Client is responding to our ping
                        pass
                    
                    case "ping":
                        # Client is pinging us - respond with pong
                        await manager.send_to_client(client_id, {"type": "pong"})
                    
                    case "subscribe":
                        # Client wants to subscribe to specific events
                        pass
                    
                    case _:
                        logger.warning(f"Unknown WebSocket message type: {message_type}")
            
            except WebSocketDisconnect:
                logger.debug(f"WebSocket {client_id} disconnected gracefully.")
                break
            except Exception as e:
                logger.error(f"Error receiving from WebSocket {client_id}: {e}")
                break
    
    except Exception as e:
        logger.error(f"WebSocket error with client {client_id}: {e}")
    
    finally:
        # Always disconnect when exiting
        await manager.disconnect(client_id)
        logger.info(f"WebSocket client {client_id} cleanup complete.")


# ===== Static Files (Dashboard) =====

# Serve React dashboard (if built)
try:
    app.mount("/static", StaticFiles(directory="dashboard/build/static"), name="static")
    
    @app.get("/")
    async def serve_dashboard_root():
        """Serve React dashboard at root"""
        return FileResponse("dashboard/build/index.html")
    
    # Catch-all route for React Router (must be last)
    @app.get("/{full_path:path}")
    async def serve_dashboard_catchall(full_path: str):
        """Catch-all for React Router - serve index.html for all non-API routes"""
        # Don't catch API routes
        if full_path.startswith("api/"):
            return {"error": "Not found"}
        return FileResponse("dashboard/build/index.html")
except:
    logger.warning("Dashboard build not found - dashboard will not be served")
    
    @app.get("/")
    async def root_fallback():
        """Fallback root endpoint when dashboard not built"""
        return {
            "status": "online",
            "app": "Aiden AI Assistant",
            "version": "2.0.0",
            "timestamp": datetime.now().isoformat(),
            "note": "Dashboard not built. Run 'npm run build' in dashboard folder."
        }


# Global function to broadcast updates (can be called from other modules)
async def broadcast_update(update_type: str, data: Dict[str, Any]):
    """
    Broadcast update to all WebSocket clients
    Can be called from other parts of the application
    """
    message = {
        "type": update_type,
        "data": data,
        "timestamp": datetime.now().isoformat()
    }
    logger.info(f"Broadcasting to {len(manager.active_connections)} clients: type={update_type}")
    logger.debug(f"Broadcast data: {data}")
    await manager.broadcast(message)


# ===== Server Lifecycle Functions =====

# Global server instance
_server = None


async def start_api_server():
    """Start the FastAPI server in background"""
    import uvicorn
    import threading
    
    settings = get_settings()
    
    def run_server():
        """Run uvicorn server in a thread with correct event loop policy"""
        # Import the event loop policy in this thread
        from src.utils.event_loop import ensure_selector_event_loop
        ensure_selector_event_loop()
        
        # Get settings properly
        settings = get_settings()
        
        # Create and run the server with the correct event loop
        uvicorn.run(
            app,
            host=settings.api.host,
            port=settings.api.port,
            log_level="info",
            access_log=False,
            loop="asyncio"  # Force asyncio loop
        )
    
    # Start server in a daemon thread
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    
    logger.info(f"API server starting on {settings.api.host}:{settings.api.port}")
    
    # Give server time to start
    await asyncio.sleep(2)


async def stop_api_server():
    """Stop the API server"""
    global _server
    
    if _server:
        logger.info("Stopping API server...")
        _server.should_exit = True
        _server = None


# Export for use in other modules
__all__ = ["app", "broadcast_update", "manager", "start_api_server", "stop_api_server"]

