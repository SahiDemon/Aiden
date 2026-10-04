"""A close action succeeds only when the named app is actually gone."""

from types import SimpleNamespace

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
