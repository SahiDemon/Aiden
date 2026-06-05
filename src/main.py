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
from src.speech.openwakeword_wake import OpenWakeWordDetector
from src.tray.tray_app import run_tray_app
from src.utils.config import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

_DEBUG_ARGS = {"--debug", "-debug"}


def _apply_cli_overrides() -> None:
    """Apply simple CLI overrides before config loads."""
    for arg in list(sys.argv):
        if arg in _DEBUG_ARGS:
            os.environ["APP_DEBUG"] = "true"
            sys.argv.remove(arg)


_apply_cli_overrides()

# Global state
assistant: Optional[object] = None
wake_word_detector: Optional[object] = None
wake_word_manager: Optional[object] = None
hotkey_listener: Optional[object] = None
toggle_hotkey_listener: Optional[object] = None
stop_listening_hotkey_listener: Optional[object] = None
api_server_task: Optional[asyncio.Task] = None
overlay_launcher: Optional[object] = None
ups_monitor: Optional[object] = None
shutdown_event = threading.Event()
restart_event = threading.Event()
main_loop: Optional[asyncio.AbstractEventLoop] = None


def handle_activation(from_hotkey: bool = False):
    """Handle voice activation (from wake word or hotkey).
    
    The outermost try/finally guarantees the wake word detector
    is ALWAYS resumed, even if an unexpected error type escapes.
    """
    _resumed = False
    try:
        logger.info(f"[VOICE] Voice activation triggered! (from_hotkey={from_hotkey})")
        
        # CRITICAL: Pause wake word detector so STT can use microphone
        if wake_word_detector:
            wake_word_detector.pause()
        
        # Schedule the async handler in the main event loop from this thread
        global main_loop
        if main_loop is None:
            logger.error("Main event loop not set yet!")
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
        except asyncio.CancelledError:
            logger.info("[VOICE] Activation coroutine was cancelled")
        except Exception as e:
            logger.error(f"Error in voice activation: {e}", exc_info=True)
        
    except Exception as e:
        logger.error(f"Error handling activation: {e}", exc_info=True)
    finally:
        # GUARANTEED resume — always re-enable detection unless the user
        # intentionally disabled it via toggle (is_enabled == False).
        #
        # BUG FIX: previously this block only resumed if wake_word_manager existed
        # AND is_enabled was truthy at callback time.  If wake_word_manager hadn't
        # finished initializing, the detector would be left permanently paused and
        # every subsequent wake word would be silently ignored.
        _should_resume = True
        if wake_word_manager is not None:
            # Only skip resume when the user deliberately disabled listening.
            _should_resume = bool(getattr(wake_word_manager, "is_enabled", True))

        if wake_word_detector and _should_resume:
            wake_word_detector.resume()
            _resumed = True
            logger.debug("[VOICE] Wake word detector resumed after activation")
        elif not _should_resume:
            logger.debug("[VOICE] Wake word detector not resumed — listening disabled by user toggle")
        else:
            logger.warning(
                "[VOICE] Wake word detector was NOT resumed — detector object is missing "
                f"(from_hotkey={from_hotkey})"
            )


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


def handle_stop_listening():
    """Handle stop-listening hotkey by cancelling active STT/request work."""
    try:
        logger.info("[STOP] Stop-listening hotkey triggered!")

        global main_loop, assistant
        if main_loop is None:
            logger.error("Main event loop not set yet!")
            return

        if assistant is None:
            logger.error("Assistant not initialized!")
            return

        # Stop playback/STT immediately from the hotkey thread. The async
        # coroutine below still cancels request tasks and broadcasts state, but
        # it may have to wait if an LLM call is in progress.
        cancelled_now = assistant.request_immediate_stop()

        future = asyncio.run_coroutine_threadsafe(
            assistant.cancel_active_listening(),
            main_loop
        )

        def _log_stop_result(done_future):
            try:
                cancelled = done_future.result()
                logger.info(
                    f"[STOP] Active listening cancel result: {cancelled} "
                    f"(immediate={cancelled_now})"
                )
            except Exception as e:
                logger.error(f"Error stopping active listening: {e}", exc_info=True)

        future.add_done_callback(_log_stop_result)

    except Exception as e:
        logger.error(f"Error handling stop-listening hotkey: {e}", exc_info=True)


async def initialize_services():
    """Initialize all Aiden services"""
    global assistant, wake_word_detector, wake_word_manager, hotkey_listener, toggle_hotkey_listener, stop_listening_hotkey_listener, api_server_task, overlay_launcher, ups_monitor, main_loop
    
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
        # Reduced from 3 s → 1 s: the API server, DB, and Redis connections
        # initialize asynchronously and don't actually need 3 s of busy-wait.
        await asyncio.sleep(1)
        
        # 3. Initialize wake word detector
        logger.info("Initializing wake word detector...")
        
        def _fallback_to_vosk(error=None):
            """Fallback to Vosk wake word detector (called from startup or watchdog thread)."""
            global wake_word_detector
            logger.info("⚠️ Falling back to Vosk wake word detector...")
            try:
                wake_word_detector = get_wake_word_detector(on_wake_word=handle_activation)
                wake_word_detector.start()
                logger.info("✅ Vosk wake word detector started (fallback)")
                # Re-inject into wake word manager if it exists
                if wake_word_manager:
                    wake_word_manager.detector = wake_word_detector
                    logger.info("Wake word manager updated with Vosk detector")
            except Exception as vosk_err:
                logger.error(f"Vosk fallback also failed: {vosk_err}", exc_info=True)
        
        # Priority: openWakeWord → Porcupine → Vosk
        oww_model = getattr(settings.speech, "oww_model_path", "")
        use_oww = getattr(settings.speech, "use_openwakeword", False)

        if use_oww:
            try:
                logger.info("Using openWakeWord detector (low false-positive, open-source)")
                wake_word_detector = OpenWakeWordDetector(callback=handle_activation)
                wake_word_detector.start()
                logger.info("✅ openWakeWord detector started successfully")
            except Exception as e:
                logger.error(f"Failed to start openWakeWord detector: {e} — falling back to Vosk")
                _fallback_to_vosk()

        elif settings.speech.use_porcupine and settings.speech.porcupine_access_key:
            try:
                logger.info("Using Porcupine wake word detector")
                wake_word_detector = get_porcupine_detector(
                    on_wake_word=handle_activation,
                    on_permanent_failure=_fallback_to_vosk,
                )
                wake_word_detector.start()
                
                # Wait up to 5 seconds for Porcupine to actually initialize
                # (it initializes inside its thread, so start() alone doesn't catch errors)
                ready = wake_word_detector.wait_until_ready(timeout=5.0)
                
                if ready:
                    logger.info("✅ Porcupine wake word detector started successfully")
                else:
                    logger.warning("⚠️ Porcupine failed to initialize — falling back to Vosk")
                    wake_word_detector.stop()
                    _fallback_to_vosk()
                    
            except Exception as e:
                logger.error(f"Failed to start Porcupine detector: {e}")
                _fallback_to_vosk()
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
        
        # 4. Initialize hotkey listeners
        hotkey_listener = get_hotkey_listener(
            on_activation=lambda: handle_activation(from_hotkey=True),
            hotkey_override=settings.app.hotkey,
        )
        hotkey_listener.start()
        logger.info(f"✅ Voice activation hotkey: {hotkey_listener.hotkey_combo['str']}")
        
        toggle_hotkey_listener = HotkeyListener(
            on_activation=handle_toggle_wake_word,
            hotkey_override=settings.app.toggle_hotkey,
        )
        toggle_hotkey_listener.start()
        logger.info(f"✅ Toggle wake-word hotkey: {toggle_hotkey_listener.hotkey_combo['str']}")

        stop_listening_hotkey_listener = HotkeyListener(
            on_activation=handle_stop_listening,
            hotkey_override=settings.app.stop_listening_hotkey,
        )
        stop_listening_hotkey_listener.start()
        logger.info(f"✅ Stop-listening hotkey: {stop_listening_hotkey_listener.hotkey_combo['str']}")
        
        # 5. Start overlay (if built)
        if os.getenv("AIDEN_EMBEDDED_OVERLAY") == "1":
            logger.info("Overlay is embedded in the installer; skipping auto-launch.")
        else:
            logger.info("Starting overlay...")
            try:
                from src.utils.overlay_launcher import get_overlay_launcher
                overlay_launcher = get_overlay_launcher()
                if overlay_launcher.is_overlay_built():
                    overlay_launcher.start()
                    logger.info("✅ Overlay started")
                else:
                    logger.warning("⚠️ Overlay not built - skipping. Run 'npm run build' in overlay directory to enable.")
            except Exception as e:
                logger.warning(f"Could not start overlay: {e}")
        
        # 5.5. Start UPS monitoring (if enabled)
        if settings.ups.enabled:
            logger.info("Initializing UPS power monitoring...")
            try:
                from src.utils.ups_monitor import get_ups_monitor
                from src.utils.ups_handler import get_ups_handler
                
                # Get handler for callbacks
                ups_handler = get_ups_handler()
                
                # Initialize monitor with callbacks
                ups_monitor = get_ups_monitor(
                    info_log_path=settings.ups.info_log_path,
                    alert_threshold=settings.ups.alert_threshold,
                    critical_threshold=settings.ups.critical_threshold,
                    shutdown_threshold=settings.ups.shutdown_threshold,
                    polling_interval=settings.ups.polling_interval,
                    on_power_lost=ups_handler.handle_power_lost,
                    on_power_restored=ups_handler.handle_power_restored,
                    on_battery_alert=ups_handler.handle_battery_alert,
                    on_battery_critical=ups_handler.handle_battery_critical,
                    on_shutdown_request=ups_handler.handle_shutdown_request,
                    main_event_loop=main_loop
                )
                
                ups_monitor.start()
                logger.info("✅ UPS monitoring started")
            except Exception as e:
                logger.warning(f"Could not start UPS monitoring: {e}")
        else:
            logger.info("UPS monitoring disabled in config")
        
        # 6. Greet user
        await assistant.greet_user()
        
        logger.info("=" * 70)
        logger.info("AIDEN IS READY!")
        logger.info(f"  Wake word       : '{settings.app.wake_word}'")
        logger.info(f"  Activate        : {hotkey_listener.hotkey_combo['str'] if hotkey_listener else settings.app.hotkey}")
        logger.info(f"  Toggle wake-word: {toggle_hotkey_listener.hotkey_combo['str'] if toggle_hotkey_listener else settings.app.toggle_hotkey}")
        logger.info(f"  Stop listening  : {stop_listening_hotkey_listener.hotkey_combo['str'] if stop_listening_hotkey_listener else settings.app.stop_listening_hotkey}")
        logger.info(f"  Dashboard       : http://{settings.api.host}:{settings.api.port}")
        logger.info(f"  Overlay         : {'Running' if overlay_launcher and overlay_launcher.process else 'Not running'}")
        logger.info(f"  UPS Monitor     : {'Running' if ups_monitor and ups_monitor.running else 'Not running'}")
        logger.info("=" * 70)
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to initialize services: {e}", exc_info=True)
        return False


async def cleanup():
    """Cleanup all services"""
    global wake_word_detector, hotkey_listener, toggle_hotkey_listener, stop_listening_hotkey_listener, api_server_task, overlay_launcher, ups_monitor
    
    logger.info("=" * 70)
    logger.info("SHUTTING DOWN AIDEN")
    logger.info("=" * 70)
    
    try:
        # Stop overlay
        if overlay_launcher:
            logger.info("Stopping overlay...")
            overlay_launcher.stop()
        
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

        if stop_listening_hotkey_listener:
            logger.info("Stopping stop-listening hotkey listener...")
            stop_listening_hotkey_listener.stop()
        
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
        shutdown_event.clear()
        restart_event.clear()

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

        def on_tray_restart():
            """Called when user requests restart from tray."""
            restart_event.set()
            shutdown_event.set()
            loop.call_soon_threadsafe(loop.stop)
        
        # Run tray in separate thread with wake_word_manager and event loop
        tray_thread = threading.Thread(
            target=run_tray_app, 
            args=(on_tray_exit, wake_word_manager, loop, on_tray_restart), 
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

        if restart_event.is_set():
            logger.info("Restart requested - re-launching current process")
            os.execv(sys.executable, [sys.executable, *sys.argv])
        
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
