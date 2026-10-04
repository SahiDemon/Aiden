"""Small async client for controlling existing Jellyfin playback sessions."""
from __future__ import annotations

from typing import Any, Dict, List

try:
    import httpx
except ImportError:  # pragma: no cover - permits imports in minimal test environments
    httpx = None

from src.utils.config import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class JellyfinError(Exception):
    """Raised when Jellyfin cannot complete a playback request."""


class JellyfinNotConfiguredError(JellyfinError):
    """Raised when Jellyfin URL or API key is missing."""


class JellyfinClient:
    """Control server sessions through Jellyfin's remote-playback API."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._client = httpx.AsyncClient(timeout=5.0) if httpx else None

    def is_enabled(self) -> bool:
        config = self.settings.app
        return bool(
            httpx
            and getattr(config, "jellyfin_url", "").strip()
            and getattr(config, "jellyfin_api_key", "").strip()
        )

    def _base_url(self) -> str:
        return self.settings.app.jellyfin_url.rstrip("/")

    def _headers(self) -> Dict[str, str]:
        return {
            "X-Emby-Token": self.settings.app.jellyfin_api_key,
            "Accept": "application/json",
        }

    async def _request(self, method: str, path: str) -> Any:
        if not self.is_enabled() or not self._client:
            raise JellyfinNotConfiguredError("Jellyfin URL or API key is not configured.")
        try:
            response = await self._client.request(
                method,
                f"{self._base_url()}{path}",
                headers=self._headers(),
            )
            response.raise_for_status()
            return response
        except httpx.HTTPError as exc:
            raise JellyfinError(f"Jellyfin request failed: {exc}") from exc

    async def get_sessions(self) -> List[Dict[str, Any]]:
        response = await self._request("GET", "/Sessions")
        try:
            payload = response.json()
        except ValueError as exc:
            raise JellyfinError("Jellyfin returned an invalid sessions response.") from exc
        return [session for session in payload if isinstance(session, dict)] if isinstance(payload, list) else []

    @staticmethod
    def _is_playback_session(session: Dict[str, Any]) -> bool:
        return bool(session.get("Id") and session.get("NowPlayingItem"))

    @classmethod
    def _can_control(cls, session: Dict[str, Any]) -> bool:
        return cls._is_playback_session(session) and session.get("SupportsMediaControl") is not False

    async def get_playing_session_ids(self) -> List[str]:
        sessions = await self.get_sessions()
        return [
            session["Id"]
            for session in sessions
            if self._can_control(session)
            # A stale session can retain NowPlayingItem while omitting playback
            # state. Treat it as non-playing; sending a pause/unpause command
            # to it can foreground or relaunch its player.
            and (session.get("PlayState") or {}).get("IsPaused") is False
        ]

    async def get_paused_session_ids(self) -> List[str]:
        sessions = await self.get_sessions()
        return [
            session["Id"]
            for session in sessions
            if self._can_control(session)
            and bool((session.get("PlayState") or {}).get("IsPaused", False))
        ]

    async def pause_session(self, session_id: str) -> None:
        await self._request("POST", f"/Sessions/{session_id}/Playing/Pause")

    async def resume_session(self, session_id: str) -> None:
        await self._request("POST", f"/Sessions/{session_id}/Playing/Unpause")

    async def pause_playing_sessions(self) -> List[str]:
        """Pause current sessions and return only those paused successfully."""
        session_ids = await self.get_playing_session_ids()
        paused_ids: List[str] = []
        for session_id in session_ids:
            try:
                await self.pause_session(session_id)
                paused_ids.append(session_id)
            except JellyfinError as exc:
                logger.debug("Could not pause Jellyfin session %s: %s", session_id, exc)
        return paused_ids

    async def resume_sessions(self, session_ids: List[str]) -> List[str]:
        """Resume exactly the sessions supplied by the caller."""
        resumed_ids: List[str] = []
        for session_id in session_ids:
            try:
                await self.resume_session(session_id)
                resumed_ids.append(session_id)
            except JellyfinError as exc:
                logger.debug("Could not resume Jellyfin session %s: %s", session_id, exc)
        return resumed_ids


_jellyfin_client: JellyfinClient | None = None


def get_jellyfin_client() -> JellyfinClient:
    global _jellyfin_client
    if _jellyfin_client is None:
        _jellyfin_client = JellyfinClient()
    return _jellyfin_client
