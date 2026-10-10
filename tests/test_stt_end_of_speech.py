import threading
from types import SimpleNamespace

import numpy as np
import pytest
import speech_recognition as sr

import src.speech.stt as stt_module
from src.speech.stt import STTEngine
from src.speech.audio_cues import is_activation_tone_only
from src.speech.tts import _activation_tone_pcm


def engine_for_vad():
    engine = STTEngine.__new__(STTEngine)
    engine._stop_requested = threading.Event()
    engine.sample_rate = 16000
    engine.frame_size = 512
    engine.frame_bytes = 1024
    engine.frame_duration_ms = 32
    engine.vad_aggressiveness = 1
    engine._ring_buffer_size = 15
    engine._trailing_window_frames = 7
    engine.pause_threshold = 0.9
    engine.non_speaking_duration = 0.8
    engine.timeout = 8
    engine.speech_start_min_frames = 3
    engine.speech_start_ratio = 0.35
    engine.min_speech_duration = 0.3
    engine.min_listening_duration = 0.0
    engine.max_speech_duration = 30
    engine._normalize_pcm_gain = lambda pcm: pcm
    return engine


@pytest.mark.parametrize("voice_frames", [20, 120, 375])
def test_background_noise_cannot_extend_finished_command_to_thirty_seconds(monkeypatch, voice_frames):
    engine = engine_for_vad()
    voice = (np.ones(512, dtype=np.int16) * 2000).tobytes()
    noise = (np.ones(512, dtype=np.int16) * 300).tobytes()
    engine._silero = SimpleNamespace(is_speech=lambda frame: frame == voice)
    # Reproduce the failure: WebRTC keeps reporting background noise as speech.
    monkeypatch.setattr(stt_module, "_WEBRTCVAD_AVAILABLE", True)
    monkeypatch.setattr(stt_module, "webrtcvad", SimpleNamespace(
        Vad=lambda _: SimpleNamespace(is_speech=lambda *_args: True),
    ))
    reads = []

    def read(_source):
        reads.append(1)
        assert len(reads) < voice_frames + 64, "Recording continued instead of ending after silence"
        return voice if len(reads) <= voice_frames else noise

    engine._read_live_frame = read
    audio = engine._listen_with_vad(object())
    duration = len(audio.frame_data) / (16000 * 2)
    assert voice_frames * 0.032 < duration < voice_frames * 0.032 + 1.05
    assert audio.frame_data.startswith(voice * voice_frames)


def test_sensitive_fallback_cannot_override_silero_end_of_speech():
    engine = engine_for_vad()
    engine._silero = SimpleNamespace(is_speech=lambda _: False)
    fallback = SimpleNamespace(is_speech=lambda *_args: True)
    noise = (np.ones(512, dtype=np.int16) * 300).tobytes()
    assert engine._classify_frame(noise, fallback, starting=True)
    assert not engine._classify_frame(noise, fallback, starting=False)


def test_stop_aborts_even_when_detectors_continuously_report_speech():
    engine = engine_for_vad()
    voice = (np.ones(512, dtype=np.int16) * 2000).tobytes()
    engine._silero = SimpleNamespace(is_speech=lambda _: True)
    reads = []

    def read(_source):
        reads.append(1)
        if len(reads) == 10:
            engine.request_stop()
        return voice

    engine._read_live_frame = read
    with pytest.raises(InterruptedError):
        engine._listen_with_vad(object())
    assert len(reads) == 10


def test_cue_alone_cannot_start_recording_before_user_speaks():
    engine = engine_for_vad()
    t = np.arange(512) / 16000
    cue = (4000 * np.sin(2 * np.pi * 1200 * t)).astype(np.int16).tobytes()
    voice = (np.ones(512, dtype=np.int16) * 2000).tobytes()
    silence = bytes(1024)
    # Even if a speech detector misclassifies the tone, it must not start VAD.
    engine._silero = SimpleNamespace(is_speech=lambda frame: frame in (cue, voice))
    inputs = iter([silence] * 40 + [voice] * 20 + [silence] * 60)
    engine._read_live_frame = lambda _: next(inputs)
    audio = engine._listen_with_vad(object(), initial_frames=[cue] * 4)
    assert voice * 20 in audio.frame_data
    assert cue not in audio.frame_data


def test_voice_overlapping_beep_is_retained():
    engine = engine_for_vad()
    t = np.arange(512) / 16000
    overlapping = (4000 * np.sin(2 * np.pi * 1200 * t)
                   + 3000 * np.sin(2 * np.pi * 600 * t)).astype(np.int16).tobytes()
    assert not is_activation_tone_only(overlapping, 16000)
    engine._silero = SimpleNamespace(is_speech=lambda frame: frame == overlapping)
    engine._read_live_frame = lambda _: bytes(1024)
    audio = engine._listen_with_vad(object(), initial_frames=[overlapping] * 12)
    assert audio.frame_data.startswith(overlapping * 12)


def test_cue_immediately_before_speech_is_removed_from_whisper_preroll():
    engine = engine_for_vad()
    t = np.arange(512) / 16000
    cue = (4000 * np.sin(2 * np.pi * 1200 * t)).astype(np.int16).tobytes()
    voice = (np.ones(512, dtype=np.int16) * 2000).tobytes()
    engine._silero = SimpleNamespace(is_speech=lambda frame: frame in (cue, voice))
    inputs = iter([voice] * 20 + [bytes(1024)] * 60)
    engine._read_live_frame = lambda _: next(inputs)
    audio = engine._listen_with_vad(object(), initial_frames=[cue] * 4)
    assert cue not in audio.frame_data
    assert voice * 20 in audio.frame_data


def test_generated_activation_is_short_non_voice_tone():
    tone = _activation_tone_pcm(16000, 1)
    assert len(tone) == 1920
    assert is_activation_tone_only(tone[512:1024].tobytes(), 16000)


def test_short_reply_is_captured_but_window_stays_open_for_three_seconds():
    engine = engine_for_vad()
    engine.min_listening_duration = 3.0
    voice = (np.ones(512, dtype=np.int16) * 2000).tobytes()
    silence = bytes(1024)
    engine._silero = SimpleNamespace(is_speech=lambda frame: frame == voice)
    inputs = iter([voice] * 8 + [silence] * 120)
    engine._read_live_frame = lambda _: next(inputs)
    audio = engine._listen_with_vad(object())
    duration = len(audio.frame_data) / (16000 * 2)
    assert 3.0 <= duration < 3.1
    assert audio.frame_data.startswith(voice * 8)


@pytest.mark.parametrize("fallback_only", [False, True])
def test_noise_does_not_consume_turn_before_delayed_user_speech(monkeypatch, fallback_only):
    engine = engine_for_vad()
    engine.timeout = 5
    engine.min_listening_duration = 3.0
    engine.pause_threshold = 1.5
    noise = (np.ones(512, dtype=np.int16) * 300).tobytes()
    voice = (np.ones(512, dtype=np.int16) * 2000).tobytes()
    silence = bytes(1024)
    engine._silero = SimpleNamespace(is_speech=lambda frame: frame == voice or (frame == noise and not fallback_only))
    monkeypatch.setattr(stt_module, "_WEBRTCVAD_AVAILABLE", True)
    monkeypatch.setattr(stt_module, "webrtcvad", SimpleNamespace(
        Vad=lambda _: SimpleNamespace(is_speech=lambda frame, _: frame == noise[:960]),
    ))
    # False onset at the beep, then user starts almost four seconds later.
    inputs = iter([noise] * 3 + [silence] * 120 + [voice] * 20 + [silence] * 70)
    engine._read_live_frame = lambda _: next(inputs)
    audio = engine._listen_with_vad(object())
    assert voice * 20 in audio.frame_data
    assert noise not in audio.frame_data


def test_user_can_hesitate_then_continue_without_losing_command():
    engine = engine_for_vad()
    engine.min_listening_duration = 3.0
    engine.pause_threshold = 1.5
    voice = (np.ones(512, dtype=np.int16) * 2000).tobytes()
    silence = bytes(1024)
    engine._silero = SimpleNamespace(is_speech=lambda frame: frame == voice)
    # A brief 'um', a two-second pause while deciding what to say, then command.
    inputs = iter([voice] * 8 + [silence] * 70 + [voice] * 30 + [silence] * 70)
    engine._read_live_frame = lambda _: next(inputs)
    audio = engine._listen_with_vad(object())
    assert voice * 8 + silence * 70 + voice * 30 in audio.frame_data


def test_natural_mid_command_pause_is_not_end_of_speech():
    engine = engine_for_vad()
    engine.pause_threshold = 1.5
    voice = (np.ones(512, dtype=np.int16) * 2000).tobytes()
    silence = bytes(1024)
    engine._silero = SimpleNamespace(is_speech=lambda frame: frame == voice)
    inputs = iter([voice] * 60 + [silence] * 36 + [voice] * 25 + [silence] * 60)
    engine._read_live_frame = lambda _: next(inputs)
    audio = engine._listen_with_vad(object())
    assert voice * 60 + silence * 36 + voice * 25 in audio.frame_data
    duration = len(audio.frame_data) / (16000 * 2)
    assert (60 + 36 + 25) * 0.032 + 1.5 <= duration < (60 + 36 + 25) * 0.032 + 1.6


def test_repeated_weak_noise_keeps_waiting_until_original_start_timeout():
    engine = engine_for_vad()
    engine.timeout = 5
    engine.min_listening_duration = 3.0
    voice = (np.ones(512, dtype=np.int16) * 2000).tobytes()
    silence = bytes(1024)
    engine._silero = SimpleNamespace(is_speech=lambda frame: frame == voice)
    reads = []

    def read(_):
        index = len(reads)
        reads.append(1)
        assert index < 200, "Noise kept restarting the speech-start deadline"
        return voice if index % 40 < 3 else silence

    engine._read_live_frame = read
    with pytest.raises(sr.WaitTimeoutError):
        engine._listen_with_vad(object())
    assert 5.0 <= len(reads) * 0.032 < 5.1
