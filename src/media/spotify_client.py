"""
Spotify Web API client with refresh-token handling.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional, Tuple

try:
    import httpx
except ImportError:  # pragma: no cover - allows tests without dependency
    httpx = None

from src.utils.config import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class SpotifyError(Exception):
    """General Spotify error."""


class SpotifyNotConfiguredError(SpotifyError):
    """Raised when Spotify integration is not configured."""


class SpotifyClient:
    """Async Spotify API client supporting token refresh and playback control."""

    TOKEN_URL = "https://accounts.spotify.com/api/token"
    API_BASE = "https://api.spotify.com/v1"

    def __init__(self):
        self.settings = get_settings()
        self._client = httpx.AsyncClient(timeout=15.0) if httpx else None
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0
        self._token_lock = asyncio.Lock()
        self._background_refresh_task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------ Helpers
    def is_enabled(self) -> bool:
        cfg = self.settings.spotify
        if not httpx:
            return False
        return bool(
            cfg.enabled
            and cfg.client_id
            and cfg.client_secret
            and cfg.refresh_token
        )

    async def _ensure_token(self) -> None:
        if not self.is_enabled():
            raise SpotifyNotConfiguredError("Spotify integration is disabled or missing credentials.")

        async with self._token_lock:
            if self._access_token and time.time() < self._token_expires_at - 30:
                return
            await self._refresh_access_token()

    def has_fresh_token(self, margin_seconds: float = 30.0) -> bool:
        return bool(self._access_token and time.time() < self._token_expires_at - margin_seconds)

    def refresh_token_in_background(self) -> None:
        """Start token refresh without blocking latency-sensitive paths."""
        if not self.is_enabled():
            return

        if self.has_fresh_token():
            return

        if self._background_refresh_task and not self._background_refresh_task.done():
            return

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        async def _refresh() -> None:
            try:
                await self._ensure_token()
            except Exception as exc:
                logger.debug(f"Spotify background token refresh skipped: {exc}")

        self._background_refresh_task = loop.create_task(_refresh())

    async def _refresh_access_token(self) -> None:
        cfg = self.settings.spotify
        data = {
            "grant_type": "refresh_token",
            "refresh_token": cfg.refresh_token,
        }
        auth = (cfg.client_id, cfg.client_secret)

        if not self._client:
            raise SpotifyError("httpx is required for Spotify integration.")

        try:
            response = await self._client.post(self.TOKEN_URL, data=data, auth=auth)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error(f"Spotify token refresh failed: {exc}")
            raise SpotifyError("Failed to refresh Spotify token.") from exc

        payload = response.json()
        self._access_token = payload["access_token"]
        expires_in = payload.get("expires_in", 3600)
        self._token_expires_at = time.time() + expires_in
        logger.info("Spotify access token refreshed.")

    async def _api_request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
    ) -> Any:
        await self._ensure_token()
        headers = {"Authorization": f"Bearer {self._access_token}"}

        url = f"{self.API_BASE}{path}"
        if not self._client:
            raise SpotifyError("Spotify client is not initialized.")
        response = await self._client.request(method, url, params=params, json=json_body, headers=headers)

        if response.status_code == 401:
            # Token expired unexpectedly, refresh and retry once
            logger.info("Spotify token expired - refreshing.")
            await self._refresh_access_token()
            headers["Authorization"] = f"Bearer {self._access_token}"
            response = await self._client.request(method, url, params=params, json=json_body, headers=headers)

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.error(f"Spotify API error ({method} {path}): {exc.response.text}")
            raise SpotifyError(f"Spotify API request failed: {exc.response.status_code}") from exc

        # Handle empty responses (204 No Content or empty body)
        if response.status_code == 204 or not response.content:
            return None
        
        try:
            return response.json()
        except Exception:
            # If JSON parsing fails, return None for empty/invalid responses
            return None

    # ---------------------------------------------------------------- Playback
    async def get_current_playback(self) -> Optional[Dict[str, Any]]:
        try:
            data = await self._api_request("GET", "/me/player")
            return data
        except SpotifyError as exc:
            logger.warning(f"Spotify playback fetch failed: {exc}")
            return None

    async def play(self, context_uri: Optional[str] = None, uris: Optional[List[str]] = None, device_id: Optional[str] = None):
        body: Dict[str, Any] = {}
        if context_uri:
            body["context_uri"] = context_uri
        if uris:
            body["uris"] = uris
        params: Dict[str, Any] = {}
        if device_id:
            params["device_id"] = device_id

        await self._api_request("PUT", "/me/player/play", params=params, json_body=body or None)

    async def pause(self, device_id: Optional[str] = None):
        params = {"device_id": device_id} if device_id else None
        await self._api_request("PUT", "/me/player/pause", params=params)

    async def next_track(self, device_id: Optional[str] = None):
        params = {"device_id": device_id} if device_id else None
        await self._api_request("POST", "/me/player/next", params=params)

    async def previous_track(self, device_id: Optional[str] = None):
        params = {"device_id": device_id} if device_id else None
        await self._api_request("POST", "/me/player/previous", params=params)

    async def set_volume(self, percent: int, device_id: Optional[str] = None):
        percent = max(0, min(100, percent))
        params = {"volume_percent": percent}
        if device_id:
            params["device_id"] = device_id
        await self._api_request("PUT", "/me/player/volume", params=params)

    async def transfer_playback(self, device_id: str, play: bool = True):
        payload = {"device_ids": [device_id], "play": play}
        await self._api_request("PUT", "/me/player", json_body=payload)

    # ---------------------------------------------------------------- Search & Devices
    async def get_devices(self) -> List[Dict[str, Any]]:
        data = await self._api_request("GET", "/me/player/devices")
        return data.get("devices", []) if data else []

    async def search(self, query: str, types: List[str], limit: int = 5) -> Dict[str, Any]:
        params = {
            "q": query,
            "type": ",".join(types),
            "limit": limit,
        }
        return await self._api_request("GET", "/search", params=params)

    async def close(self):
        if self._client:
            await self._client.aclose()


# Global instance -------------------------------------------------------------
_spotify_client: Optional[SpotifyClient] = None


def get_spotify_client() -> SpotifyClient:
    global _spotify_client
    if _spotify_client is None:
        _spotify_client = SpotifyClient()
    return _spotify_client
