import asyncio
import base64
import io
import json
import threading
import wave
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from src.speech import kitten_client as kitten
from src.speech.stt import STTEngine
from src.speech.tts import TTSEngine
from src.utils.config import SpeechConfig
import speech_recognition as sr


def config(**values):
    return SpeechConfig(_env_file=None, kitten_api_key="test-key", **values)


def http_client(monkeypatch, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr(kitten.httpx, "AsyncClient",
                        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))


@pytest.mark.asyncio
async def test_kitten_tts_complete_pcm_is_valid_wav(monkeypatch):
    pcm = b"\x00\x01" * 4800
    def handler(request):
        body = json.loads(request.content)
        assert body["voice"] == "eleanor_somber_female_32"
        assert body["stream_format"] == "sse"
        assert request.headers["Authorization"] == "Bearer test-key"
        events = [{"type": "speech.audio.delta", "audio": base64.b64encode(pcm).decode()},
                  {"type": "speech.audio.done"}]
        return httpx.Response(200, text="\n\n".join("data: " + json.dumps(e) for e in events))
    http_client(monkeypatch, handler)
    result = await kitten.KittenClient(config()).speech("Hello")
    with wave.open(io.BytesIO(result)) as audio:
        assert audio.getframerate() == 24000
        assert audio.getnchannels() == 1
        assert audio.readframes(4800) == pcm


@pytest.mark.asyncio
async def test_kitten_tts_interrupted_stream_is_not_success(monkeypatch):
    def handler(request):
        return httpx.Response(200, text='data: {"type":"speech.audio.delta","audio":"AAA="}\n\n')
    http_client(monkeypatch, handler)
    with pytest.raises(kitten.KittenError, match="without complete audio"):
        await kitten.KittenClient(config()).speech("Hello")


@pytest.mark.asyncio
async def test_kitten_http_error_does_not_expose_secrets(monkeypatch):
    http_client(monkeypatch, lambda request: httpx.Response(401, text="test-key private provider response"))
    with pytest.raises(kitten.KittenError) as error:
        await kitten.KittenClient(config()).speech("Hello")
    assert str(error.value) == "Kitten TTS HTTP 401"
    assert "kitten_api_key" not in config().model_dump()
    assert "test-key" not in repr(config())


@pytest.mark.asyncio
async def test_kitten_upload_uses_clean_text(monkeypatch):
    def handler(request):
        assert request.url.path == "/v1/audio/transcriptions"
        return httpx.Response(200, json={"text": "Open Chrome", "enriched_text": "[happy]Open Chrome[/happy]"})
    http_client(monkeypatch, handler)
    assert await kitten.KittenClient(config()).transcribe(kitten.pcm_wav(b"\0" * 9600)) == "Open Chrome"


class Socket:
    def __init__(self, *, fail=False):
        self.events = asyncio.Queue()
        self.events.put_nowait({"type": "session.created"})
        self.sent = []
        self.fail = fail
        self.exited = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.exited = True

    async def recv(self):
        return json.dumps(await self.events.get())

    async def send(self, raw):
        event = json.loads(raw)
        self.sent.append(event)
        if event["type"] == "session.update":
            assert event["session"]["audio"]["input"]["turn_detection"] is None
            self.events.put_nowait({"type": "session.updated"})
        elif event["type"] == "input_audio_buffer.append":
            assert len(base64.b64decode(event["audio"])) > 0
            self.events.put_nowait({"type": "conversation.item.input_audio_transcription.delta",
                                   "clean_text": "Open Crow", "delta": "Open Crow"})
            self.events.put_nowait({"type": "conversation.item.input_audio_transcription.delta",
                                   "clean_text": "Open Chrome", "delta": ""})
        elif event["type"] == "input_audio_buffer.commit":
            if self.fail:
                self.events.put_nowait({"type": "session.closed"})
            else:
                self.events.put_nowait({"type": "conversation.item.input_audio_transcription.completed",
                    "transcript": "Open Chrome.", "text": "[happy]Open Chrome.[/happy]"})


@pytest.mark.asyncio
async def test_kitten_realtime_replaces_partial_and_commits_final(monkeypatch):
    socket = Socket()
    monkeypatch.setattr(kitten, "connect", lambda *args, **kwargs: socket)
    previews = []
    session = kitten.KittenRealtime(config(), 16000, previews.append)
    await asyncio.to_thread(session.feed, b"\0" * 6400)
    assert await session.finish() == "Open Chrome."
    assert previews == ["Open Crow", "Open Chrome"]
    assert socket.exited
    assert session.closed.is_set()
    assert session.task.done()


@pytest.mark.asyncio
async def test_kitten_realtime_closed_without_final_fails(monkeypatch):
    socket = Socket(fail=True)
    monkeypatch.setattr(kitten, "connect", lambda *args, **kwargs: socket)
    session = kitten.KittenRealtime(config(), 16000, lambda text: None)
    session.feed(b"\0" * 6400)
    await asyncio.sleep(0)
    with pytest.raises(kitten.KittenError):
        await session.finish()
    assert socket.exited
    assert session.task.done()


@pytest.mark.asyncio
async def test_kitten_realtime_cancel_releases_session(monkeypatch):
    socket = Socket()
    monkeypatch.setattr(kitten, "connect", lambda *args, **kwargs: socket)
    session = kitten.KittenRealtime(config(), 16000, lambda text: None)
    await asyncio.sleep(0)
    await session.aclose()
    assert socket.exited
    assert session.task.done()


@pytest.mark.asyncio
async def test_stt_kitten_failure_fallback_is_explicit(monkeypatch):
    engine = STTEngine.__new__(STTEngine)
    engine.settings = SimpleNamespace(speech=config(stt_provider="kitten", kitten_fallback=False))
    monkeypatch.setattr(kitten.KittenClient, "transcribe", AsyncMock(side_effect=kitten.KittenError("offline")))
    with pytest.raises(kitten.KittenError):
        await engine._transcribe_audio(b"recording")
    groq = SimpleNamespace(transcribe_audio=AsyncMock(return_value="Open Chrome"))
    monkeypatch.setattr("src.ai.groq_client.get_groq_client", AsyncMock(return_value=groq))
    engine.settings.speech.kitten_fallback = True
    assert await engine._transcribe_audio(b"recording") == "Open Chrome"
    groq.transcribe_audio.assert_awaited_once_with(b"recording")


@pytest.mark.asyncio
async def test_tts_kitten_queues_without_waiting_for_audio():
    engine = TTSEngine.__new__(TTSEngine)
    engine.provider = "kitten"
    engine.audio_queue = asyncio.Queue()
    await engine.speak("Hello", source="local")
    assert engine.audio_queue.get_nowait() == {"type": "kitten_stream", "text": "Hello"}


@pytest.mark.asyncio
async def test_tts_kitten_plays_before_generator_finishes(monkeypatch):
    engine = TTSEngine.__new__(TTSEngine)
    engine.settings = SimpleNamespace(speech=config())
    engine._stream_stop = threading.Event()
    engine._pause_wake_word_detection = lambda: False
    engine._resume_wake_word_detection = lambda paused: None
    writes = []
    state = {"closed": False, "finished": False}
    class Stream:
        def __init__(self, **kwargs):
            assert kwargs["samplerate"] == 24000
        def start(self): pass
        def write(self, data):
            assert not state["finished"]
            writes.append(data)
        def stop(self): pass
        def close(self): state["closed"] = True
    async def generate(self, text):
        yield b"\0" * 16800
        assert writes  # playback happened before the next network event
        yield b"\0" * 4800
        state["finished"] = True
    monkeypatch.setattr("sounddevice.RawOutputStream", Stream)
    monkeypatch.setattr(kitten.KittenClient, "speech_pcm", generate)
    monkeypatch.setattr("src.utils.websocket_broadcast.broadcast_voice_status", AsyncMock())
    monkeypatch.setattr("src.utils.websocket_broadcast.broadcast_message", AsyncMock())
    await engine._play_kitten_stream("Hello")
    assert len(writes) == 2
    assert state["closed"]


def test_kitten_cache_is_separate_from_baseline():
    engine = TTSEngine.__new__(TTSEngine)
    engine.settings = SimpleNamespace(speech=config())
    engine.provider = "kitten"
    assert engine._cache_key("Hello") != "Hello"
    original = engine._cache_key("Hello")
    engine.settings.speech.kitten_tts_speed = 1.2
    assert engine._cache_key("Hello") != original
    engine.provider = "edge"
    assert engine._cache_key("Hello") != original
    assert engine._cache_key("Hello").startswith("tts:v2:")


@pytest.mark.asyncio
async def test_stt_capture_uses_realtime_final_without_upload(monkeypatch):
    socket = Socket()
    monkeypatch.setattr(kitten, "connect", lambda *args, **kwargs: socket)
    engine = STTEngine.__new__(STTEngine)
    engine.settings = SimpleNamespace(speech=config(stt_provider="kitten"))
    engine.sample_rate = 16000
    engine._stop_requested = threading.Event()
    engine._silero = None
    engine._should_reject_transcript = lambda text: False
    engine._transcribe_audio = AsyncMock(side_effect=AssertionError("must not upload after realtime"))
    pcm = b"\0" * 6400
    def listen(ready, *args):
        ready()
        engine._live_preview.feed(pcm)
        return True, sr.AudioData(pcm, 16000, 2), None
    engine._listen_sync = listen
    monkeypatch.setattr("src.utils.websocket_broadcast.broadcast_voice_status", AsyncMock())
    monkeypatch.setattr("src.utils.websocket_broadcast.broadcast_message", AsyncMock())
    assert await engine.transcribe(play_activation_sound=False, media_already_ducked=True) == (True, "Open Chrome.", None)
    assert engine._live_preview.closed.is_set()
    engine._transcribe_audio.assert_not_awaited()


def test_kitten_launch_selectors_override_saved_preferences(monkeypatch):
    from src.utils import config as module
    monkeypatch.setenv("SPEECH_KITTEN_EXPERIMENT", "true")
    monkeypatch.setenv("SPEECH_TTS_PROVIDER", "kitten")
    monkeypatch.setenv("SPEECH_STT_PROVIDER", "kitten")
    monkeypatch.setenv("SPEECH_KITTEN_API_KEY", "test-key")
    monkeypatch.setenv("APP_LLM_PROVIDER", "ollama")
    monkeypatch.setattr(module, "settings_overrides", {"speech": {"tts_provider": "edge", "stt_provider": "groq"}})
    settings = module._build_settings()
    assert settings.speech.tts_provider == "kitten"
    assert settings.speech.stt_provider == "kitten"
    assert settings.speech.kitten_api_key == "test-key"
