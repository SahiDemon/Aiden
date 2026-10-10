import asyncio
import collections
import json
import sys
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import numpy as np

from src.speech import playback_events
from src.speech.live_transcript import LiveTranscript
from src.speech.tts import TTSEngine


def test_live_preview_consumes_capture_frames_and_never_executes_commands(monkeypatch):
    received = []
    published = []
    ready = threading.Event()

    class Recognizer:
        def AcceptWaveform(self, frame):
            received.append(frame)
            return False

        def PartialResult(self):
            return json.dumps({"partial": "play Thunder"})

    monkeypatch.setattr("src.speech.live_transcript.load_model", lambda _: object())
    monkeypatch.setitem(sys.modules, "vosk", SimpleNamespace(KaldiRecognizer=lambda *_: Recognizer()))

    def publish(text):
        published.append(text)
        ready.set()

    preview = LiveTranscript("model", 16000, publish)
    preview.feed(b"captured PCM")
    assert ready.wait(2)
    preview.close()
    preview.feed(b"late PCM")
    assert received == [b"captured PCM"]
    assert published == ["play Thunder"]


def test_same_breath_wake_capture_streams_previews_and_hands_off_to_thinking(monkeypatch):
    from src.speech.openwakeword_wake import OpenWakeWordDetector
    loud = np.full(1280, 1000, dtype=np.int16).tobytes()
    quiet = bytes(2560)
    frames = collections.deque([loud] * 6 + [quiet] * 8)
    events, fed = [], []

    class Preview:
        def __init__(self, _path, _rate, publish):
            self.publish = publish

        def feed(self, frame):
            fed.append(frame)
            self.publish("play Thunder")

        def close(self):
            events.append(("closed", {}))

    def broadcast(kind, data):
        events.append((kind, data))
        return True

    monkeypatch.setattr("src.speech.live_transcript.LiveTranscript", Preview)
    monkeypatch.setattr("src.utils.websocket_broadcast.broadcast_from_thread", broadcast)
    detector = OpenWakeWordDetector.__new__(OpenWakeWordDetector)
    detector._stream = SimpleNamespace(read=lambda *_args, **_kwargs: frames.popleft())
    detector._noise_rms = 30
    detector.continuation_window_ms = 300
    detector._audio_history = collections.deque([b"wake"])
    pcm, metadata = detector._capture_command_continuation()
    assert metadata["continuation"] is True
    assert pcm == b"wake" + b"".join(fed)
    assert events[0][1]["status"] == "listening"
    assert events[-2][0] == "closed"
    assert events[-1][1]["status"] == "processing"


@pytest.mark.asyncio
async def test_edge_boundaries_are_kept_with_audio_and_use_seconds(monkeypatch):
    class Communicate:
        def __init__(self, **kwargs):
            assert kwargs["boundary"] == "WordBoundary"

        async def stream(self):
            yield {"type": "audio", "data": b"mp3"}
            yield {"type": "WordBoundary", "text": "Hello", "offset": 2_000_000, "duration": 3_000_000}

    monkeypatch.setattr("src.speech.tts.edge_tts.Communicate", Communicate)
    engine = TTSEngine.__new__(TTSEngine)
    engine.rate, engine.voice_id = 1, "test"
    audio = await engine._generate_speech("Hello")
    assert audio == b"mp3"
    assert engine._timings_for(audio) == [{"text": "Hello", "start": .2, "end": .5}]
    assert engine._timings_for(b"offline WAV") == []


@pytest.mark.asyncio
async def test_browser_clock_requires_known_id_and_one_playback_owner():
    payload = playback_events.register_playback("Hello", [], "web")
    speech_id = payload["speech_id"]
    assert playback_events.playback_event("other", {"speech_id": [], "state": "playing"}) is None
    assert playback_events.playback_event("other", {"speech_id": "unknown", "state": "playing"}) is None
    assert playback_events.playback_event("phone", {"speech_id": speech_id, "state": "playing", "position": float("nan")}) is None
    blocked = playback_events.playback_event("pc", {"speech_id": speech_id, "state": "blocked"})
    assert blocked["state"] == "blocked"
    assert playback_events.playback_event("phone", {"speech_id": speech_id, "state": "playing", "position": .25})["position"] == .25
    assert playback_events.playback_event("pc", {"speech_id": speech_id, "state": "ended"}) is None
    playback_events.playback_event("phone", {"speech_id": speech_id, "state": "ended"})
    await playback_events.wait_for_playback(speech_id)
    assert speech_id not in playback_events._pending


@pytest.mark.asyncio
async def test_interrupt_releases_browser_playback_wait_from_another_thread():
    payload = playback_events.register_playback("Hello", [], "web")
    await asyncio.to_thread(playback_events.cancel_playback, payload["speech_id"])
    await asyncio.wait_for(playback_events.wait_for_playback(payload["speech_id"]), 1)
    assert payload["speech_id"] not in playback_events._pending


@pytest.mark.asyncio
async def test_cached_audio_restores_its_own_boundaries(monkeypatch):
    words = [{"text": "Hello", "start": .2, "end": .5}]
    redis = SimpleNamespace(get_tts_audio=AsyncMock(return_value=b"audio"), get=AsyncMock(return_value=json.dumps(words)))
    monkeypatch.setattr("src.speech.tts.get_redis_client", AsyncMock(return_value=redis))
    engine = TTSEngine.__new__(TTSEngine)
    engine.provider = "edge"
    assert await engine._get_cached_audio("Hello") == b"audio"
    assert engine._timings_for(b"audio") == words


@pytest.mark.asyncio
async def test_speak_queues_edge_audio_without_using_offline_fallback():
    engine = TTSEngine.__new__(TTSEngine)
    engine.provider = "edge"
    engine.audio_queue = asyncio.Queue()
    engine._get_cached_audio = AsyncMock(return_value=None)
    engine._generate_speech = AsyncMock(return_value=b"mp3")
    engine._generate_offline_speech = AsyncMock(return_value=b"RIFF")
    engine._cache_audio = AsyncMock()
    await engine.speak("Hello", source="web")
    engine._generate_offline_speech.assert_not_awaited()
    assert engine.audio_queue.get_nowait() == {"type": "speak", "data": b"mp3", "text": "Hello", "source": "web"}


@pytest.mark.asyncio
async def test_browser_previews_only_broadcast_and_never_execute(monkeypatch):
    from fastapi import WebSocketDisconnect
    from src.api import server
    broadcast = AsyncMock()
    monkeypatch.setattr(server, "broadcast_update", broadcast)
    monkeypatch.setattr(server, "manager", SimpleNamespace(
        connect=AsyncMock(return_value="phone"), send_to_client=AsyncMock(), disconnect=AsyncMock(),
    ))
    packets = iter([
        {"type": "voice_transcript", "data": {"text": "", "stage": "start"}},
        {"type": "voice_transcript", "data": {"text": "play", "stage": "partial"}},
        {"type": "voice_transcript", "data": {"text": "play Thunder", "stage": "final"}},
        {"type": "voice_transcript", "data": {"text": "late preview", "stage": "partial"}},
    ])

    async def receive():
        try:
            return next(packets)
        except StopIteration:
            raise WebSocketDisconnect()

    await server.websocket_endpoint(SimpleNamespace(receive_json=receive))
    transcripts = [call.args[1]["text"] for call in broadcast.await_args_list if call.args[0] == "voice_transcript"]
    assert transcripts == ["", "play", "play Thunder"]
    stages = [call.args[1]["status"] for call in broadcast.await_args_list if call.args[0] == "voice_activity"]
    assert stages == ["listening", "processing"]
