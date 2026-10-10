"""Track browser playback by server-issued ID and its actual audio clock."""
import asyncio
import math
import uuid

_pending = {}


def register_playback(text: str, words: list, source: str) -> dict:
    payload = {"speech_id": uuid.uuid4().hex, "text": text, "words": words, "source": source}
    if source == "web":
        _pending[payload["speech_id"]] = {
            "payload": payload, "owner": None, "done": asyncio.Event(), "loop": asyncio.get_running_loop(),
        }
    return payload


async def wait_for_playback(speech_id: str):
    entry = _pending.get(speech_id)
    if not entry:
        return
    try:
        words = entry["payload"]["words"]
        timeout = max(90, words[-1]["end"] + 30) if words else 90
        await asyncio.wait_for(entry["done"].wait(), timeout=min(3600, timeout))
    except asyncio.TimeoutError:
        pass
    finally:
        _pending.pop(speech_id, None)


def playback_event(client_id: str, data: dict):
    if not isinstance(data, dict):
        return None
    speech_id = data.get("speech_id")
    if not isinstance(speech_id, str) or len(speech_id) > 64:
        return None
    entry = _pending.get(speech_id)
    state = data.get("state")
    position = data.get("position", 0)
    if not entry or state not in ("playing", "progress", "ended", "blocked"):
        return None
    if not isinstance(position, (int, float)) or not math.isfinite(position) or not 0 <= position <= 3600:
        return None
    if entry["owner"] is None and state != "blocked":
        entry["owner"] = client_id
    if entry["owner"] is not None and entry["owner"] != client_id:
        return None
    if state == "ended":
        entry["done"].set()
    return {"speech_id": data["speech_id"], "source": "web", "state": state, "position": position}


def disconnect_playback(client_id: str):
    for entry in _pending.values():
        if entry["owner"] == client_id:
            entry["done"].set()


def cancel_playback(speech_id: str):
    entry = _pending.get(speech_id)
    if entry and not entry["loop"].is_closed():
        entry["loop"].call_soon_threadsafe(entry["done"].set)
