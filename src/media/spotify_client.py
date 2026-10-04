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
        )

    async def _ensure_token(self, interactive_auth: bool = True) -> None:
        if not self.is_enabled():
            raise SpotifyNotConfiguredError("Spotify integration is disabled or missing credentials.")

        async with self._token_lock:
            if self._access_token and time.time() < self._token_expires_at - 30:
                return
            await self._refresh_access_token(interactive_auth=interactive_auth)

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
                await self._ensure_token(interactive_auth=False)
            except Exception as exc:
                logger.debug(f"Spotify background token refresh skipped: {exc}")

        self._background_refresh_task = loop.create_task(_refresh())

    async def _refresh_access_token(self, interactive_auth: bool = True) -> None:
        cfg = self.settings.spotify
        
        if not self._client:
            raise SpotifyError("httpx is required for Spotify integration.")

        if not cfg.refresh_token:
            if interactive_auth:
                logger.info("Spotify refresh token missing. Triggering interactive auth flow.")
                await self._interactive_auth_flow()
                return
            else:
                raise SpotifyError("Spotify refresh token missing. Interactive auth disabled.")

        data = {
            "grant_type": "refresh_token",
            "refresh_token": cfg.refresh_token,
        }
        auth = (cfg.client_id, cfg.client_secret)

        try:
            response = await self._client.post(self.TOKEN_URL, data=data, auth=auth)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            if interactive_auth:
                logger.warning(f"Spotify token refresh failed: {exc}. Trying interactive auth.")
                try:
                    await self._interactive_auth_flow()
                    return
                except Exception as inner_exc:
                    raise SpotifyError("Failed to refresh token and interactive auth failed.") from inner_exc
            else:
                logger.error(f"Spotify token refresh failed: {exc}")
                raise SpotifyError("Failed to refresh Spotify token.") from exc

        payload = response.json()
        self._access_token = payload["access_token"]
        expires_in = payload.get("expires_in", 3600)
        self._token_expires_at = time.time() + expires_in
        logger.info("Spotify access token refreshed.")

    async def _interactive_auth_flow(self) -> None:
        """Perform interactive OAuth flow, opening browser and hosting local callback."""
        from src.speech.tts import get_tts_engine
        import webbrowser
        import urllib.parse
        import threading
        import http.server
        try:
            from dotenv import set_key
        except ImportError:
            set_key = None
            
        from src.utils.config import _ENV_FILE

        cfg = self.settings.spotify
        if not cfg.client_id or not cfg.client_secret:
            await get_tts_engine().speak("I cannot connect to Spotify because the client ID or secret is missing from your config.")
            raise SpotifyError("Missing client_id or client_secret")

        logger.info("Starting interactive Spotify authorization flow...")
        await get_tts_engine().speak("My Spotify token has expired. Let me open the browser so you can authorize me again.")

        wait_event = threading.Event()
        auth_code_result = []

        class CallbackHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                parsed = urllib.parse.urlparse(self.path)
                if parsed.path != "/callback":
                    self.send_response(404)
                    self.end_headers()
                    return
                params = urllib.parse.parse_qs(parsed.query)
                code = params.get("code", [None])[0]
                if code:
                    auth_code_result.append(code)
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"<html><body><h1>Authorization successful!</h1><p>You can close this window and Aiden will resume.</p><script>setTimeout(window.close, 3000);</script></body></html>")
                else:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b"Authorization failed.")
                wait_event.set()

            def log_message(self, format, *args):
                pass  # suppress output

        server = http.server.HTTPServer(("127.0.0.1", 8888), CallbackHandler)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()

        params = {
            "client_id": cfg.client_id,
            "response_type": "code",
            "redirect_uri": "http://127.0.0.1:8888/callback",
            "scope": "user-read-playback-state user-modify-playback-state user-read-currently-playing",
        }
        auth_url = "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode(params)
        webbrowser.open(auth_url)

        # Pause wake word detector so Aiden doesn't trigger while user is authenticating
        wake_word_paused = False
        try:
            from src.main import wake_word_manager
            if wake_word_manager and getattr(wake_word_manager, "detector", None):
                wake_word_paused = wake_word_manager.detector.pause()
        except Exception as e:
            logger.debug(f"Could not pause wake-word detection for Spotify auth: {e}")

        try:
            # Wait for user to authorize (up to 2 minutes)
            await asyncio.to_thread(wait_event.wait, 120.0)
        finally:
            server.shutdown()
            server.server_close()
            # Resume wake word detector
            if wake_word_paused:
                try:
                    from src.main import wake_word_manager
                    if wake_word_manager and getattr(wake_word_manager, "detector", None):
                        wake_word_manager.detector.resume()
                except Exception as e:
                    logger.debug(f"Could not resume wake-word detection after Spotify auth: {e}")

        if not auth_code_result:
            await get_tts_engine().speak("I didn't receive the Spotify authorization. Please try again later.")
            raise SpotifyError("Interactive auth timed out or failed.")

        code = auth_code_result[0]
        logger.info("Exchanging authorization code for tokens...")
        
        token_response = await self._client.post(
            self.TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": "http://127.0.0.1:8888/callback",
            },
            auth=(cfg.client_id, cfg.client_secret)
        )
        token_response.raise_for_status()
        data = token_response.json()
        
        new_refresh = data.get("refresh_token")
        if new_refresh:
            cfg.refresh_token = new_refresh
            if set_key:
                set_key(_ENV_FILE, "SPOTIFY_REFRESH_TOKEN", new_refresh)
                logger.info("Saved new Spotify refresh token to .env")
            else:
                logger.warning("python-dotenv not installed; cannot save refresh token to .env")
                
        self._access_token = data["access_token"]
        expires_in = data.get("expires_in", 3600)
        self._token_expires_at = time.time() + expires_in
        
        await get_tts_engine().speak("Got it! Re-authorizing and playing your music.")
        logger.info("Interactive Spotify authorization complete.")

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
