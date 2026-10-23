"""Choose an actual playback session, never merely an open application."""
from typing import Optional


def session_key(candidate: dict) -> tuple:
    return candidate.get("target"), candidate.get("id")


def select_playback(candidates: list[dict], last: Optional[dict] = None) -> tuple[Optional[dict], str]:
    playing = [item for item in candidates if item.get("is_playing")]
    if len(playing) == 1:
        return playing[0], ""
    if len(playing) > 1:
        foreground = [item for item in playing if item.get("foreground")]
        if len(foreground) == 1:
            return foreground[0], ""
        return None, "More than one player is playing. Which one should I control?"
    # A paused session can be resumed. An idle app with no media isn't a
    # candidate. Prefer the last session the user controlled if it still exists.
    if last:
        previous = next((item for item in candidates if session_key(item) == session_key(last)), None)
        if previous:
            return previous, ""
    if len(candidates) == 1:
        return candidates[0], ""
    if candidates:
        return None, "More than one player is paused. Which one should I control?"
    return None, "I can't find any active or paused media to control."
