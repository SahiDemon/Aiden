"""Focused coverage for delayed non-power commands."""
from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.database.models import ScheduledTimer
from src.execution.command_executor import CommandExecutor
from src.execution.timer_scheduler import TimerScheduler


@pytest.mark.asyncio
async def test_scheduled_command_stores_a_normal_command_without_running_it():
    executor = CommandExecutor()
    scheduled = []

    class StubScheduler:
        async def create_timer(self, **kwargs):
            scheduled.append(kwargs)
            return SimpleNamespace(id=uuid4())

    executor.timer_scheduler = StubScheduler()
    command = {
        "type": "fan_control",
        "params": {"control_id": "power", "target": "off"},
    }

    success, response = await executor._handle_scheduled_command({
        "duration_seconds": 300,
        "command": command,
    })

    assert success is True
    assert "Timer created" in response
    assert scheduled == [{
        "action": "fan_control",
        "duration_seconds": 300,
        "user_id": "default",
        "conversation_id": None,
        "command_data": command,
    }]


@pytest.mark.asyncio
async def test_scheduled_command_rejects_malformed_nested_params():
    executor = CommandExecutor()
    executor.timer_scheduler = SimpleNamespace()

    success, response = await executor._handle_scheduled_command({
        "duration_seconds": 60,
        "command": {"type": "fan_control", "params": "off"},
    })

    assert success is False
    assert response == "Scheduled command must include a command with a type"


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy_params_key", ["command_params", "params"])
async def test_scheduled_command_accepts_legacy_generic_action_shape(legacy_params_key):
    executor = CommandExecutor()
    scheduled = []

    class StubScheduler:
        async def create_timer(self, **kwargs):
            scheduled.append(kwargs)
            return SimpleNamespace(id=uuid4())

    executor.timer_scheduler = StubScheduler()
    success, _ = await executor._handle_scheduled_command({
        "action": "fan_control",
        "duration_seconds": 60,
        legacy_params_key: {"operation": "off"},
    })

    assert success is True
    assert scheduled[0]["action"] == "fan_control"
    assert scheduled[0]["command_data"] == {
        "type": "fan_control",
        "params": {"operation": "off"},
    }


@pytest.mark.asyncio
async def test_scheduled_command_normalizes_legacy_spotify_play_shape():
    executor = CommandExecutor()
    scheduled = []

    class StubScheduler:
        async def create_timer(self, **kwargs):
            scheduled.append(kwargs)
            return SimpleNamespace(id=uuid4())

    executor.timer_scheduler = StubScheduler()
    success, _ = await executor._handle_scheduled_command({
        "action": "play",
        "target": "spotify",
        "duration_seconds": 600,
    })

    assert success is True
    assert scheduled[0]["action"] == "media_control"
    assert scheduled[0]["command_data"] == {
        "type": "media_control",
        "params": {"action": "play", "target": "spotify"},
    }


@pytest.mark.asyncio
async def test_scheduled_command_normalizes_legacy_close_app_shape():
    executor = CommandExecutor()
    scheduled = []

    class StubScheduler:
        async def create_timer(self, **kwargs):
            scheduled.append(kwargs)
            return SimpleNamespace(id=uuid4())

    executor.timer_scheduler = StubScheduler()
    success, _ = await executor._handle_scheduled_command({
        "action": "kill_process",
        "name": "spotify.exe",
        "duration_seconds": 600,
    })

    assert success is True
    assert scheduled[0]["action"] == "kill_process"
    assert scheduled[0]["command_data"] == {
        "type": "kill_process",
        "params": {"name": "spotify.exe"},
    }


@pytest.mark.asyncio
async def test_elapsed_generic_timer_uses_registered_command_executor(monkeypatch):
    scheduler = TimerScheduler()
    executed = []
    completed = []

    async def execute_later(command, conversation_id):
        executed.append((command, conversation_id))
        return {"success": True}

    async def no_wait(_seconds):
        return None

    async def record_completion(timer, error_message=None):
        completed.append((timer.id, error_message))

    async def no_broadcast(*_args, **_kwargs):
        return None

    scheduler.set_command_executor(execute_later)
    monkeypatch.setattr("src.execution.timer_scheduler.asyncio.sleep", no_wait)
    monkeypatch.setattr(scheduler, "_complete_timer", record_completion)
    monkeypatch.setattr(scheduler, "_broadcast_timer_update", no_broadcast)
    monkeypatch.setattr(scheduler, "_broadcast_timer_event", no_broadcast)

    command = {
        "type": "fan_control",
        "params": {"control_id": "power", "target": "on"},
    }
    timer = ScheduledTimer(
        id=uuid4(),
        action="fan_control",
        command_data=command,
        scheduled_time=datetime.utcnow() + timedelta(seconds=2),
        duration_seconds=2,
        conversation_id=None,
        status="active",
    )

    await scheduler._execute_timer(timer)

    assert executed == [(command, None)]
    assert completed == [(timer.id, None)]


@pytest.mark.asyncio
async def test_elapsed_spotify_timer_routes_through_registered_command_executor(monkeypatch):
    scheduler = TimerScheduler()
    executed = []

    async def execute_later(command, conversation_id):
        executed.append((command, conversation_id))
        return {"success": True}

    async def no_wait(_seconds):
        return None

    async def no_broadcast(*_args, **_kwargs):
        return None

    async def no_completion(*_args, **_kwargs):
        return None

    scheduler.set_command_executor(execute_later)
    monkeypatch.setattr("src.execution.timer_scheduler.asyncio.sleep", no_wait)
    monkeypatch.setattr(scheduler, "_complete_timer", no_completion)
    monkeypatch.setattr(scheduler, "_broadcast_timer_update", no_broadcast)
    monkeypatch.setattr(scheduler, "_broadcast_timer_event", no_broadcast)

    command = {"type": "media_control", "params": {"action": "play", "target": "spotify"}}
    timer = ScheduledTimer(
        id=uuid4(),
        action="media_control",
        command_data=command,
        scheduled_time=datetime.utcnow() + timedelta(seconds=2),
        duration_seconds=2,
        conversation_id=None,
        status="active",
    )

    await scheduler._execute_timer(timer)

    assert executed == [(command, None)]
