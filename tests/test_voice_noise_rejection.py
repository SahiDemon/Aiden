import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import speech_recognition as sr

from src.core.assistant import AidenAssistant, should_retry_listen_after_idle
from src.speech.stt import STTEngine


@pytest.mark.parametrize("text", [".", "...", "?!", " ", "♪♫", "BELL RINGS", "[Music]", "(beeping)"])
def test_non_speech_recognition_is_rejected_without_recovery_listen(text):
    engine = STTEngine.__new__(STTEngine)
    assert engine._should_reject_transcript(text)
    assert not should_retry_listen_after_idle("non_speech")


@pytest.mark.parametrize("text", ["Oh.", "Bye", "yes", "NO", "Music", "play music", "ring the bell", "bell rings", "හරි", "thank you"])
def test_real_short_replies_and_commands_survive(text):
    assert not STTEngine.__new__(STTEngine)._should_reject_transcript(text)


def followup_assistant(monkeypatch, result):
    events = []
    assistant = AidenAssistant.__new__(AidenAssistant)
    assistant._voice_stop_requested = False
    assistant._wait_for_voice_output = AsyncMock(return_value=True)
    assistant._process_user_message = AsyncMock()
    assistant.context_manager = SimpleNamespace(refresh_pending_clarification_grace=AsyncMock())
    assistant.tts = SimpleNamespace(speak=AsyncMock())

    async def transcribe(**kwargs):
        assert assistant._is_listening
        events.append("capture")
        return result

    assistant.stt = SimpleNamespace(transcribe=transcribe, close=lambda: events.append("closed"))
    detector = SimpleNamespace(
        pause=lambda: events.append("paused"),
        wait_until_stream_released=lambda _: events.append("released") or True,
        resume=lambda: events.append("resumed"),
    )
    monkeypatch.setattr("src.core.wake_word_manager.get_wake_word_manager",
                        lambda: SimpleNamespace(detector=detector, get_state=lambda: True))
    monkeypatch.setattr("src.utils.websocket_broadcast.broadcast_message", AsyncMock())
    return assistant, events, detector


@pytest.mark.asyncio
async def test_noise_followup_stops_without_answer_or_recursive_listen(monkeypatch):
    assistant, events, _ = followup_assistant(monkeypatch, (False, None, "non_speech"))
    await assistant._auto_listen_for_followup()
    assert events == ["paused", "released", "capture", "closed", "resumed"]
    assert not assistant._is_listening
    assistant._process_user_message.assert_not_awaited()
    assistant.tts.speak.assert_not_awaited()


@pytest.mark.asyncio
async def test_real_followup_releases_microphone_before_processing(monkeypatch):
    assistant, events, _ = followup_assistant(monkeypatch, (True, "Spotify", None))
    assistant._process_user_message.side_effect = lambda _: events.append("process")
    await assistant._auto_listen_for_followup()
    assert events == ["paused", "released", "capture", "closed", "resumed", "process"]


@pytest.mark.asyncio
async def test_followup_does_not_capture_or_beep_if_detector_fails_to_release(monkeypatch):
    assistant, events, detector = followup_assistant(monkeypatch, (True, "Spotify", None))
    detector.wait_until_stream_released = Mock(return_value=False)
    await assistant._auto_listen_for_followup()
    assert events == ["paused", "resumed"]
    assistant._process_user_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancelled_followup_closes_capture_and_restores_wake_detection(monkeypatch):
    assistant, events, _ = followup_assistant(monkeypatch, None)
    assistant.stt.transcribe = AsyncMock(side_effect=asyncio.CancelledError())
    with pytest.raises(asyncio.CancelledError):
        await assistant._auto_listen_for_followup()
    assert events == ["paused", "released", "closed", "resumed"]
    assert not assistant._is_listening


@pytest.mark.asyncio
async def test_followup_never_listens_over_unfinished_assistant_playback(monkeypatch):
    assistant, events, _ = followup_assistant(monkeypatch, (True, "Hello", None))
    assistant._wait_for_voice_output.return_value = False
    await assistant._auto_listen_for_followup()
    assert events == []
    assistant._process_user_message.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("buffered", [False, True])
@pytest.mark.parametrize("text", [".", "BELL RINGS"])
async def test_noise_is_rejected_at_both_transcription_entry_points(monkeypatch, buffered, text):
    engine = STTEngine.__new__(STTEngine)
    engine.sample_rate = 16000
    engine.min_speech_duration = 0.3
    engine._stop_requested = threading.Event()
    engine._silero = None
    engine._normalize_pcm_gain = lambda value: value
    pcm = bytes(16000 * 2)

    def listen(on_ready, *_args):
        on_ready()
        return True, sr.AudioData(pcm, 16000, 2), None

    engine._listen_sync = listen
    client = SimpleNamespace(transcribe_audio=AsyncMock(return_value=text))
    monkeypatch.setattr("src.ai.groq_client.get_groq_client", AsyncMock(return_value=client))
    monkeypatch.setattr("src.utils.websocket_broadcast.broadcast_voice_status", AsyncMock())
    if buffered:
        result = await engine.transcribe_captured_pcm(pcm)
    else:
        result = await engine.transcribe(play_activation_sound=False, media_already_ducked=True)
    assert result == (False, None, "non_speech")
