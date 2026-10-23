"""Regression tests for wake acknowledgement and microphone readiness ordering."""

import asyncio
import threading
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import src.media.media_router as media_router_module
from src.core.assistant import (
    AidenAssistant,
    _needs_action_repair,
    _validated_ai_commands,
    extract_jellyfin_movie_request,
)
from src.media.media_router import MediaRouter
from src.speech.stt import STTEngine
from src.speech.wake_detection import WakeDetection


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("from_hotkey", "expected"),
    [
        (False, ["activation"]),
        (True, ["activation"]),
    ],
)
async def test_activation_sound_is_the_final_speak_now_cue(from_hotkey, expected):
    assistant = AidenAssistant.__new__(AidenAssistant)
    events = []

    async def acknowledgement():
        events.append("acknowledgement")

    async def play_sound(sound_name):
        events.append(sound_name)

    assistant._play_wake_acknowledgement = acknowledgement
    assistant.tts = SimpleNamespace(play_sound_now=play_sound)

    await assistant._play_activation_ready_cue(from_hotkey)

    assert events == expected


@pytest.mark.asyncio
async def test_activation_sound_retries_once_before_fallback():
    assistant = AidenAssistant.__new__(AidenAssistant)
    attempts = []

    async def play_sound(sound_name):
        attempts.append(sound_name)
        return len(attempts) == 2

    assistant.tts = SimpleNamespace(play_sound_now=play_sound)

    assert await assistant._play_sound_reliably("activation") is True
    assert attempts == ["activation", "activation"]


def test_command_flow_uses_buffered_audio_only_for_wake_detection():
    detection = WakeDetection("aiden_v2", 0.9, command_audio=b"wake and command")

    assert AidenAssistant._should_use_buffered_command(False, detection) is True
    assert AidenAssistant._should_use_buffered_command(True, detection) is False
    assert AidenAssistant._should_use_buffered_command(False, None) is False


def test_minor_jellyfin_provider_typo_keeps_the_requested_title():
    assert extract_jellyfin_movie_request(
        "Can you play friends on jellyfine?"
    ) == "friends"


def test_ai_action_repair_detects_contradictions_but_not_valid_plans():
    command = {"type": "media_control", "params": {
        "action": "play_title", "target": "jellyfin", "query": "Friends",
    }}
    assert _needs_action_repair("Play Friends", {
        "intent": "command", "commands": [command],
        "response": "I can't play Jellyfin", "expecting_followup": True,
    }) is True
    assert _needs_action_repair("Play Friends", {
        "intent": "command", "commands": [command],
        "response": "I'll play it", "expecting_followup": False,
    }) is False
    assert _needs_action_repair("Play Friends", {
        "intent": "command", "commands": [],
        "response": "Done.", "expecting_followup": False,
    }) is True


def test_ai_command_validation_keeps_runnable_parts_and_rejects_placeholders():
    valid = {"type": "launch_app", "params": {"name": "notepad.exe"}}
    missing_title = {"type": "media_control", "params": {
        "action": "play_title", "target": "jellyfin",
    }}
    malformed_timer = {"type": "scheduled_command", "params": {
        "duration_seconds": "later", "command": valid,
    }}
    wrong_provider = {"type": "media_control", "params": {
        "action": "play_title", "target": "spotify", "query": "Friends",
    }}
    malformed_target = {"type": "media_control", "params": {
        "action": "play", "target": ["jellyfin"],
    }}

    assert _validated_ai_commands([
        valid, missing_title, malformed_timer, wrong_provider, malformed_target,
        {"type": ["launch_app"], "params": {"name": "notepad.exe"}},
    ]) == [valid]
    assert _validated_ai_commands({"type": "launch_app", "params": {}}) == []


def test_action_result_overrides_unverified_ai_claim():
    assistant = AidenAssistant.__new__(AidenAssistant)
    successful = [{"success": True, "command": "media_control", "params": {},
                   "response_data": {"type": "jellyfin", "message": "Playing Friends on Jellyfin."}}]
    failed = [{"success": False, "command": "media_control", "params": {},
               "response_data": {"type": "jellyfin", "message": "Jellyfin player is offline."}}]

    assert assistant._response_after_execution("I can't play Jellyfin.", successful) == "Playing Friends on Jellyfin."
    assert assistant._response_after_execution("Playing Friends.", failed) == "Jellyfin isn't ready yet. Open it, then try again."


def test_timer_reply_hides_internal_action_name():
    assistant = AidenAssistant.__new__(AidenAssistant)
    result = [{"success": True, "command": "scheduled_command", "params": {},
               "response_data": "Timer created: launch_app in 10.0 seconds"}]

    assert assistant._response_after_execution("I'll open Notepad in 10 seconds.", result) == "I'll open Notepad in 10 seconds."


def test_action_refusal_is_not_mistaken_for_a_trivia_search():
    refusal = {"intent": "command", "commands": [],
               "response": "I can't access Jellyfin to play that."}
    assert AidenAssistant._is_unhelpful_question_response(refusal) is False


def make_ai_flow_assistant(ai_responses, execution_results):
    assistant = AidenAssistant.__new__(AidenAssistant)
    assistant.context_manager = SimpleNamespace(
        get_context=AsyncMock(return_value={}),
        build_messages=AsyncMock(return_value=[{"role": "user", "content": "request"}]),
        update_context=AsyncMock(),
    )
    assistant.executor = SimpleNamespace(execute_multiple=AsyncMock(return_value=execution_results))
    assistant._no_context_needed = lambda *_args: True
    assistant._speak_async = AsyncMock()
    assistant._auto_listen_for_followup = AsyncMock()
    llm = SimpleNamespace(chat=AsyncMock(side_effect=ai_responses))
    assistant._ensure_llm_client = AsyncMock(return_value=llm)
    return assistant, llm


@pytest.mark.asyncio
async def test_ai_repair_uses_jellyfin_command_and_real_success_result():
    command = {"type": "media_control", "params": {
        "action": "play_title", "target": "jellyfin", "query": "friends",
    }}
    assistant, llm = make_ai_flow_assistant(
        [
            {"intent": "command", "commands": [command], "response": "I can't play Jellyfin.",
             "expecting_followup": True, "needs_context": []},
            {"intent": "command", "commands": [command], "response": "I'll play Friends.",
             "expecting_followup": False, "needs_context": []},
        ],
        [{"success": True, "command": "media_control", "params": command["params"],
          "response_data": {"type": "jellyfin", "message": "Resuming Friends S3 E12 on Jellyfin."}}],
    )

    response = await assistant._process_user_message("Can you play friends on jellyfine?")

    assert response == "Resuming Friends S3 E12 on Jellyfin."
    assert llm.chat.await_count == 2
    assistant.executor.execute_multiple.assert_awaited_once_with([command])
    assistant._speak_async.assert_awaited_once_with(response, source="local")


@pytest.mark.asyncio
async def test_ai_miss_uses_typed_jellyfin_fallback_and_real_failure_result():
    assistant, llm = make_ai_flow_assistant(
        [
            {"intent": "command", "commands": [], "response": "I can't play Jellyfin.",
             "expecting_followup": True, "needs_context": []},
            {"intent": "command", "commands": [], "response": "I can't play Jellyfin.",
             "expecting_followup": False, "needs_context": []},
        ],
        [{"success": False, "command": "media_control",
          "params": {"action": "play_title", "target": "jellyfin", "query": "Friends"},
          "response_data": {"type": "jellyfin", "message": "No Jellyfin player was available."}}],
    )

    response = await assistant._process_user_message("Play Friends on Jellyfin")

    assert response == "Jellyfin isn't ready yet. Open it, then try again."
    assert llm.chat.await_count == 2
    command = assistant.executor.execute_multiple.await_args.args[0][0]
    assert command == {"type": "media_control", "params": {
        "action": "play_title", "target": "jellyfin", "query": "Friends",
    }}
    assistant._speak_async.assert_awaited_once_with(response, source="local")


@pytest.mark.asyncio
async def test_ai_followup_does_not_drop_an_executable_command():
    command = {"type": "launch_app", "params": {"name": "notepad.exe"}}
    assistant, llm = make_ai_flow_assistant(
        [
            {"intent": "command", "commands": [command], "response": "Opening Notepad. What else?",
             "expecting_followup": True, "needs_context": []},
            {"intent": "command", "commands": [command], "response": "Opening Notepad. What else?",
             "expecting_followup": True, "needs_context": []},
        ],
        [{"success": True, "command": "launch_app", "params": command["params"],
          "response_data": None}],
    )

    response = await assistant._process_user_message("Open Notepad and then I'll tell you more")

    assert response == "Opening Notepad. What else?"
    assert llm.chat.await_count == 2
    assistant.executor.execute_multiple.assert_awaited_once_with([command])
    assistant._auto_listen_for_followup.assert_awaited_once()


@pytest.mark.asyncio
async def test_ai_partial_request_runs_only_complete_command():
    ready_command = {"type": "launch_app", "params": {"name": "notepad.exe"}}
    missing_title = {"type": "media_control", "params": {
        "action": "play_title", "target": "jellyfin",
    }}
    plan = {
        "intent": "multi_command", "commands": [ready_command, missing_title],
        "response": "Opening Notepad. Which title should I play?",
        "expecting_followup": True, "needs_context": [],
    }
    assistant, _ = make_ai_flow_assistant(
        [plan, plan],
        [{"success": True, "command": "launch_app", "params": ready_command["params"],
          "response_data": None}],
    )

    response = await assistant._process_user_message("Open Notepad and then play a movie")

    assert response == "Opening Notepad. Which title should I play?"
    assistant.executor.execute_multiple.assert_awaited_once_with([ready_command])
    assistant._auto_listen_for_followup.assert_awaited_once()


@pytest.mark.asyncio
async def test_voice_close_spotify_after_corrected_time_schedules_once():
    bad_plan = {
        "intent": "multi_command",
        "commands": [
            {"type": "kill_process", "params": {"name": "spotify.exe"}},
            {"type": "scheduled_command", "params": {"action": "close", "duration_seconds": 60}},
        ],
        "response": "Closing Spotify in one minute.",
        "expecting_followup": False,
        "needs_context": [],
    }
    assistant, _ = make_ai_flow_assistant(
        [bad_plan],
        [{"success": True, "command": "scheduled_command", "params": {},
          "response_data": "Timer created: kill_process in 60.0 seconds"}],
    )

    response = await assistant._process_user_message(
        "Close Spotify after 5 minutes. No, no, 1 minute. Not 5 minutes, only 1 minute."
    )

    assert response == "I'll close Spotify in 1 minute."
    assistant.executor.execute_multiple.assert_awaited_once_with([{
        "type": "scheduled_command",
        "params": {"duration_seconds": 60, "command": {
            "type": "kill_process", "params": {"name": "spotify"},
        }},
    }])


@pytest.mark.asyncio
async def test_ai_repair_cannot_erase_an_original_runnable_command():
    command = {"type": "media_control", "params": {
        "action": "play_track", "target": "spotify", "query": "Bad News by Aries",
    }}
    assistant, _ = make_ai_flow_assistant(
        [
            {"intent": "command", "commands": [command], "response": "I can't play Spotify.",
             "expecting_followup": False, "needs_context": []},
            {"intent": "question", "commands": [], "response": "Try the Spotify app.",
             "expecting_followup": False, "needs_context": []},
        ],
        [{"success": True, "command": "media_control", "params": command["params"],
          "response_data": {"type": "spotify", "message": "Playing Bad News by Aries on Spotify."}}],
    )

    response = await assistant._process_user_message("Play Bad News by Aries on Spotify")

    assert response == "Playing Bad News by Aries on Spotify."
    assistant.executor.execute_multiple.assert_awaited_once_with([command])


@pytest.mark.asyncio
async def test_listening_status_is_published_only_after_microphone_ready(monkeypatch):
    engine = STTEngine.__new__(STTEngine)
    engine._silero = None
    engine._stop_requested = threading.Event()
    events = []

    def fake_listen(
        on_listening_ready,
        preserve_recent_audio,
        start_capture,
        on_capture_armed,
    ):
        events.append(("microphone_ready", preserve_recent_audio))
        assert start_capture is None
        assert on_capture_armed is not None
        on_listening_ready()
        return False, None, "timeout"

    async def fake_broadcast(status, **payload):
        events.append(("broadcast", status, payload))

    monkeypatch.setattr(engine, "_listen_sync", fake_listen)
    monkeypatch.setattr(
        "src.utils.websocket_broadcast.broadcast_voice_status",
        fake_broadcast,
    )

    result = await engine.transcribe(
        play_activation_sound=False,
        media_already_ducked=True,
    )

    assert result == (False, None, "timeout")
    assert events[0] == ("microphone_ready", False)
    assert events[1] == (
        "broadcast",
        "listening",
        {"speaking": False, "active": True, "source": "local"},
    )


def test_microphone_buffer_is_flushed_before_ready_signal(monkeypatch):
    engine = STTEngine.__new__(STTEngine)
    engine.sample_rate = 16_000
    engine._persistent_mic = object()
    events = []

    native_stream = SimpleNamespace(get_read_available=lambda: 3_200)
    stream = SimpleNamespace(
        pyaudio_stream=native_stream,
        read=lambda samples: events.append(("flushed", samples)),
    )
    source = SimpleNamespace(stream=stream)

    monkeypatch.setattr(engine, "_ensure_mic", lambda: source)
    monkeypatch.setattr(engine, "_prepare_live_microphone", lambda *_args: source)
    monkeypatch.setattr(engine, "_listen_with_vad", lambda ready_source: object())

    success, _, error = engine._listen_sync(
        lambda: events.append(("ready",)),
        preserve_recent_audio=False,
    )

    assert success is True
    assert error is None
    assert events == [
        ("flushed", 3_200),
        ("ready",),
    ]


@pytest.mark.asyncio
async def test_ready_cue_finishes_before_listening_starts(monkeypatch):
    engine = STTEngine.__new__(STTEngine)
    engine._silero = None
    engine._stop_requested = threading.Event()
    events = []

    def fake_listen(
        on_listening_ready,
        preserve_recent_audio,
        start_capture,
        on_capture_armed,
    ):
        events.append("worker_started")
        on_capture_armed()
        assert start_capture.wait(timeout=1)
        events.append("capture_started")
        on_listening_ready()
        return False, None, "timeout"

    async def cue():
        events.append("cue_started")
        await asyncio.sleep(0)
        events.append("cue_finished")

    async def fake_broadcast(*_args, **_kwargs):
        return None

    monkeypatch.setattr(engine, "_listen_sync", fake_listen)
    monkeypatch.setattr(
        "src.utils.websocket_broadcast.broadcast_voice_status",
        fake_broadcast,
    )

    result = await engine.transcribe(
        play_activation_sound=False,
        media_already_ducked=True,
        ready_cue=cue,
    )

    assert result == (False, None, "timeout")
    assert events == [
        "worker_started",
        "cue_started",
        "cue_finished",
        "capture_started",
    ]


def test_microphone_is_reopened_for_the_wake_to_stt_handoff(monkeypatch):
    engine = STTEngine.__new__(STTEngine)
    events = []
    engine._persistent_mic = SimpleNamespace(
        __exit__=lambda *_args: events.append("closed"),
    )

    def reopen():
        events.append("opened")
        engine._persistent_mic = object()

    monkeypatch.setattr(engine, "_init_persistent_mic", reopen)

    assert engine.refresh_microphone() is True
    assert events == ["closed", "opened"]


@pytest.mark.parametrize(
    ("idle_seconds", "expected"),
    [
        (60, ["closed", "opened"]),
        (30 * 60, ["closed", "opened"]),
    ],
)
def test_long_idle_microphone_is_opened_once_before_live_verification(monkeypatch, idle_seconds, expected):
    engine = STTEngine.__new__(STTEngine)
    events = []

    def make_mic():
        return SimpleNamespace(__exit__=lambda *_args: events.append("closed"))

    engine._persistent_mic = make_mic()
    engine._last_activation_refresh = time.monotonic() - idle_seconds

    def reopen():
        events.append("opened")
        engine._persistent_mic = make_mic()

    monkeypatch.setattr(engine, "_init_persistent_mic", reopen)

    assert engine.refresh_microphone() is True
    assert events == expected


def test_idle_microphone_is_opened_once_even_soon_after_startup(monkeypatch):
    engine = STTEngine.__new__(STTEngine)
    engine._persistent_mic = None
    engine._last_activation_refresh = time.monotonic() - 20
    events = []

    def reopen():
        events.append("opened")
        engine._persistent_mic = SimpleNamespace(
            __exit__=lambda *_args: events.append("closed"),
        )

    monkeypatch.setattr(engine, "_init_persistent_mic", reopen)

    assert engine.refresh_microphone() is True
    assert events == ["opened"]


def test_idle_microphone_release_is_idempotent():
    engine = STTEngine.__new__(STTEngine)
    events = []
    engine._persistent_mic = SimpleNamespace(
        __exit__=lambda *_args: events.append("closed"),
    )

    engine.close()
    engine.close()

    assert events == ["closed"]
    assert engine.microphone_ready is False


@pytest.mark.asyncio
async def test_slow_spotify_does_not_block_listening_readiness(monkeypatch):
    router = MediaRouter.__new__(MediaRouter)

    async def slow_playback_lookup():
        await asyncio.sleep(1)
        return {"is_playing": True, "device": {"id": "device"}}

    router.spotify_client = SimpleNamespace(
        is_enabled=lambda: True,
        has_fresh_token=lambda: True,
        get_current_playback=slow_playback_lookup,
        pause=lambda **kwargs: None,
    )
    local_ducker = SimpleNamespace(
        duck_for_listening=lambda: {"muted_sessions": []},
    )

    monkeypatch.setattr(media_router_module, "get_audio_session_ducker", lambda: local_ducker)
    monkeypatch.setattr(media_router_module, "_SPOTIFY_DUCK_DEADLINE_SECONDS", 0.01)

    started = asyncio.get_running_loop().time()
    state = await router.duck_for_listening()
    elapsed = asyncio.get_running_loop().time() - started

    assert elapsed < 0.2
    assert state["spotify_was_playing"] is False
    assert state["muted_app_sessions"] == {"muted_sessions": []}


@pytest.mark.asyncio
async def test_media_restore_resumes_only_sources_ducked_by_aiden(monkeypatch):
    """A paused source must never be started by voice-turn cleanup."""
    router = MediaRouter.__new__(MediaRouter)
    router.spotify_client = SimpleNamespace(
        is_enabled=lambda: True,
        has_fresh_token=lambda: True,
        get_current_playback=AsyncMock(
            return_value={"is_playing": True, "device": {"id": "desktop"}}
        ),
        pause=AsyncMock(),
        play=AsyncMock(),
    )
    router.browser_controller = SimpleNamespace(
        duck_for_listening=AsyncMock(return_value={"toggled_handles": [42]}),
        restore_after_listening=AsyncMock(),
    )
    local_ducker = SimpleNamespace(
        duck_for_listening=lambda: {"muted_sessions": []},
        restore_after_listening=lambda _state: None,
    )
    monkeypatch.setattr(media_router_module, "get_audio_session_ducker", lambda: local_ducker)

    state = await router.duck_for_listening()
    assert state["spotify_was_playing"] is True
    assert state["spotify_device_id"] == "desktop"
    assert state["browser_media"] == {"toggled_handles": [42]}

    await router.restore_after_listening(state)
    router.spotify_client.play.assert_awaited_once_with(device_id="desktop")
    router.browser_controller.restore_after_listening.assert_awaited_once_with(
        {"toggled_handles": [42]}
    )

    router.spotify_client.play.reset_mock()
    await router.restore_after_listening({"spotify_was_playing": False})
    router.spotify_client.play.assert_not_awaited()


@pytest.mark.asyncio
async def test_voice_turn_waits_for_background_reply_before_media_restore():
    assistant = AidenAssistant.__new__(AidenAssistant)
    events = []

    async def speak_in_background():
        await asyncio.sleep(0)
        events.append("reply_generated")

    async def wait_until_done(timeout):
        events.append(("playback_finished", timeout))
        return True

    task = asyncio.create_task(speak_in_background())
    assistant._speak_tasks = {task}
    assistant.tts = SimpleNamespace(wait_until_done=wait_until_done)

    await assistant._wait_for_voice_output()

    assert events == ["reply_generated", ("playback_finished", 60.0)]
