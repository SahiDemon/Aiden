"""Small Jellyfin remote-playback client used by Aiden media controls."""
from __future__ import annotations

from typing import Any, Optional

import httpx

from src.utils.config import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class JellyfinError(Exception):
    """Jellyfin could not complete a playback request."""


class JellyfinClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    def is_enabled(self) -> bool:
        app = self.settings.app
        return bool(app.jellyfin_url and app.jellyfin_api_key)

    @property
    def _base_url(self) -> str:
        return self.settings.app.jellyfin_url.rstrip("/")

    @property
    def _headers(self) -> dict[str, str]:
        return {"X-Emby-Token": self.settings.app.jellyfin_api_key, "Accept": "application/json"}

    async def get_sessions(self) -> list[dict[str, Any]]:
        if not self.is_enabled():
            raise JellyfinError("Jellyfin is not configured.")
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(f"{self._base_url}/Sessions", headers=self._headers)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as exc:
            raise JellyfinError("Could not connect to Jellyfin.") from exc

    async def set_paused(self, session_id: str, paused: bool) -> None:
        endpoint = "Pause" if paused else "Unpause"
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.post(
                    f"{self._base_url}/Sessions/{session_id}/Playing/{endpoint}",
                    headers=self._headers,
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise JellyfinError("Jellyfin did not accept the playback command.") from exc

    @staticmethod
    def _can_control(session: dict[str, Any]) -> bool:
        return bool(session.get("Id") and session.get("NowPlayingItem")) and session.get("SupportsMediaControl", True)

    async def get_playing_session_ids(self) -> list[str]:
        return [session["Id"] for session in await self.get_sessions()
                if self._can_control(session) and (session.get("PlayState") or {}).get("IsPaused") is False]

    async def get_paused_session_ids(self) -> list[str]:
        return [session["Id"] for session in await self.get_sessions()
                if self._can_control(session) and (session.get("PlayState") or {}).get("IsPaused") is True]

    async def pause_session(self, session_id: str) -> None:
        await self.set_paused(session_id, paused=True)

    async def resume_session(self, session_id: str) -> None:
        await self.set_paused(session_id, paused=False)

    async def pause_playing_sessions(self) -> list[str]:
        paused_ids = []
        for session_id in await self.get_playing_session_ids():
            try:
                await self.pause_session(session_id)
                paused_ids.append(session_id)
            except JellyfinError as exc:
                logger.debug("Could not pause Jellyfin session %s: %s", session_id, exc)
        return paused_ids

    async def resume_sessions(self, session_ids: list[str]) -> list[str]:
        resumed_ids = []
        for session_id in session_ids:
            try:
                await self.resume_session(session_id)
                resumed_ids.append(session_id)
            except JellyfinError as exc:
                logger.debug("Could not resume Jellyfin session %s: %s", session_id, exc)
        return resumed_ids

    async def search_movies(self, query: str) -> list[dict[str, Any]]:
        """Find movies in the Jellyfin library by title."""
        return await self.search_titles(query, item_types=("Movie",))

    async def search_titles(
        self, query: str, item_types: tuple[str, ...] = ("Movie", "Series")
    ) -> list[dict[str, Any]]:
        """Find movie and series title candidates without selecting a partial hit."""
        if not self.is_enabled():
            raise JellyfinError("Jellyfin is not configured.")
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    f"{self._base_url}/Items",
                    headers=self._headers,
                    params={"SearchTerm": query, "IncludeItemTypes": ",".join(item_types), "Recursive": "true", "Limit": 50, "Fields": "ProductionYear"},
                )
                response.raise_for_status()
                return response.json().get("Items", [])
        except httpx.HTTPError as exc:
            raise JellyfinError("Could not search the Jellyfin library.") from exc

    async def list_titles(self, item_types: tuple[str, ...] = ("Movie", "Series")) -> list[dict[str, Any]]:
        """Read a bounded title catalog when Jellyfin's literal search misses a typo."""
        if not self.is_enabled():
            raise JellyfinError("Jellyfin is not configured.")
        items: list[dict[str, Any]] = []
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                for start_index in range(0, 3000, 500):
                    response = await client.get(
                        f"{self._base_url}/Items",
                        headers=self._headers,
                        params={
                            "IncludeItemTypes": ",".join(item_types),
                            "Recursive": "true",
                            "StartIndex": start_index,
                            "Limit": 500,
                            "Fields": "ProductionYear",
                        },
                    )
                    response.raise_for_status()
                    page = response.json().get("Items", [])
                    items.extend(page)
                    if len(page) < 500:
                        break
            return items
        except httpx.HTTPError as exc:
            raise JellyfinError("Could not search the Jellyfin library.") from exc

    async def get_resume_episodes(self, user_id: str, series_id: str) -> list[dict[str, Any]]:
        """Read partially watched episodes for the viewer controlling the player."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    f"{self._base_url}/Users/{user_id}/Items/Resume",
                    headers=self._headers,
                    params={"ParentId": series_id, "IncludeItemTypes": "Episode", "Limit": 100, "EnableUserData": "true"},
                )
                response.raise_for_status()
                return response.json().get("Items", [])
        except httpx.HTTPError as exc:
            raise JellyfinError("Could not read Jellyfin watch progress.") from exc

    async def get_next_up_episode(self, user_id: str, series_id: str) -> Optional[dict[str, Any]]:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    f"{self._base_url}/Shows/NextUp",
                    headers=self._headers,
                    params={"UserId": user_id, "SeriesId": series_id, "Limit": 10, "EnableUserData": "true"},
                )
                response.raise_for_status()
                episodes = response.json().get("Items", [])
                return next((item for item in episodes if item.get("SeriesId") == series_id and item.get("Id")), None)
        except httpx.HTTPError as exc:
            raise JellyfinError("Could not read the next Jellyfin episode.") from exc

    async def get_first_episode(self, user_id: Optional[str], series_id: str) -> Optional[dict[str, Any]]:
        """Return the first available episode, with progress data when a user is known."""
        try:
            params: dict[str, Any] = {"Limit": 100, "IsMissing": "false"}
            if user_id:
                params.update({"UserId": user_id, "EnableUserData": "true"})
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    f"{self._base_url}/Shows/{series_id}/Episodes",
                    headers=self._headers,
                    params=params,
                )
                response.raise_for_status()
                episodes = response.json().get("Items", [])
                return next((item for item in episodes if item.get("Id") and item.get("IndexNumber") is not None and (item.get("ParentIndexNumber") or 0) > 0), None)
        except httpx.HTTPError as exc:
            raise JellyfinError("Could not read Jellyfin episodes.") from exc

    async def play_item(self, session_id: str, item_id: str, start_position_ticks: int = 0) -> None:
        """Start one library item on a connected Jellyfin player."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    f"{self._base_url}/Sessions/{session_id}/Playing",
                    headers=self._headers,
                    # Jellyfin binds this remote-control endpoint from query
                    # parameters, not a JSON PlayRequest body.
                    params=[("itemIds", item_id), ("playCommand", "PlayNow"), ("startPositionTicks", str(start_position_ticks))],
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise JellyfinError("Jellyfin could not start that title on the connected player.") from exc

_jellyfin_client: Optional[JellyfinClient] = None


def get_jellyfin_client() -> JellyfinClient:
    global _jellyfin_client
    if _jellyfin_client is None:
        _jellyfin_client = JellyfinClient()
    return _jellyfin_client
