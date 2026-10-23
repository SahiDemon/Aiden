import asyncio
from unittest.mock import AsyncMock

import pytest

from src.utils import websocket_broadcast


@pytest.mark.parametrize("source", ["local", "web", "web_text"])
def test_voice_status_preserves_request_source(monkeypatch, source):
    callback = AsyncMock()
    monkeypatch.setattr(websocket_broadcast, "_broadcast_callback", callback)
    asyncio.run(websocket_broadcast.broadcast_voice_status("processing", active=True, source=source))
    callback.assert_awaited_once_with("voice_activity", {
        "status": "processing", "speaking": False, "active": True, "source": source,
    })


def test_voice_status_defaults_to_local_for_pc_capture(monkeypatch):
    callback = AsyncMock()
    monkeypatch.setattr(websocket_broadcast, "_broadcast_callback", callback)
    asyncio.run(websocket_broadcast.broadcast_voice_status("listening"))
    assert callback.await_args.args[1]["source"] == "local"
