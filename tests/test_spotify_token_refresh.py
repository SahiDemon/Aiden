import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from src.media.spotify_client import SpotifyClient, SpotifyError


def make_client(handler):
    client = SpotifyClient.__new__(SpotifyClient)
    client.settings = SimpleNamespace(spotify=SimpleNamespace(
        enabled=True, client_id="client", client_secret="secret", refresh_token="old-refresh",
    ))
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client._access_token = None
    client._token_expires_at = 0
    client._token_lock = asyncio.Lock()
    client._rejected_refresh_token = None
    client._background_refresh_task = None
    client._interactive_auth_flow = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_rejected_refresh_is_not_retried_in_background():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(400, json={"error": "invalid_grant"})

    client = make_client(handler)
    try:
        for _ in range(2):
            with pytest.raises(SpotifyError, match="Reconnect Spotify"):
                await client._ensure_token(interactive_auth=False)
        client.refresh_token_in_background()
        assert client._background_refresh_task is None
        assert len(calls) == 1
        await client._ensure_token()
        client._interactive_auth_flow.assert_awaited_once()
    finally:
        await client._client.aclose()


@pytest.mark.asyncio
async def test_refresh_rotation_is_saved_and_missing_rotation_keeps_token(monkeypatch):
    save = Mock()
    monkeypatch.setattr("dotenv.set_key", save)
    client = make_client(lambda request: httpx.Response(200, json={
        "access_token": "new-access", "expires_in": 3600, "refresh_token": "replacement",
    }))
    try:
        await client._refresh_access_token(False)
        assert client.settings.spotify.refresh_token == "replacement"
        assert client.has_fresh_token()
        assert save.call_args.args[1:] == ("SPOTIFY_REFRESH_TOKEN", "replacement")
        client._apply_token_payload({"access_token": "next-access"})
        assert client.settings.spotify.refresh_token == "replacement"
        assert save.call_count == 1
    finally:
        await client._client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("status, code, message", [
    (400, "invalid_client", "client credentials"),
    (503, "server_error", "503"),
])
async def test_other_errors_do_not_open_authorization_browser(status, code, message):
    client = make_client(lambda request: httpx.Response(status, json={"error": code}))
    try:
        with pytest.raises(SpotifyError, match=message):
            await client._refresh_access_token()
        client._interactive_auth_flow.assert_not_awaited()
        assert client._rejected_refresh_token is None
    finally:
        await client._client.aclose()


@pytest.mark.asyncio
async def test_network_failure_does_not_open_authorization_browser():
    def handler(request):
        raise httpx.ConnectError("connection failed", request=request)

    client = make_client(handler)
    try:
        with pytest.raises(SpotifyError, match="Could not reach"):
            await client._refresh_access_token()
        client._interactive_auth_flow.assert_not_awaited()
    finally:
        await client._client.aclose()
