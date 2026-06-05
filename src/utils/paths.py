"""Path helpers for source and PyInstaller packaged runs."""
from __future__ import annotations

import sys
from pathlib import Path


def app_root() -> Path:
    """Return the directory that holds bundled runtime resources."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[2]


def resource_path(*parts: str) -> Path:
    """Resolve a path inside the repo or PyInstaller bundle."""
    return app_root().joinpath(*parts)
