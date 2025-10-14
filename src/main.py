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

# CRITICAL: Set event loop policy for Windows BEFORE any async operations
# Required for psycopg to work properly on Windows
if platform.system() == 'Windows':
    import selectors
    
    class SelectEventLoopPolicy(asyncio.DefaultEventLoopPolicy):
        """Custom event loop policy that uses SelectorEventLoop on Windows"""
        def new_event_loop(self):
            selector = selectors.SelectSelector()
            return asyncio.SelectorEventLoop(selector)
    
    asyncio.set_event_loop_policy(SelectEventLoopPolicy())

from src.api.server import start_api_server, stop_api_server
from src.core.assistant import get_assistant
from src.core.hotkey_listener import get_hotkey_listener
from src.speech.wake_word import get_wake_word_detector
from src.tray.tray_app import run_tray_app
from src.utils.config import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Global state
assistant: Optional[object] = None
wake_word_detector: Optional[object] = None
hotkey_listener: Optional[object] = None
api_server_task: Optional[asyncio.Task] = None
shutdown_event = threading.Event()
main_loop: Optional[asyncio.AbstractEventLoop] = None


def handle_activation():
    """Handle voice activation (from wake word or hotkey)"""
    try:
        logger.info("[VOICE] Voice activation triggered!")
        
        # CRITICAL: Pause wake word detector so STT can use microphone
        if wake_word_detector:
            logger.info("Pausing wake word detector...")
            wake_word_detector.pause()
        
        # Schedule the async handler in the main event loop from this thread
        global main_loop
        if main_loop is None:
            logger.error("Main event loop not set yet!")
            # Resume wake word detector
            if wake_word_detector:
                wake_word_detector.resume()
            return
        
        logger.debug(f"Loop running? {main_loop.is_running()}, Loop: {main_loop}")
        
        # Run the coroutine in the main loop from this thread
        future = asyncio.run_coroutine_threadsafe(
            assistant.handle_voice_activation(),
            main_loop
        )
        
        # Wait for completion (longer timeout for auto-listen scenarios)
        try:
            result = future.result(timeout=60)  # 60 second timeout (allows auto-listen)
            logger.info("[VOICE] Activation handling complete")
        except TimeoutError:
            logger.error("Voice activation timed out after 60 seconds")
        except Exception as e:
            logger.error(f"Error in voice activation: {e}", exc_info=True)
        finally:
            # ALWAYS resume wake word detector
            if wake_word_detector:
                logger.info("Resuming wake word detector...")
                wake_word_detector.resume()
        
    except Exception as e:
        logger.error(f"Error handling activation: {e}", exc_info=True)
        # Resume wake word detector even on error
        if wake_word_detector:
            wake_word_detector.resume()


async def initialize_services():
    """Initialize all Aiden services"""
    global assistant, wake_word_detector, hotkey_listener, api_server_task, main_loop
    
    # Store the main event loop for thread-safe async calls
    main_loop = asyncio.get_event_loop()
    logger.info(f"Main event loop set: {main_loop}")
    
    try:
        logger.info("=" * 70)
        logger.info("AIDEN AI ASSISTANT - STARTING UP")
        logger.info("=" * 70)
        
        settings = get_settings()
        
        # 1. Initialize assistant
        logger.info("Initializing assistant...")
        assistant = await get_assistant()
        
        # 2. Start API server
        logger.info(f"Starting API server on {settings.api.host}:{settings.api.port}...")
        api_server_task = asyncio.create_task(start_api_server())
        await asyncio.sleep(1)  # Give server time to start
        
        # 3. Initialize wake word detector
        logger.info("Initializing wake word detector...")
        wake_word_detector = get_wake_word_detector(on_wake_word=handle_activation)
        wake_word_detector.start()
        
        # Give wake word detector a moment to start
        await asyncio.sleep(0.5)
        
        # 4. Initialize hotkey listener
        logger.info("Initializing hotkey listener...")
        hotkey_listener = get_hotkey_listener(on_activation=handle_activation)
        hotkey_listener.start()
        
        # 5. Greet user
        await assistant.greet_user()
        
        logger.info("=" * 70)
        logger.info("AIDEN IS READY!")
        logger.info(f"Wake word: '{settings.app.wake_word}'")
        logger.info(f"Hotkey: {settings.app.hotkey}")
        logger.info(f"Dashboard: http://{settings.api.host}:{settings.api.port}")
        logger.info("=" * 70)
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to initialize services: {e}", exc_info=True)
        return False


async def cleanup():
    """Cleanup all services"""
    global wake_word_detector, hotkey_listener, api_server_task
    
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
        
        # Run tray in separate thread
        tray_thread = threading.Thread(target=run_tray_app, args=(on_tray_exit,), daemon=True)
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

