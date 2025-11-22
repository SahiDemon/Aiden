"""
Overlay Launcher - Automatically launches the Electron overlay when Aiden starts
"""
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional
import psutil

from src.utils.logger import get_logger

logger = get_logger(__name__)


class OverlayLauncher:
    """Manages the Electron overlay application"""
    
    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.overlay_dir = self._find_overlay_directory()
        
    def _find_overlay_directory(self) -> Optional[Path]:
        """Find the overlay directory in the project"""
        # Get project root (parent of src/)
        project_root = Path(__file__).parent.parent.parent
        overlay_path = project_root / "overlay"
        
        if overlay_path.exists() and overlay_path.is_dir():
            return overlay_path
        
        logger.warning(f"Overlay directory not found at {overlay_path}")
        return None
    
    def is_overlay_built(self) -> bool:
        """Check if the overlay has been built"""
        if not self.overlay_dir:
            return False
        
        # Check for dist-electron directory (production build)
        dist_electron = self.overlay_dir / "dist-electron"
        if dist_electron.exists():
            main_js = dist_electron / "main.js"
            if main_js.exists():
                return True
        
        return False
    
    def _kill_existing_overlays(self):
        """Kill any existing overlay processes"""
        try:
            killed_count = 0
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    # Check if it's an electron process running the overlay
                    cmdline = proc.info.get('cmdline', [])
                    if cmdline and 'electron' in proc.info['name'].lower():
                        # Check if it's our overlay (contains 'overlay' or 'Aiden Overlay' in cmdline)
                        cmdline_str = ' '.join(cmdline).lower()
                        if 'overlay' in cmdline_str or str(self.overlay_dir).lower() in cmdline_str:
                            logger.info(f"Killing existing overlay process (PID: {proc.info['pid']})")
                            proc.kill()
                            proc.wait(timeout=3)
                            killed_count += 1
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
                    pass
            
            if killed_count > 0:
                logger.info(f"Killed {killed_count} existing overlay process(es)")
        except Exception as e:
            logger.warning(f"Error while killing existing overlays: {e}")
    
    def start(self) -> bool:
        """Start the overlay application"""
        if not self.overlay_dir:
            logger.error("Cannot start overlay: overlay directory not found")
            return False
        
        if not self.is_overlay_built():
            logger.error("Cannot start overlay: overlay not built. Run 'npm run build' in overlay directory")
            return False
        
        # Kill any existing overlay processes first
        self._kill_existing_overlays()
        
        try:
            # Use electron to run the built app
            if os.name == 'nt':  # Windows
                electron_path = self.overlay_dir / "node_modules" / ".bin" / "electron.cmd"
            else:  # Linux/Mac
                electron_path = self.overlay_dir / "node_modules" / ".bin" / "electron"
            
            # Check if electron exists
            if not electron_path.exists():
                logger.error(f"Electron not found at {electron_path}. Run 'npm install' in overlay directory")
                return False
            
            logger.info(f"Starting overlay from {self.overlay_dir}...")
            
            # Start electron process in the background
            if os.name == 'nt':  # Windows
                self.process = subprocess.Popen(
                    [str(electron_path), "."],
                    cwd=str(self.overlay_dir),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            else:  # Linux/Mac
                self.process = subprocess.Popen(
                    [str(electron_path), "."],
                    cwd=str(self.overlay_dir),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            
            logger.info(f"✅ Overlay started successfully (PID: {self.process.pid})")
            return True
            
        except FileNotFoundError as e:
            logger.error(f"Electron not found: {e}. Make sure to run 'npm install' in overlay directory")
            return False
        except Exception as e:
            logger.error(f"Failed to start overlay: {e}", exc_info=True)
            return False
    
    def stop(self):
        """Stop the overlay application"""
        # First stop our tracked process
        if self.process:
            try:
                logger.info("Stopping overlay...")
                self.process.terminate()
                
                # Wait for process to terminate
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    logger.warning("Overlay didn't terminate gracefully, killing...")
                    self.process.kill()
                
                logger.info("Overlay stopped")
            except Exception as e:
                logger.error(f"Error stopping overlay: {e}", exc_info=True)
            finally:
                self.process = None
        
        # Also kill any other overlay processes that might be lingering
        self._kill_existing_overlays()


# Global singleton instance
_overlay_launcher: Optional[OverlayLauncher] = None


def get_overlay_launcher() -> OverlayLauncher:
    """Get or create the overlay launcher singleton"""
    global _overlay_launcher
    if _overlay_launcher is None:
        _overlay_launcher = OverlayLauncher()
    return _overlay_launcher

