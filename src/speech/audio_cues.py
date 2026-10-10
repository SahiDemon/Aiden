"""Non-voice readiness cue and conservative detection of cue-only input."""

import numpy as np

ACTIVATION_TONE_HZ = 1200


def is_activation_tone_only(pcm: bytes, sample_rate: int) -> bool:
    """Identify a narrow-band cue without discarding overlapping speech."""
    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
    if len(samples) < 8:
        return False
    power = np.abs(np.fft.rfft(samples * np.hanning(len(samples)))) ** 2
    total = float(power.sum())
    if total <= 0:
        return False
    frequencies = np.fft.rfftfreq(len(samples), 1 / sample_rate)
    cue_band = np.abs(frequencies - ACTIVATION_TONE_HZ) <= 100
    return float(power[cue_band].sum()) / total > 0.85
