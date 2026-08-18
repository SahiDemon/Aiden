"""
Aiden AI Assistant - Main Entry Point
Unified application with hidden tray + optional web dashboard
"""
# -----------------------------------------------------------------------
# MUST be the very first code that runs — before ANY other import.
#
# When Aiden.exe is launched with --debug from a PowerShell / cmd window,
# we attach to that parent console so all logging appears in the caller's
# terminal.  If there is no parent console (double-click), AttachConsole
# fails silently and the process stays hidden (tray-only).
# -----------------------------------------------------------------------
import sys
import os
from pathlib import Path

class DummyStream:
    """A dummy stream that does nothing but prevents NoneType AttributeError for GUI processes."""
    def write(self, data: str) -> int:
        return len(data)
    def flush(self) -> None:
        pass
    def isatty(self) -> bool:
        return False
    def fileno(self) -> int:
        return -1

# CRITICAL: Prevent uvicorn/click/logging from crashing when run in windowed GUI mode without console.
if sys.stdout is None:
    sys.stdout = DummyStream()
if sys.stderr is None:
    sys.stderr = DummyStream()
if sys.stdin is None:
    sys.stdin = DummyStream()

def _attach_debug_console() -> None:
    """Attach stdout/stderr to the parent console when --debug is passed.

    Only does anything when:
    - running as a frozen PyInstaller exe (sys.frozen is set)
    - --debug or -debug is in argv (case-insensitive)
    - on Windows
    Does nothing (and never raises) in all other cases.
    """
    _debug_args = {"--debug", "-debug"}
    if not (
        sys.platform == "win32"
        and getattr(sys, "frozen", False)
        and any(a.lower() in _debug_args for a in sys.argv)
    ):
        return

    try:
        import ctypes
        import io

        ATTACH_PARENT_PROCESS = -1  # type: ignore[assignment]
        attached = ctypes.windll.kernel32.AttachConsole(ATTACH_PARENT_PROCESS)

        if attached:
            # Re-open the C-level stdout / stderr so print() and logging work.
            sys.stdout = io.TextIOWrapper(
                open("CONOUT$", "wb", buffering=0),  # noqa: WPS515
                encoding="utf-8",
                errors="replace",
                line_buffering=True,
            )
            sys.stderr = sys.stdout
            # Also redirect stdin so input() doesn't hang if ever called.
            try:
                sys.stdin = io.TextIOWrapper(
                    open("CONIN$", "rb", buffering=0),
                    encoding="utf-8",
                    errors="replace",
                )
            except OSError:
                pass  # stdin not critical
    except Exception:
        pass  # Never crash on console setup


_attach_debug_console()

import asyncio
import logging
import signal
import threading
from typing import Optional
import platform

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# CRITICAL: Import event loop policy FIRST before any other imports
# This sets the correct event loop policy for Windows/psycopg compatibility
from src.utils.event_loop import ensure_selector_event_loop

# CRITICAL: Initialize COM on the main thread immediately at startup and harden comtypes GC
try:
    import comtypes
    comtypes.CoInitialize()
    try:
        from comtypes._post_coinit.unknwn import _compointer_base
        _orig_compointer_del = _compointer_base.__del__
        def _safe_compointer_del(self, *args, **kwargs):
            try:
                _orig_compointer_del(self, *args, **kwargs)
            except Exception:
                pass
        _compointer_base.__del__ = _safe_compointer_del
    except Exception:
        pass
except Exception:
    pass

# CRITICAL: Initialize pygame mixer on the main thread at startup.
# If this is deferred to the first TTS call, it may be called from an async
# task or thread context that doesn't match the mixer's expected thread,
# leading to segfaults when stop() is called before any sound plays.
try:
    import pygame
    if not pygame.mixer.get_init():
        pygame.mixer.init()
    from src.speech import tts as _tts_module
    _tts_module._MIXER_INITIALIZED = True
    _tts_module.PYGAME_AVAILABLE = True
except Exception as _pg_exc:
    import logging as _logging
    _logging.getLogger(__name__).warning(f"Pygame mixer init at startup failed: {_pg_exc}")

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
        if arg.lower() in _DEBUG_ARGS:
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
media_idle_monitor: Optional[object] = None
shutdown_event = threading.Event()
restart_event = threading.Event()
main_loop: Optional[asyncio.AbstractEventLoop] = None


def _set_high_priority():
    """Set process priority to HIGH_PRIORITY_CLASS on Windows.

    Ensures Aiden's audio capture, wake-word, and AI threads are
    scheduled ahead of background apps for responsive interaction.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        # HIGH_PRIORITY_CLASS = 0x00000080
        ctypes.windll.kernel32.SetPriorityClass(handle, 0x00000080)
        logger.info("✅ Process priority set to HIGH_PRIORITY_CLASS")
    except Exception as e:
        logger.warning(f"Could not set process priority: {e}")


def handle_activation(from_hotkey: bool = False):
    """Handle voice activation (from wake word or hotkey) non-blockingly."""
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
        # We do NOT wait for completion, allowing the background detector thread
        # to immediately exit the callback and process the pause state (which releases mic).
        asyncio.run_coroutine_threadsafe(
            assistant.handle_voice_activation(from_hotkey=from_hotkey),
            main_loop
        )
        
    except Exception as e:
        logger.error(f"Error handling activation: {e}", exc_info=True)


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
    global assistant, wake_word_detector, wake_word_manager, hotkey_listener, toggle_hotkey_listener, stop_listening_hotkey_listener, api_server_task, overlay_launcher, ups_monitor, media_idle_monitor, main_loop
    
    # Store the main event loop for thread-safe async calls
    main_loop = asyncio.get_running_loop()
    logger.info(f"Main event loop set: {main_loop}")
    
    try:
        logger.info("=" * 70)
        logger.info("AIDEN AI ASSISTANT - STARTING UP")
        logger.info("=" * 70)
        
        # Set high process priority for responsive audio processing
        _set_high_priority()
        
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
        # Reduced from 1 s → 0.3 s: the API server starts asynchronously
        # and is typically ready in ~100ms.
        await asyncio.sleep(0.3)

        # Auto-start the configured Cloudflare Tunnel when the local binary is available.
        try:
            import os, subprocess

            cf_token = settings.app.cloudflare_tunnel_token
            cloudflared_path = Path(__file__).resolve().parent.parent / "tools" / "bin" / "cloudflared.exe"
            if cloudflared_path.exists() and cf_token:
                logger.info("Auto-starting the configured Cloudflare Tunnel")
                creation_flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
                subprocess.Popen([str(cloudflared_path), "tunnel", "run", "--token", cf_token], creationflags=creation_flags)
        except Exception as cf_err:
            logger.warning(f"Could not auto-start Cloudflare tunnel: {cf_err}")
        
        # Pre-warm the LLM client in the background so startup isn't blocked.
        # Delay 3s to let the API server finish initializing Redis first
        # (Gemini's initialize() loads the working API key index from Redis).
        async def _prewarm_llm():
            try:
                await asyncio.sleep(3)
                await assistant._ensure_llm_client()
                logger.info("✅ LLM client pre-warmed")
            except Exception as e:
                logger.warning(f"⚠️ LLM client pre-warm failed (will init on first use): {e}")
        asyncio.create_task(_prewarm_llm())
        logger.info("LLM client pre-warm scheduled in background")
        
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
        
        # Wake word detector signals readiness via wait_until_ready() — no sleep needed
        
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

        # 5.6. Start Media Idle monitoring
        try:
            from src.utils.media_idle_monitor import get_media_idle_monitor
            media_idle_monitor = get_media_idle_monitor()
            media_idle_monitor.start()
        except Exception as e:
            logger.warning(f"Could not start Media Idle monitoring: {e}")
        
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
        logger.info(f"  Media Idle Mon  : {'Running' if media_idle_monitor and media_idle_monitor.running else 'Not running'}")
        logger.info("=" * 70)
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to initialize services: {e}", exc_info=True)
        return False


async def cleanup():
    """Cleanup all services"""
    global wake_word_detector, hotkey_listener, toggle_hotkey_listener, stop_listening_hotkey_listener, api_server_task, overlay_launcher, ups_monitor, media_idle_monitor
    
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

        if ups_monitor:
            logger.info("Stopping UPS monitor...")
            ups_monitor.stop()

        if media_idle_monitor:
            logger.info("Stopping Media Idle monitor...")
            media_idle_monitor.stop()

        logger.info("Closing STT engine...")
        from src.speech.stt import reset_stt_engine
        reset_stt_engine()
        
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
