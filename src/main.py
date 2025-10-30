"""
Aiden AI Assistant - Main Entry Point
Unified application with hidden tray + optional web dashboard
"""
import asyncio
import logging
import os
import signal
import sys
import threading
from typing import Optional
import platform

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# CRITICAL: Import event loop policy FIRST before any other imports
# This sets the correct event loop policy for Windows/psycopg compatibility
from src.utils.event_loop import ensure_selector_event_loop

from src.api.server import start_api_server, stop_api_server
from src.core.assistant import get_assistant
from src.core.hotkey_listener import get_hotkey_listener, HotkeyListener
from src.core.wake_word_manager import get_wake_word_manager
from src.speech.wake_word import get_wake_word_detector
from src.speech.porcupine_wake import get_porcupine_detector
from src.tray.tray_app import run_tray_app
from src.utils.config import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Global state
assistant: Optional[object] = None
wake_word_detector: Optional[object] = None
wake_word_manager: Optional[object] = None
hotkey_listener: Optional[object] = None
toggle_hotkey_listener: Optional[object] = None
api_server_task: Optional[asyncio.Task] = None
shutdown_event = threading.Event()
main_loop: Optional[asyncio.AbstractEventLoop] = None


def handle_activation(from_hotkey: bool = False):
    """Handle voice activation (from wake word or hotkey)"""
    try:
        logger.info(f"[VOICE] Voice activation triggered! (from_hotkey={from_hotkey})")
        
        # CRITICAL: Pause wake word detector so STT can use microphone
        if wake_word_detector:
            wake_word_detector.pause()
        
        # Schedule the async handler in the main event loop from this thread
        global main_loop
        if main_loop is None:
            logger.error("Main event loop not set yet!")
            # Resume wake word detector
            if wake_word_detector and wake_word_manager and wake_word_manager.is_enabled:
                wake_word_detector.resume()
            return
        
        # Run the coroutine in the main loop from this thread
        future = asyncio.run_coroutine_threadsafe(
            assistant.handle_voice_activation(from_hotkey=from_hotkey),
            main_loop
        )
        
        # Wait for completion (longer timeout for auto-listen scenarios)
        try:
            result = future.result(timeout=60)  # 60 second timeout (allows auto-listen)
        except TimeoutError:
            logger.error("Voice activation timed out after 60 seconds")
        except Exception as e:
            logger.error(f"Error in voice activation: {e}", exc_info=True)
        finally:
            # ALWAYS resume wake word detector (only if enabled)
            if wake_word_detector and wake_word_manager and wake_word_manager.is_enabled:
                wake_word_detector.resume()
        
    except Exception as e:
        logger.error(f"Error handling activation: {e}", exc_info=True)
        # Resume wake word detector even on error (only if enabled)
        if wake_word_detector and wake_word_manager and wake_word_manager.is_enabled:
            wake_word_detector.resume()


def handle_toggle_wake_word():
    """Handle toggle wake word hotkey"""
    try:
        logger.info("[TOGGLE] Wake word toggle triggered!")
        
        global main_loop, wake_word_manager
        if main_loop is None:
            logger.error("Main event loop not set yet!")
            return
        
        if wake_word_manager is None:
            logger.error("Wake word manager not initialized!")
            return
        
        # Run the toggle in the main loop from this thread
        future = asyncio.run_coroutine_threadsafe(
            wake_word_manager.toggle(),
            main_loop
        )
        
        # Wait for completion
        try:
            new_state = future.result(timeout=10)
            logger.info(f"[TOGGLE] Wake word is now: {'ENABLED' if new_state else 'DISABLED'}")
        except TimeoutError:
            logger.error("Toggle wake word timed out")
        except Exception as e:
            logger.error(f"Error toggling wake word: {e}", exc_info=True)
        
    except Exception as e:
        logger.error(f"Error handling toggle: {e}", exc_info=True)


async def initialize_services():
    """Initialize all Aiden services"""
    global assistant, wake_word_detector, wake_word_manager, hotkey_listener, toggle_hotkey_listener, api_server_task, main_loop
    
    # Store the main event loop for thread-safe async calls
    main_loop = asyncio.get_event_loop()
    logger.info(f"Main event loop set: {main_loop}")
    
    try:
        logger.info("=" * 70)
        logger.info("AIDEN AI ASSISTANT - STARTING UP")
        logger.info("=" * 70)
        
        settings = get_settings()
        
        # 1. Pre-cache system context (apps & processes) in background
        logger.info("Pre-caching system context (installed apps & processes)...")
        try:
            from src.utils.system_context import get_system_context
            sys_ctx = get_system_context()
            # Run cache in background, don't wait
            asyncio.create_task(sys_ctx.get_installed_apps())
            logger.info("System context caching started in background")
        except Exception as e:
            logger.warning(f"Could not start system context cache: {e}")
        
        # 2. Initialize assistant
        logger.info("Initializing assistant...")
        assistant = await get_assistant()
        
        # 3. Start API server
        logger.info(f"Starting API server on {settings.api.host}:{settings.api.port}...")
        
        # Set voice activation callback for API server
        from src.api.server import set_voice_activation_callback, broadcast_update
        set_voice_activation_callback(handle_activation)
        logger.info("Voice activation callback set for API server")
        
        # Set broadcast callback for voice status updates
        from src.utils.websocket_broadcast import set_broadcast_callback
        set_broadcast_callback(broadcast_update)
        logger.info("WebSocket broadcast callback set")
        
        api_server_task = asyncio.create_task(start_api_server())
        await asyncio.sleep(3)  # Give server time to start (including DB/Redis/Groq init)
        
        # 3. Initialize wake word detector
        logger.info("Initializing wake word detector...")
        
        # Try Porcupine first (if enabled), fallback to Vosk
        if settings.speech.use_porcupine and settings.speech.porcupine_access_key:
            try:
                logger.info("Using Porcupine wake word detector")
                wake_word_detector = get_porcupine_detector(on_wake_word=handle_activation)
                wake_word_detector.start()
                logger.info("✅ Porcupine wake word detector started successfully")
            except Exception as e:
                logger.error(f"Failed to start Porcupine detector: {e}")
                logger.info("⚠️ Falling back to Vosk wake word detector...")
                wake_word_detector = get_wake_word_detector(on_wake_word=handle_activation)
                wake_word_detector.start()
                logger.info("✅ Vosk wake word detector started (fallback)")
        else:
            logger.info("Using Vosk wake word detector (Porcupine disabled or no access key)")
            wake_word_detector = get_wake_word_detector(on_wake_word=handle_activation)
            wake_word_detector.start()
        
        # Give wake word detector a moment to start
        await asyncio.sleep(0.5)
        
        # 3.5. Initialize wake word manager
        logger.info("Initializing wake word manager...")
        wake_word_manager = get_wake_word_manager(wake_word_detector)
        
        # 3.6. Inject wake word manager into command executor for voice control
        from src.execution.command_executor import get_command_executor
        executor = get_command_executor()
        executor.set_wake_word_manager(wake_word_manager)
        logger.info("Wake word manager injected into command executor")
        
        # 4. Initialize hotkey listener
        logger.info("Initializing hotkey listener...")
        hotkey_listener = get_hotkey_listener(on_activation=lambda: handle_activation(from_hotkey=True))
        hotkey_listener.start()
        
        # 4.5. Initialize toggle hotkey listener
        logger.info("Initializing toggle hotkey listener...")
        toggle_hotkey_listener = HotkeyListener(on_activation=handle_toggle_wake_word)
        # Override the hotkey with toggle_hotkey from settings
        toggle_hotkey_listener.settings.app.hotkey = settings.app.toggle_hotkey
        toggle_hotkey_listener.hotkey_combo = toggle_hotkey_listener._parse_hotkey()
        toggle_hotkey_listener.start()
        logger.info(f"✅ Toggle hotkey: {settings.app.toggle_hotkey}")
        
        # 5. Greet user
        await assistant.greet_user()
        
        logger.info("=" * 70)
        logger.info("AIDEN IS READY!")
        logger.info(f"Wake word: '{settings.app.wake_word}'")
        logger.info(f"Hotkey: {settings.app.hotkey}")
        logger.info(f"Toggle hotkey: {settings.app.toggle_hotkey}")
        logger.info(f"Dashboard: http://{settings.api.host}:{settings.api.port}")
        logger.info("=" * 70)
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to initialize services: {e}", exc_info=True)
        return False


async def cleanup():
    """Cleanup all services"""
    global wake_word_detector, hotkey_listener, toggle_hotkey_listener, api_server_task
    
    logger.info("=" * 70)
    logger.info("SHUTTING DOWN AIDEN")
    logger.info("=" * 70)
    
    try:
        # Stop wake word detector
        if wake_word_detector:
            logger.info("Stopping wake word detector...")
            wake_word_detector.stop()
        
        # Stop hotkey listener
        if hotkey_listener:
            logger.info("Stopping hotkey listener...")
            hotkey_listener.stop()
        
        # Stop toggle hotkey listener
        if toggle_hotkey_listener:
            logger.info("Stopping toggle hotkey listener...")
            toggle_hotkey_listener.stop()
        
        # Stop API server
        if api_server_task:
            logger.info("Stopping API server...")
            await stop_api_server()
            api_server_task.cancel()
            try:
                await api_server_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Cleanup complete")
        
    except Exception as e:
        logger.error(f"Error during cleanup: {e}", exc_info=True)


def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logger.info(f"Received signal {signum}")
    shutdown_event.set()


def main():
    """Main entry point"""
    try:
        # Setup signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Initialize services
        # Event loop policy already set at module level for Windows
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        success = loop.run_until_complete(initialize_services())
        
        if not success:
            logger.error("Failed to start Aiden")
            return 1
        
        # Start tray app (blocks until exit)
        def on_tray_exit():
            """Called when user exits from tray"""
            shutdown_event.set()
            loop.call_soon_threadsafe(loop.stop)
        
        # Run tray in separate thread with wake_word_manager and event loop
        tray_thread = threading.Thread(
            target=run_tray_app, 
            args=(on_tray_exit, wake_word_manager, loop), 
            daemon=True
        )
        tray_thread.start()
        
        # Keep event loop running in the background
        logger.info("Aiden is running. Press Ctrl+C or use tray to exit.")
        
        # Run the event loop until stopped
        try:
            loop.run_forever()
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        
        # Cleanup
        loop.run_until_complete(cleanup())
        
        logger.info("Goodbye!")
        return 0
        
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
        return 0
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())

