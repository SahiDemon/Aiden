"""Recovery after a transient Neon startup failure."""

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest

import src.database.neon_client as neon_client
from src.execution.timer_scheduler import TimerScheduler


@pytest.mark.asyncio
async def test_failed_startup_connection_retries_and_allows_timer_creation(monkeypatch):
    clock = [100.0]
    instances = []

    class FakeDBClient:
        def __init__(self):
            self.session_maker = None
            self.next_reconnect_at = 0.0
            self.connect_attempts = 0
            self.tables_created = 0
            self.timer_requests = []
            instances.append(self)

        async def connect(self):
            self.connect_attempts += 1
            if self.connect_attempts == 1:
                self.next_reconnect_at = clock[0] + 30
            else:
                self.session_maker = object()
                self.next_reconnect_at = 0.0

        async def create_tables(self):
            self.tables_created += 1

        async def create_timer(self, **kwargs):
            self.timer_requests.append(kwargs)
            return (
                SimpleNamespace(id=uuid4(), action=kwargs["action"], command_data=None)
                if self.session_maker else None
            )

    monkeypatch.setattr(neon_client, "_db_client", None)
    monkeypatch.setattr(neon_client, "NeonDBClient", FakeDBClient)
    monkeypatch.setattr(neon_client.time, "monotonic", lambda: clock[0])

    first_client = await neon_client.get_db_client()
    assert first_client.session_maker is None
    await neon_client.get_db_client()
    assert first_client.connect_attempts == 1

    clock[0] += 31
    scheduler = TimerScheduler()

    async def ignore_timer(_timer):
        return None

    async def ignore_broadcast(*_args):
        return None

    monkeypatch.setattr(scheduler, "_schedule_timer_task", ignore_timer)
    monkeypatch.setattr(scheduler, "_broadcast_timer_update", ignore_broadcast)
    monkeypatch.setattr(scheduler, "_broadcast_timer_event", ignore_broadcast)

    timer = await scheduler.create_timer("shutdown", 2700)

    assert timer is not None
    assert len(instances) == 1
    assert first_client.connect_attempts == 2
    assert first_client.tables_created == 1
    assert first_client.timer_requests[0]["duration_seconds"] == 2700


@pytest.mark.asyncio
async def test_concurrent_reconnect_requests_share_one_attempt(monkeypatch):
    class FakeDBClient:
        def __init__(self):
            self.session_maker = None
            self.next_reconnect_at = 0.0
            self.connect_attempts = 0

        async def connect(self):
            self.connect_attempts += 1
            await asyncio.sleep(0)
            self.session_maker = object()

        async def create_tables(self):
            return None

    monkeypatch.setattr(neon_client, "_db_client", None)
    monkeypatch.setattr(neon_client, "NeonDBClient", FakeDBClient)

    clients = await asyncio.gather(*(neon_client.get_db_client() for _ in range(3)))

    assert clients[0] is clients[1] is clients[2]
    assert clients[0].connect_attempts == 1


@pytest.mark.asyncio
async def test_failed_connection_releases_engine_and_sets_retry_cooldown(monkeypatch):
    disposed = []

    class FakeEngine:
        async def dispose(self):
            disposed.append(True)

    client = object.__new__(neon_client.NeonDBClient)
    client.engine = FakeEngine()
    client.session_maker = object()
    client.next_reconnect_at = 0.0
    monkeypatch.setattr(neon_client.time, "monotonic", lambda: 100.0)

    await client._reset_failed_connection()

    assert disposed == [True]
    assert client.engine is None
    assert client.session_maker is None
    assert client.next_reconnect_at == 130.0
