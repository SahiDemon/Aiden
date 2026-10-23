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

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.utils.config import get_settings
from src.utils.logger import get_logger
from src.database.neon_client import get_db_client, close_db_client
from src.database.redis_client import get_redis_client, close_redis_client
from src.ai.groq_client import get_groq_client, close_groq_client
from src.ai.gemini_client import get_gemini_client, close_gemini_client
from src.ai.ollama_client import close_ollama_client
from src.smart_home.esp32_client import get_esp32_client, close_esp32_client
from src.services.settings_service import (
    get_provider_models,
    get_settings_payload,
    load_settings_overrides,
    save_settings_payload,
)
from src.core.runtime_refresh import refresh_runtime_components

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
    source: str = "local"
    client_message_id: Optional[str] = None

class CommandRequest(BaseModel):
    command_type: str
    params: Dict[str, Any]

class ConfigUpdateRequest(BaseModel):
    settings: Dict[str, Any]


class SettingsUpdateRequest(BaseModel):
    settings: Dict[str, Any]

class ESP32ControlRequest(BaseModel):
    control_id: Optional[str] = None
    target: Optional[str] = None
    action: Optional[str] = None

class TimerCreateRequest(BaseModel):
    action: str  # shutdown, hibernate, restart, sleep, lock
    duration_seconds: int
    user_id: str = "default"

class TimerCancelRequest(BaseModel):
    timer_id: Optional[str] = None
    action: Optional[str] = None
    user_id: str = "default"

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

        logger.info("Loading persisted settings overrides...")
        await load_settings_overrides()
        
        settings = get_settings()
        if settings.app.llm_provider == "groq":
            logger.info("Initializing Groq chat client...")
            await get_groq_client()
        elif settings.app.llm_provider == "gemini":
            logger.info("Initializing Gemini chat client...")
            await get_gemini_client()
        else:
            logger.info("Using lazy AI client initialization for provider: %s", settings.app.llm_provider)
        
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
        await close_gemini_client()
        await close_groq_client()
        await close_ollama_client()
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
    """Comprehensive health check endpoint"""
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
    except Exception:
        pass
    
    try:
        redis = await get_redis_client()
        services_health["redis"] = True
    except Exception:
        pass
    
    try:
        groq = await get_groq_client()
        services_health["ai"] = True
    except Exception:
        pass
    
    try:
        esp32 = await get_esp32_client()
        services_health["esp32"] = settings.esp32.enabled
    except Exception:
        pass
    
    # Determine overall status
    all_healthy = all(services_health.values())
    status = "healthy" if all_healthy else "degraded"
    
    return {
        "status": status,
        "app": "Aiden AI Assistant",
        "version": "2.0.0",
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
        from src.core.assistant import get_assistant
        assistant = await get_assistant()
        source = "web_text" if request.source == "web" and request.input_type == "text" else request.source
        options = {"client_message_id": request.client_message_id} if request.client_message_id else {}
        response_text = await assistant.handle_text_message(request.message, source=source, **options)
        return {
            "success": True,
            "message": "Message processed",
            "input": request.message,
            "response": response_text
        }
    except Exception as e:
        logger.error(f"Error processing message: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/conversation/new")
async def new_conversation():
    """Start a fresh dashboard conversation without activating the PC microphone."""
    from src.core.assistant import get_assistant
    assistant = await get_assistant()
    await assistant.context_manager.end_conversation()
    conversation_id = await assistant.context_manager.start_conversation(mode="text")
    return {"success": True, "conversation_id": conversation_id}


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
        
        # System stats (interval=None prevents blocking the async event loop)
        cpu_percent = psutil.cpu_percent(interval=None)
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
    """Compatibility wrapper for legacy dashboard clients."""
    try:
        settings_payload = await get_settings_payload()
        return {"success": True, "config": settings_payload}
    except Exception as e:
        logger.error(f"Error getting config: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/v1/config")
async def update_config(request: ConfigUpdateRequest):
    """Compatibility wrapper for legacy dashboard clients."""
    try:
        settings_payload = await save_settings_payload(request.settings)
        await refresh_runtime_components()
        return {
            "success": True,
            "message": "Settings updated",
            "config": settings_payload,
        }
    except Exception as e:
        logger.error(f"Error updating config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _get_esp32_runtime_payload(esp32) -> Dict[str, Any]:
    connected = await esp32.check_connection()
    device = await esp32.get_device_snapshot() if connected else {
        "device_name": "ESP32 Device",
        "ip_address": esp32.ip_address,
        "controls": [],
        "summary": {"state": "unknown", "speed": None, "timer": None, "mode": None, "osc": None},
        "raw_state": {},
        "raw_config": {},
    }
    return {
        "success": True,
        "connected": connected,
        "ip_address": esp32.ip_address,
        "device": device,
        "status": device.get("summary", {}),
    }

@app.get("/api/v1/esp32/status")
async def get_esp32_status():
    """Get ESP32 device status."""
    try:
        esp32 = await get_esp32_client()
        
        if not esp32.enabled:
            return {
                "success": False,
                "error": "ESP32 is disabled in configuration"
            }
        
        payload = await _get_esp32_runtime_payload(esp32)
        return payload
    except Exception as e:
        logger.error(f"Error getting ESP32 status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/esp32/device")
async def get_esp32_device():
    """Get the canonical normalized ESP32 runtime payload."""
    try:
        esp32 = await get_esp32_client()

        if not esp32.enabled:
            return {
                "success": False,
                "error": "ESP32 is disabled in configuration",
            }

        return await _get_esp32_runtime_payload(esp32)
    except Exception as e:
        logger.error(f"Error getting ESP32 device payload: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/esp32/control")
async def control_esp32(request: ESP32ControlRequest):
    """Control ESP32 device using exact targets or relative actions."""
    try:
        esp32 = await get_esp32_client()
        
        if not esp32.enabled:
            raise HTTPException(status_code=400, detail="ESP32 is disabled")

        legacy_action = request.action if not request.control_id else None
        result = await esp32.execute_control_request(
            control_id=request.control_id,
            target=request.target,
            action=request.action if request.control_id else None,
            legacy_action=legacy_action,
        )

        if not result.get("success"):
            detail = result.get("error") or "Failed to control ESP32 device"
            raise HTTPException(status_code=400, detail=detail)

        payload = await _get_esp32_runtime_payload(esp32)
        await manager.broadcast({
            "type": "esp32_update",
            "data": {
                "control_id": result.get("control_id") or request.control_id,
                "target": result.get("target") or request.target,
                "action": request.action,
                "message": result.get("message"),
                "device": payload.get("device"),
                "connected": payload.get("connected"),
            },
            "timestamp": datetime.now().isoformat()
        })

        return {
            "success": True,
            "message": result.get("message"),
            "device": payload.get("device"),
            "connected": payload.get("connected"),
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
    """Get canonical dashboard settings payload."""
    try:
        return {"success": True, "settings": await get_settings_payload()}
    except Exception as e:
        logger.error(f"Error getting settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/v1/settings")
async def update_settings_endpoint(request: SettingsUpdateRequest):
    """Persist canonical dashboard settings payload and refresh runtime state."""
    try:
        settings_payload = await save_settings_payload(request.settings)
        await refresh_runtime_components()
        return {
            "success": True,
            "message": "Settings updated",
            "settings": settings_payload,
            "restart_required": False,
        }
    except Exception as e:
        logger.error(f"Error updating settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/settings/providers/models")
async def get_provider_models_endpoint(provider: str = Query(...)):
    """Get provider model options or discovered models."""
    try:
        return {"success": True, **(await get_provider_models(provider))}
    except Exception as e:
        logger.error(f"Error getting provider models: {e}")
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
        messages = await db.get_conversation_messages(conversation_id)
        return {
            "success": True,
            "conversation": conversation.to_dict(),
            "messages": [message.to_dict() for message in messages],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting conversation: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/conversations/{conversation_id}/resume")
async def resume_conversation(conversation_id: str):
    """Restore saved chat context before the dashboard sends a follow-up."""
    db = await get_db_client()
    conversation = await db.get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    from src.core.assistant import get_assistant
    assistant = await get_assistant()
    manager = assistant.context_manager
    context = await manager.get_context(conversation_id)
    messages = await db.get_conversation_messages(conversation_id)
    context["conversation_id"] = conversation_id
    context["history"] = [{"role": message.role, "content": message.content} for message in messages[-50:]]
    redis = await get_redis_client()
    await redis.save_context(conversation_id, context)
    manager.current_conversation_id = conversation_id
    return {"success": True, "messages": [message.to_dict() for message in messages]}


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
                _voice_activation_callback(from_hotkey=True, source="web")
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
        
        # Get fast SQL counts
        total_conversations = await db.count_conversations()
        total_commands = await db.count_commands()
        
        return {
            "success": True,
            "stats": {
                "total_conversations": total_conversations,
                "total_commands": total_commands,
                "uptime": "N/A",
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

# ===== Timer Endpoints =====

@app.post("/api/v1/timers")
async def create_timer(request: TimerCreateRequest):
    """Create a new system timer"""
    try:
        # Import here to avoid circular imports
        from src.execution.timer_scheduler import get_timer_scheduler
        
        timer_scheduler = await get_timer_scheduler()
        
        # Validate action
        valid_actions = ["shutdown", "restart", "sleep", "hibernate", "lock"]
        if request.action not in valid_actions:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid action. Valid actions: {', '.join(valid_actions)}"
            )
        
        # Validate duration (between 1 second and 24 hours)
        if request.duration_seconds < 1 or request.duration_seconds > 86400:
            raise HTTPException(
                status_code=400,
                detail="Duration must be between 1 second and 24 hours"
            )
        
        timer = await timer_scheduler.create_timer(
            action=request.action,
            duration_seconds=request.duration_seconds,
            user_id=request.user_id
        )
        
        if timer:
            return {
                "success": True,
                "message": f"Timer created: {request.action} in {request.duration_seconds} seconds",
                "timer": timer.to_dict()
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to create timer")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating timer: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/timers")
async def get_active_timers(user_id: str = "default"):
    """Get all active timers for a user"""
    try:
        from src.execution.timer_scheduler import get_timer_scheduler
        
        timer_scheduler = await get_timer_scheduler()
        timers = await timer_scheduler.get_active_timers(user_id)
        
        return {
            "success": True,
            "timers": timers
        }
        
    except Exception as e:
        logger.error(f"Error getting timers: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/v1/timers/{timer_id}")
async def cancel_timer(timer_id: str):
    """Cancel a specific timer"""
    try:
        from src.execution.timer_scheduler import get_timer_scheduler
        
        timer_scheduler = await get_timer_scheduler()
        success = await timer_scheduler.cancel_timer(timer_id)
        
        if success:
            return {
                "success": True,
                "message": "Timer cancelled"
            }
        else:
            raise HTTPException(status_code=404, detail="Timer not found or already completed")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling timer: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/timers/cancel")
async def cancel_timers(request: TimerCancelRequest):
    """Cancel timers by ID or action"""
    try:
        from src.execution.timer_scheduler import get_timer_scheduler
        
        timer_scheduler = await get_timer_scheduler()
        
        if request.timer_id:
            # Cancel specific timer
            success = await timer_scheduler.cancel_timer(request.timer_id)
            return {
                "success": success,
                "message": "Timer cancelled" if success else "Timer not found"
            }
        elif request.action:
            # Cancel all timers for action
            count = await timer_scheduler.cancel_timers_by_action(request.action, request.user_id)
            return {
                "success": True,
                "message": f"Cancelled {count} {request.action} timers",
                "cancelled_count": count
            }
        else:
            raise HTTPException(status_code=400, detail="Either timer_id or action must be provided")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling timers: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ===== WebSocket Endpoint =====

@app.websocket("/api/v1/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time communication
    Sends status updates, voice status, command execution, etc.
    """
    client_id = await manager.connect(websocket)
    preview_started = False
    last_preview = 0.0
    
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
                    
                    case "voice_transcript":
                        import time
                        payload = data.get("data", {})
                        if not isinstance(payload, dict):
                            continue
                        text = payload.get("text", "")
                        stage = payload.get("stage", "partial")
                        if not isinstance(text, str) or len(text) > 2000 or stage not in ("start", "partial", "final", "cancel"):
                            continue
                        now = time.monotonic()
                        if stage == "partial" and now - last_preview < .08:
                            continue
                        if stage == "partial":
                            last_preview = now
                        if stage == "start":
                            preview_started = True
                            await broadcast_update("voice_activity", {"status": "listening", "speaking": False, "active": True, "source": "web"})
                        elif not preview_started:
                            continue
                        await broadcast_update("voice_transcript", {"text": text, "source": "web"})
                        if stage in ("final", "cancel"):
                            preview_started = False
                            await broadcast_update("voice_activity", {"status": "processing" if stage == "final" else "idle", "active": stage == "final", "speaking": False, "source": "web"})

                    case "tts_playback":
                        from src.speech.playback_events import playback_event
                        event = playback_event(client_id, data.get("data", {}))
                        if event:
                            await broadcast_update("tts_progress", event)

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
        from src.speech.playback_events import disconnect_playback
        disconnect_playback(client_id)
        if preview_started:
            await broadcast_update("voice_activity", {"status": "idle", "speaking": False, "active": False, "source": "web"})
        # Always disconnect when exiting
        await manager.disconnect(client_id)
        logger.info(f"WebSocket client {client_id} cleanup complete.")

# ===== Static Files (Dashboard) =====

# Serve React dashboard (if built)
try:
    from src.utils.paths import resource_path

    dashboard_build = resource_path("dashboard", "build")
    app.mount("/static", StaticFiles(directory=str(dashboard_build / "static")), name="static")
    
    @app.get("/")
    async def serve_dashboard_root():
        """Serve React dashboard at root"""
        return FileResponse(str(dashboard_build / "index.html"))
    
    # Catch-all route for React Router (must be last)
    @app.get("/{full_path:path}")
    async def serve_dashboard_catchall(full_path: str):
        """Catch-all for React Router - serve index.html for all non-API routes"""
        # Don't catch API routes
        if full_path.startswith("api/"):
            return {"error": "Not found"}
        return FileResponse(str(dashboard_build / "index.html"))
except Exception:
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
    logger.debug(f"Broadcasting to {len(manager.active_connections)} clients: type={update_type}")
    logger.debug(f"Broadcast data: {data}")
    await manager.broadcast(message)

# ===== Server Lifecycle Functions =====

# Global server instance and configuration
_server = None
_server_config = None

async def start_api_server():
    """Start the FastAPI server in background"""
    global _server, _server_config
    import uvicorn
    
    settings = get_settings()
    
    # Check for SSL certificates for HTTPS support
    import os
    ssl_keyfile = "key.pem" if os.path.exists("key.pem") else None
    ssl_certfile = "cert.pem" if os.path.exists("cert.pem") else None
    
    _server_config = uvicorn.Config(
        app,
        host=settings.api.host,
        port=settings.api.port,
        log_level="info",
        access_log=False,
        loop="asyncio",
        ssl_keyfile=ssl_keyfile,
        ssl_certfile=ssl_certfile
    )
    
    _server = uvicorn.Server(_server_config)
    asyncio.create_task(_server.serve())
    
    logger.info(f"API server starting on {settings.api.host}:{settings.api.port}")
    
    # Give server time to start
    await asyncio.sleep(2)

async def stop_api_server():
    """Stop the API server gracefully"""
    global _server
    
    if _server:
        logger.info("Stopping API server...")
        _server.should_exit = True
        # Give it time to shutdown gracefully
        await asyncio.sleep(1)
        _server = None
        logger.info("API server stopped")
    else:
        logger.warning("No server instance to stop")

# Export for use in other modules
__all__ = ["app", "broadcast_update", "manager", "start_api_server", "stop_api_server"]
