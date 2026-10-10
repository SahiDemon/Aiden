"""Redis shutdown must never hold a thread lock across an await."""
import asyncio
from types import SimpleNamespace

import pytest

from src.database import redis_client


@pytest.mark.asyncio
@pytest.mark.parametrize("all_clients", [False, True])
async def test_shutdown_allows_registry_access_and_retains_new_clients(monkeypatch, all_clients):
    loop_id = id(asyncio.get_running_loop())
    replacement = object()
    disconnected = []

    async def disconnect():
        # A nonblocking acquire makes a lock regression fail instead of
        # freezing the test event loop.
        assert redis_client._client_lock.acquire(blocking=False)
        try:
            redis_client._redis_clients[loop_id] = replacement
        finally:
            redis_client._client_lock.release()
        await asyncio.sleep(0)
        disconnected.append(True)

    monkeypatch.setattr(redis_client, "_redis_clients", {loop_id: SimpleNamespace(disconnect=disconnect)})
    close = redis_client.close_all_redis_clients if all_clients else redis_client.close_redis_client
    await close()
    assert disconnected == [True]
    assert redis_client._redis_clients[loop_id] is replacement


@pytest.mark.asyncio
async def test_shutdown_continues_when_one_disconnect_fails(monkeypatch):
    calls = []

    async def failing():
        calls.append("failed")
        raise OSError("connection lost")

    async def succeeding():
        calls.append("closed")

    monkeypatch.setattr(redis_client, "_redis_clients", {
        1: SimpleNamespace(disconnect=failing), 2: SimpleNamespace(disconnect=succeeding),
    })
    await redis_client.close_all_redis_clients()
    assert calls == ["failed", "closed"]
    assert redis_client._redis_clients == {}
