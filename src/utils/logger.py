"""
Logging Configuration
Provides structured logging with colors and rotation
"""
import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler

try:
    from colorlog import ColoredFormatter
except ImportError:  # pragma: no cover - used in lightweight test envs
    ColoredFormatter = None


def _default_log_path() -> str:
    """Return an absolute path for the default log file.

    Resolves relative to the EXE directory when frozen (PyInstaller) or the
    project root when running from source, so the log is always written to a
    predictable location regardless of the process working directory.
    """
    if getattr(sys, "frozen", False):
        # PyInstaller EXE: write logs next to the EXE
        return str(Path(sys.executable).parent / "logs" / "aiden.log")
    # Development: project root (two levels above src/utils/logger.py)
    return str(Path(__file__).resolve().parents[2] / "logs" / "aiden.log")


def setup_logger(
    name: str = "aiden",
    log_file: str = "",
    level: int = logging.INFO,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5
) -> logging.Logger:
    """
    Setup structured logger with file rotation and colored console output
    
    Args:
        name: Logger name
        log_file: Path to log file (defaults to <app_root>/logs/aiden.log)
        level: Logging level
        max_bytes: Max log file size before rotation
        backup_count: Number of backup files to keep
        
    Returns:
        Configured logger instance
    """
    if not log_file:
        log_file = _default_log_path()
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Remove existing handlers
    logger.handlers = []
    
    # Create logs directory if it doesn't exist
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # File handler with rotation
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8"
    )
    file_formatter = logging.Formatter(
        "%(asctime)s | %(name)s | %(levelname)s | %(module)s:%(funcName)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(file_formatter)
    file_handler.setLevel(level)
    
    # Console handler with colors
    # Set encoding to utf-8 for Windows console compatibility when stdout is available.
    stream = sys.stdout if sys.stdout is not None else sys.stderr
    if sys.platform == "win32" and stream is not None and hasattr(stream, "buffer"):
        import io
        # If it is already a TextIOWrapper with utf-8 encoding, do not wrap it again (preserves line_buffering=True)
        if not (isinstance(stream, io.TextIOWrapper) and getattr(stream, "encoding", "").lower() == "utf-8"):
            stream = io.TextIOWrapper(stream.buffer, encoding="utf-8", errors="replace")
            sys.stdout = stream
    
    console_handler = logging.StreamHandler(stream)
    if ColoredFormatter:
        console_formatter = ColoredFormatter(
            "%(log_color)s%(levelname)-8s%(reset)s | %(cyan)s%(name)s%(reset)s | %(message)s",
            datefmt="%H:%M:%S",
            log_colors={
                "DEBUG": "cyan",
                "INFO": "green",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "red,bg_white",
            }
        )
    else:  # pragma: no cover - fallback path
        console_formatter = logging.Formatter(
            "%(levelname)-8s | %(name)s | %(message)s",
            datefmt="%H:%M:%S"
        )
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(level)
    
    # Add handlers to logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    # Prevent propagation to root logger
    logger.propagate = False
    
    return logger


def get_logger(name: str = "aiden") -> logging.Logger:
    """Get existing logger or create new one"""
    logger = logging.getLogger(name)
    if not logger.handlers:
        return setup_logger(name)
    return logger
