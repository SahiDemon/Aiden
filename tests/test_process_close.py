"""A close action succeeds only when the named app is actually gone."""

from types import SimpleNamespace
import asyncio
from unittest.mock import AsyncMock

import psutil
import pytest

from src.execution.process_manager import ProcessManager


def test_spotify_close_checks_that_main_app_and_helpers_are_gone(monkeypatch):
    class SpotifyProcess:
        def __init__(self, pid):
            self.pid = pid
            self.info = {"name": "Spotify.exe"}

        def kill(self):
            alive.remove(self)

    alive = [SpotifyProcess(100), SpotifyProcess(101)]
    unrelated = SimpleNamespace(pid=200, info={"name": "JellyfinMediaPlayer.exe"})
    monkeypatch.setattr(psutil, "process_iter", lambda _fields: [*alive, unrelated])
    monkeypatch.setattr(psutil, "wait_procs", lambda _processes, timeout: None)

    assert ProcessManager._close_spotify_completely() is True
    assert alive == []


def test_spotify_close_reports_failure_when_app_survives(monkeypatch):
    class ProtectedSpotify:
        pid = 100
        info = {"name": "Spotify.exe"}

        def kill(self):
            raise psutil.AccessDenied(self.pid)

    monkeypatch.setattr(psutil, "process_iter", lambda _fields: [ProtectedSpotify()])
    monkeypatch.setattr(psutil, "wait_procs", lambda _processes, timeout: None)

    assert ProcessManager._close_spotify_completely() is False


@pytest.mark.asyncio
async def test_spotify_close_with_a_pid_still_closes_the_whole_app(monkeypatch):
    manager = ProcessManager()
    calls = []
    monkeypatch.setattr(manager, "_close_spotify_completely", lambda: calls.append("all") or True)

    assert await manager.kill_process("Spotify.exe (PID: 1234)") is True
    assert calls == ["all"]


@pytest.mark.asyncio
async def test_multi_process_close_is_bounded_and_waits_for_all_targets(monkeypatch):
    manager = ProcessManager()
    targets = [{"name": "chrome.exe", "pid": pid} for pid in range(1, 19)]
    context = SimpleNamespace(find_process=AsyncMock(return_value=targets))
    monkeypatch.setattr("src.utils.system_context.get_system_context", lambda: context)
    release = asyncio.Event()
    full_batch = asyncio.Event()
    active = 0
    peak = 0
    completed = []

    async def kill(pid):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        if active == 8:
            full_batch.set()
        await release.wait()
        active -= 1
        completed.append(pid)
        return pid == 18

    monkeypatch.setattr(manager, "kill_process_by_pid", kill)
    closing = asyncio.create_task(manager.kill_process("chrome.exe"))
    try:
        await asyncio.wait_for(full_batch.wait(), 1)
        assert not closing.done()
        release.set()
        assert await closing is True
        assert peak == 8
        assert sorted(completed) == list(range(1, 19))
    finally:
        release.set()
        await closing


@pytest.mark.asyncio
async def test_pid_close_uses_arguments_without_blocking_event_loop(monkeypatch):
    import threading
    from src.execution import process_manager

    loop_thread = threading.get_ident()
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs, threading.get_ident()))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(process_manager.subprocess, "run", run)
    assert await ProcessManager().kill_process_by_pid(42)
    command, kwargs, worker_thread = calls[0]
    assert command == ["taskkill", "/F", "/PID", "42"]
    assert not kwargs.get("shell", False)
    assert worker_thread != loop_thread
