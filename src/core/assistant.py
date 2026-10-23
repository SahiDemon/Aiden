"""
Main Aiden Assistant Orchestrator
Coordinates all components for intelligent voice interaction
"""
import asyncio
from difflib import SequenceMatcher
import json
import logging
import re
import time
from typing import Optional, List, Dict, Any, Tuple

from src.ai.groq_client import get_groq_client
from src.ai.gemini_client import get_gemini_client
from src.ai.ollama_client import get_ollama_client
from src.core.context_manager import get_context_manager
from src.execution.command_executor import get_command_executor
from src.speech.stt import get_stt_engine
from src.speech.tts import get_tts_engine
from src.speech.wake_detection import WakeDetection
from src.utils.config import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _normalize_intent_text(text: str) -> str:
    normalized = re.sub(r"[^a-z0-9\s]", " ", (text or "").lower())
    return " ".join(normalized.split())


def _repair_contextual_media_request(user_text: str, commands: List[dict]) -> List[dict]:
    """A standalone playback request must not inherit an invented app target."""
    text = _normalize_intent_text(user_text)
    text = re.sub(r"^(?:(?:can|could|would) you )?(?:please )?", "", text)
    text = re.sub(r" please$", "", text)
    match = re.fullmatch(
        r"(pause|stop|resume|play|next|previous|mute|unmute)(?: (?:it|this|that|the playback|playback|the music|music|song|track|video|episode|the song|the video))?",
        text,
    )
    action = None
    volume = None
    if match:
        action = {"stop": "pause", "play": "resume"}.get(match[1], match[1])
    elif re.fullmatch(r"(?:volume up|(?:increase|raise|turn up) (?:the )?volume|turn (?:the )?volume up)", text):
        action = "volume_up"
    elif re.fullmatch(r"(?:volume down|(?:decrease|lower|reduce|turn down) (?:the )?volume|turn (?:the )?volume down)", text):
        action = "volume_down"
    else:
        level = re.fullmatch(r"(?:set |turn )?(?:the )?volume(?: to)? (\d{1,3})(?: percent)?", text)
        if level:
            action, volume = "set_volume", max(0, min(100, int(level[1])))
    if action is None:
        return commands
    params = {"action": action}
    if volume is not None:
        params["volume"] = volume
    return [{"type": "media_control", "params": params}]


def _repair_youtube_search_request(user_text: str, commands: List[dict]) -> List[dict]:
    """Recover a dropped search phrase in one explicit YouTube playback request."""
    match = re.fullmatch(
        r"\s*(?:(?:can|could|would) you\s+)?(?:please\s+)?play\s+(.+?)\s+(?:on|using)\s+"
        r"(youtube\s+music|youtube)\s*(?:please)?[.!?]*\s*",
        user_text, re.IGNORECASE,
    )
    if not match or len(commands) > 1:
        return commands
    query = re.sub(r"^(?:some|a|the)\s+", "", match[1].strip(), flags=re.IGNORECASE)
    if not query or query.lower() in {"it", "this", "that", "music", "playback"}:
        return commands
    if re.search(r"\b(?:and then|then|and (?:open|close|play|pause|turn|set))\b", query, re.IGNORECASE):
        return commands
    target = "youtube_music" if "music" in match[2].lower() else "youtube"
    if commands and commands[0].get("type") == "media_control":
        params = commands[0].get("params") or {}
        if params.get("target") == target and params.get("query") and params.get("action") in {"play_track", "play_playlist"}:
            return commands
    playlist = bool(re.search(r"\bplaylist\b", query, re.IGNORECASE))
    return [{"type": "media_control", "params": {
        "action": "play_playlist" if playlist else "play_track", "target": target, "query": query,
    }}]


def _keep_spotify_correction_as_one_action(user_text: str, commands: List[dict]) -> Tuple[List[dict], Optional[str]]:
    """A spoken correction replaces the earlier Spotify action in this utterance."""
    normalized = _normalize_intent_text(user_text)
    if "spotify" not in normalized:
        return commands, None
    corrections = re.split(r"\b(?:i mean|actually|rather)\b", normalized)
    if len(corrections) < 2:
        return commands, None
    final_request = corrections[-1].strip()
    media_reference = re.search(r"\b(?:spotify|playback|music|it)\b", final_request)
    if not media_reference and not re.fullmatch(r"(?:please )?(?:pause|stop|resume|play)", final_request):
        return commands, None
    if re.search(r"\b(?:not|dont|don t|never)\b", final_request):
        return commands, None
    # 'post the playback' is a common phonetic transcription of 'pause the
    # playback'. Limit that repair to this explicit playback correction.
    if re.search(r"\b(?:pause|stop)\b", final_request) or re.search(r"\bpost (?:the )?playback\b", final_request):
        action, response = "pause", "Spotify paused."
    elif re.search(r"\bresume\b", final_request) or re.fullmatch(r"(?:please )?play(?: (?:the )?(?:playback|music|spotify|it))?", final_request):
        action, response = "play", "Spotify playback resumed."
    else:
        return commands, None
    retained = [command for command in commands if not (
        command.get("type") == "media_control"
        and command.get("params", {}).get("target") == "spotify"
    )]
    retained.append({"type": "media_control", "params": {"action": action, "target": "spotify"}})
    return retained, response


_SYSTEM_ACTION_TERMS = {
    "lock": ("lock",),
    "shutdown": ("shutdown", "shut down", "turn off the computer", "turn off computer", "turn off the pc"),
    "restart": ("restart", "reboot"),
    "sleep": ("sleep", "put the computer to sleep", "put computer to sleep", "put the pc to sleep"),
    "hibernate": ("hibernate",),
}

_AIDEN_EXIT_TERMS = (
    "exit aiden", "quit aiden", "close aiden", "stop aiden", "kill aiden",
    "kill python", "terminate yourself", "shut down aiden", "shutdown aiden",
)
_AIDEN_RESTART_TERMS = (
    "restart yourself", "restart aiden", "reboot aiden", "restart the assistant",
)


def is_explicit_system_action_requested(user_text: str, action: str) -> bool:
    """Require an explicit power-action phrase before executing it.

    This is a final guard against a model inventing a lock, shutdown, restart,
    sleep, or hibernate action while answering an unrelated request.
    """
    normalized = _normalize_intent_text(user_text)
    return any(term in normalized for term in _SYSTEM_ACTION_TERMS.get(action.lower(), ()))


def remove_unrequested_system_commands(user_text: str, commands: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], List[str]]:
    """Remove system power actions that were not explicitly said by the user."""
    allowed: List[Dict[str, Any]] = []
    blocked_actions: List[str] = []
    normalized_request = _normalize_intent_text(user_text)

    for command in commands:
        command_type = (command.get("type") or "").lower()
        params = command.get("params") or {}
        action = ""

        if command_type == "system_command":
            action = str(params.get("action") or "").lower()
        elif command_type == "scheduled_command":
            action = str(params.get("action") or "").lower()
            nested_command = params.get("command")
            if isinstance(nested_command, dict) and (nested_command.get("type") or "").lower() == "system_command":
                action = str((nested_command.get("params") or {}).get("action") or "").lower()
        elif command_type == "self_termination":
            action = "exit Aiden"
        elif command_type == "restart_application":
            action = "restart Aiden"

        unrequested_power = action in _SYSTEM_ACTION_TERMS and not is_explicit_system_action_requested(user_text, action)
        unrequested_exit = action == "exit Aiden" and not any(term in normalized_request for term in _AIDEN_EXIT_TERMS)
        unrequested_restart = action == "restart Aiden" and not any(term in normalized_request for term in _AIDEN_RESTART_TERMS)
        if unrequested_power or unrequested_exit or unrequested_restart:
            logger.error("Blocked unrequested system action '%s' for: %s", action, user_text)
            blocked_actions.append(action)
            continue

        allowed.append(command)

    return allowed, blocked_actions


def infer_delayed_close_command(user_text: str) -> Optional[Dict[str, Any]]:
    """Read one clear delayed close request, including a spoken time correction."""
    normalized = _normalize_intent_text(user_text)
    match = re.search(
        r"\b(?:close|quit|exit|stop)\s+(?:the\s+)?(?P<target>[a-z0-9 ._-]+?)\s+(?:in|after)\s+(?P<amount>\d+|one|a|an)\s*(?P<unit>second|seconds|minute|minutes|hour|hours)\b",
        normalized,
    )
    if not match:
        return None

    remainder = normalized[match.end():]
    if re.search(r"\b(?:and|then)\s+(?:turn|open|close|quit|exit|stop|play|pause|lock|shut|restart)\b", remainder):
        return None

    target = match.group("target").strip()
    if (
        not target
        or target in {"it", "this", "that", "app", "application"}
        or re.search(r"\b(?:and|then|now)\b", target)
    ):
        return None

    # Speech often includes a self-correction: "after five minutes, no,
    # one minute." Use the last affirmative time, never a negated time.
    duration_matches = list(re.finditer(
        r"\b(?P<amount>\d+|one|a|an)\s*(?P<unit>second|seconds|minute|minutes|hour|hours)\b",
        normalized[match.start("amount"):],
    ))
    corrected_duration = duration_matches[0]
    for candidate in duration_matches[1:]:
        preceding = normalized[match.start("amount"):][max(0, candidate.start() - 12):candidate.start()].strip()
        if not re.search(r"\bnot\s*$", preceding):
            corrected_duration = candidate

    amount_text = corrected_duration.group("amount")
    amount = 1 if amount_text in {"one", "a", "an"} else int(amount_text)
    unit = corrected_duration.group("unit")
    multiplier = 3600 if unit.startswith("hour") else 60 if unit.startswith("minute") else 1
    duration_seconds = amount * multiplier

    return {
        "type": "scheduled_command",
        "params": {
            "duration_seconds": duration_seconds,
            "command": {"type": "kill_process", "params": {"name": target}},
        },
    }


def _keep_delayed_close_as_one_action(
    user_text: str, commands: List[Dict[str, Any]]
) -> tuple[List[Dict[str, Any]], Optional[str]]:
    """Keep one clearly spoken delayed close as one scheduled action."""
    delayed = infer_delayed_close_command(user_text)
    if not delayed:
        return commands, None

    target = delayed["params"]["command"]["params"]["name"]
    return [delayed], _delayed_close_reply(target, delayed["params"]["duration_seconds"])


def _delayed_close_reply(target: str, delay_seconds: int) -> str:
    target = target.removesuffix(".exe")
    if delay_seconds % 3600 == 0:
        value, unit = delay_seconds // 3600, "hour"
    elif delay_seconds % 60 == 0:
        value, unit = delay_seconds // 60, "minute"
    else:
        value, unit = delay_seconds, "second"
    return f"I'll close {target.title()} in {value} {unit}{'' if value == 1 else 's'}."


def _is_jellyfin_provider_name(name: str) -> bool:
    """Allow a minor speech-to-text spelling error in an explicit provider."""
    return SequenceMatcher(None, name.casefold(), "jellyfin").ratio() >= 0.85


def _has_explicit_jellyfin_provider(user_text: str) -> bool:
    match = re.search(r"\bon\s+([\w-]+)[?!.,]*\s*$", user_text, flags=re.IGNORECASE)
    return bool(match and _is_jellyfin_provider_name(match.group(1)))


def _is_capability_refusal(response_text: str) -> bool:
    """Identify an AI claim that it cannot perform an action before trying it."""
    return bool(re.search(
        r"\b(?:can'?t|cannot|unable|not able|don'?t have|do not have)\b",
        response_text or "",
        flags=re.IGNORECASE,
    ))


def _needs_action_repair(user_text: str, ai_response: Dict[str, Any]) -> bool:
    """Retry contradictory AI plans without silently discarding their commands."""
    commands = ai_response.get("commands") or []
    response = str(ai_response.get("response") or "")
    return bool(
        (commands and (ai_response.get("expecting_followup") or _is_capability_refusal(response)))
        or (
            not commands
            and ai_response.get("intent") in {"command", "multi_command", "system_command"}
            and not ai_response.get("expecting_followup")
        )
        or (
            ai_response.get("intent") in {"command", "multi_command", "system_command"}
            and _is_capability_refusal(response)
        )
        or (
            _is_capability_refusal(response)
            and (
                _has_explicit_jellyfin_provider(user_text)
                or any(provider in _normalize_intent_text(user_text) for provider in ("spotify", "youtube"))
            )
        )
    )


def _has_jellyfin_play_command(commands: List[Dict[str, Any]]) -> bool:
    return any(
        isinstance(command, dict)
        and command.get("type") == "media_control"
        and (command.get("params") or {}).get("target") == "jellyfin"
        and (command.get("params") or {}).get("action") in {"play_title", "play_movie", "play_series"}
        and bool((command.get("params") or {}).get("query"))
        for command in commands
    )


def _validated_ai_commands(raw_commands: Any) -> List[Dict[str, Any]]:
    """Reject incomplete tool calls, while allowing runnable partial requests."""
    if not isinstance(raw_commands, list):
        return []

    validated: List[Dict[str, Any]] = []
    for command in raw_commands:
        if not isinstance(command, dict) or not isinstance(command.get("params"), dict):
            continue
        command_type = command.get("type")
        if not isinstance(command_type, str):
            continue
        params = command["params"]
        action = params.get("action")

        if command_type == "media_control":
            if not isinstance(action, str) or not action.strip():
                continue
            target = params.get("target")
            if target is not None and not isinstance(target, str):
                continue
            if target is not None and target not in {"spotify", "jellyfin", "youtube", "youtube_music"}:
                continue
            if action in {"play_title", "play_movie", "play_series"} and target != "jellyfin":
                continue
            if action in {"play_title", "play_movie", "play_series", "play_track", "play_playlist"}:
                if not isinstance(params.get("query"), str) or not params["query"].strip():
                    continue
            if action == "transfer" and not isinstance(params.get("device_name"), str):
                continue
            if action == "set_volume" and params.get("volume", params.get("level")) is None:
                continue
        elif command_type == "launch_app":
            if not any(
                isinstance(params.get(key), str) and params[key].strip()
                for key in ("name", "app_name", "app", "application")
            ):
                continue
        elif command_type == "kill_process":
            if not isinstance(params.get("name"), str) or not params["name"].strip():
                continue
        elif command_type in {"system_command", "system_control", "wake_word_control", "ups_control"}:
            if not isinstance(action, str) or not action.strip():
                continue
        elif command_type == "scheduled_command":
            try:
                duration_seconds = float(params.get("duration_seconds"))
            except (TypeError, ValueError):
                continue
            if not 0 < duration_seconds <= 31_536_000:
                continue
            nested = params.get("command")
            if nested is not None:
                if (
                    not isinstance(nested, dict)
                    or nested.get("type") in {"scheduled_command", "cancel_timer", "self_termination", "restart_application"}
                    or not _validated_ai_commands([nested])
                ):
                    continue
            elif action not in {"shutdown", "restart", "sleep", "hibernate", "lock"}:
                continue
            command = {**command, "params": {**params, "duration_seconds": duration_seconds}}
        elif command_type == "shell_command":
            if not isinstance(params.get("command"), str) or not params["command"].strip():
                continue
        elif command_type == "fan_control":
            if not (params.get("control_id") or params.get("operation") or action):
                continue
        elif command_type not in {"fan_control", "cancel_timer", "self_termination", "restart_application"}:
            continue

        validated.append(command)

    return validated


def extract_jellyfin_movie_request(user_text: str) -> Optional[str]:
    """Return a likely movie title from a short, unqualified play request."""
    normalized = _normalize_intent_text(user_text)
    # This shortcut runs before the LLM. It must never override an explicit
    # provider choice such as Spotify just because the words after "play" also
    # look like a possible film title.
    explicit_non_jellyfin_providers = {
        "spotify", "youtube", "youtube music", "soundcloud", "apple music",
        "amazon music", "tidal", "deezer",
    }
    if any(provider in normalized for provider in explicit_non_jellyfin_providers):
        return None

    match = re.match(
        r"^\s*(?:can you |could you |please )?play\s+(.+?)[?!.,]*\s*$",
        user_text or "",
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    title = match.group(1).strip().rstrip("?!., ")
    provider_match = re.match(r"^(.+?)\s+on\s+([\w-]+)$", title, flags=re.IGNORECASE)
    if provider_match and _is_jellyfin_provider_name(provider_match.group(2)):
        title = provider_match.group(1).strip()
    if title.lower() in {"music", "something", "a song", "some music", "spotify"}:
        return None
    return title or None


def should_retry_listen_after_idle(error: Optional[str]) -> bool:
    """Retry one capture window after the common first-command idle failure."""
    normalized = (error or "").strip().lower()
    return normalized == "timeout" or "no speech" in normalized


def infer_simple_fan_command(user_text: str) -> Optional[Dict[str, Any]]:
    """
    Recover obvious single-purpose fan power commands when STT typos or the LLM
    misses a simple request like "trun of fan".
    """
    normalized = _normalize_intent_text(user_text)
    if not normalized or "fan" not in normalized:
        return None

    # Only apply this heuristic to short, direct fan commands.
    if any(token in normalized.split() for token in {"and", "then", "after"}):
        return None
    if re.search(r"\b(?:in|within)\s+(?:\d+|one|a|an)\s*(?:seconds?|minutes?|hours?)\b", normalized):
        return None

    off_patterns = (
        r"\b(?:turn|trun|switch|shut)\s+(?:the\s+)?fan\s+(?:off|of)\b",
        r"\b(?:turn|trun|switch|shut)\s+(?:off|of)\s+(?:the\s+)?fan\b",
        r"\bfan\s+(?:off|of)\b",
        r"\bstop\s+(?:the\s+)?fan\b",
    )
    on_patterns = (
        r"\b(?:turn|trun|switch)\s+(?:the\s+)?fan\s+on\b",
        r"\b(?:turn|trun|switch)\s+on\s+(?:the\s+)?fan\b",
        r"\bfan\s+on\b",
    )

    target: Optional[str] = None
    if any(re.search(pattern, normalized) for pattern in off_patterns):
        target = "off"
    elif any(re.search(pattern, normalized) for pattern in on_patterns):
        target = "on"

    if target is None:
        return None

    response = "Turning the fan off." if target == "off" else "Turning the fan on."
    return {
        "is_followup": False,
        "intent": "command",
        "commands": [{"type": "fan_control", "params": {"control_id": "power", "target": target}}],
        "response": response,
        "update_context": True,
        "expecting_followup": False,
    }


def build_fan_spoken_response(payload: Any) -> Optional[str]:
    """Generate deterministic, user-friendly spoken fan status."""
    if isinstance(payload, str):
        text = payload.strip()
        lowered = text.lower()
        if "already off" in lowered:
            return "The fan is already off."
        if "already on" in lowered:
            return "The fan is already on."
        return None

    if not isinstance(payload, dict):
        return None

    control_id = str(payload.get("control_id") or "").lower()
    target = str(payload.get("target") or "").lower() if payload.get("target") is not None else None
    message = str(payload.get("message") or "").strip().lower()
    device = payload.get("device") if isinstance(payload.get("device"), dict) else {}
    summary = device.get("summary") if isinstance(device, dict) else {}
    confirmed_state = str(summary.get("state") or "").lower() if isinstance(summary, dict) else ""

    if control_id == "power" and payload.get("unverified_toggle"):
        return "I sent a power toggle to the fan."

    if control_id == "power" and target in {"on", "off"}:
        if "already" in message:
            return f"The fan is already {target}."
        if confirmed_state == target:
            return f"The fan is {target}."
        return f"I sent the command to turn the fan {target}."

    if control_id == "speed" and target:
        return f"Fan speed set to {target}."

    if control_id == "timer" and target:
        if target == "off":
            return "Turning the fan timer off."
        return f"Setting the fan timer to {target} hours."

    if control_id == "osc" and target in {"on", "off"}:
        return f"Turning oscillation {target}."

    if control_id == "mode" and target:
        return f"Setting the fan mode to {target}."

    return None


class AidenAssistant:
    """
    Main assistant orchestrator
    Handles the complete interaction flow from speech to execution
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.user_name = self.settings.app.user_name
        
        # Core components (non-async)
        self.context_manager = get_context_manager()
        self.executor = get_command_executor()
        self.stt = get_stt_engine()
        self.tts = get_tts_engine()
        
        # Async components (initialized lazily)
        self.llm_client = None
        
        # State
        self.is_processing = False
        self._speak_tasks = set()
        self._current_request_task = None
        self._is_listening = False
        
        logger.info(f"Aiden Assistant initialized with {self.settings.app.llm_provider.upper()} LLM")

    async def _play_wake_acknowledgement(self) -> None:
        """Play the short voice wake acknowledgement before the mic-open cue."""
        try:
            import random

            sound_name = random.choice(("mmm1", "mmm2"))
            await self.tts.play_sound_now(sound_name)
        except Exception as exc:
            logger.debug("Could not play wake acknowledgement: %s", exc)

    async def _play_sound_reliably(self, sound_name: str) -> bool:
        """Play a cue with one retry and an audible Windows fallback."""
        for attempt in range(2):
            try:
                result = await self.tts.play_sound_now(sound_name)
                # Older/mocked engines returned None after successful playback.
                if result is not False:
                    return True
            except Exception as exc:
                logger.debug(
                    "Wake cue '%s' attempt %d failed: %s",
                    sound_name,
                    attempt + 1,
                    exc,
                )
            if attempt == 0:
                await asyncio.sleep(0.04)

        if sound_name == "activation":
            try:
                import winsound

                await asyncio.to_thread(winsound.MessageBeep, winsound.MB_OK)
                logger.warning("Activation sound failed; used Windows fallback cue")
                return True
            except Exception as exc:
                logger.warning("All activation cue paths failed: %s", exc)
        return False

    async def _play_activation_ready_cue(self, from_hotkey: bool) -> None:
        """Play the cue while capture is already recording.

        Spoken acknowledgements would be captured as speech and could end the
        recording before the user starts. Use the same short cue for both paths.
        """
        started_at = getattr(self, "_activation_started_at", None)
        if started_at is not None:
            import time
            logger.info("[TIMING] Activation to ready cue: %.0f ms", (time.monotonic() - started_at) * 1000)
        await self._play_sound_reliably("activation")

    async def _play_continuous_command_confirmation(self) -> None:
        """Confirm a command that was already captured with the wake phrase."""
        await self._play_sound_reliably("activation")

    @staticmethod
    def _should_use_buffered_command(
        from_hotkey: bool,
        wake_detection: Optional[WakeDetection],
    ) -> bool:
        return bool(
            not from_hotkey
            and wake_detection is not None
            and wake_detection.has_command_audio
        )

    async def _maybe_apply_vague_close_heuristic(
        self,
        user_text: str,
        needs_context: List[str],
        ai_response: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        If the user asked to close a vague 'game' or 'music player' and the LLM only asked a question,
        pick a kill target from the running-process table (singleton) or list concrete candidates.
        """
        if not ai_response or "running_processes" not in (needs_context or []):
            return ai_response
        if ai_response.get("commands"):
            return ai_response

        ut = (user_text or "").lower()
        wants_game = bool(
            re.search(
                r"\b(close|kill|end|quit|stop|force\s*quit)\s+(my|the|this)?\s*game\b",
                ut,
            )
        ) or ("close" in ut and "my game" in ut)
        wants_music = bool(
            re.search(
                r"\b(close|kill|end|quit|stop)\s+.*\b(music\s*player|my\s+music|app\s+playing\s+music|the\s+music\s+app)\b",
                ut,
            )
        ) or ("close" in ut and "playing music" in ut)

        if not wants_game and not wants_music:
            return ai_response

        from src.utils.system_context import get_system_context

        lines = (await get_system_context().get_ai_context()).get("running_processes") or []

        def parse_pid_rows(tag: str) -> List[Tuple[str, int, str]]:
            rows: List[Tuple[str, int, str]] = []
            for line in lines:
                if tag not in line:
                    continue
                m = re.match(r"^(.+?)\s+\(PID:\s*(\d+)\)", line.strip())
                if m:
                    rows.append((m.group(1).strip(), int(m.group(2)), line))
            return rows

        path_markers = (
            "steamapps",
            "epic games",
            "riot games",
            "ubisoft",
            "ea games",
            "electronic arts",
            "battle.net",
            "gog ",
            "xboxgames",
            "rockstar games",
        )

        def parse_rows_from_path_hints() -> List[Tuple[str, int, str]]:
            rows: List[Tuple[str, int, str]] = []
            for line in lines:
                low = line.lower()
                if not any(m in low for m in path_markers):
                    continue
                m = re.match(r"^(.+?)\s+\(PID:\s*(\d+)\)", line.strip())
                if m:
                    rows.append((m.group(1).strip(), int(m.group(2)), line))
            return rows

        candidates: List[Tuple[str, int, str]] = []
        if wants_game:
            candidates = parse_pid_rows("[game]")
            if not candidates:
                candidates = parse_rows_from_path_hints()
        elif wants_music:
            candidates = parse_pid_rows("[media/music]")

        # #region agent log
        try:
            with open("debug-a7b452.log", "a", encoding="utf-8") as _df:
                _df.write(
                    json.dumps(
                        {
                            "sessionId": "a7b452",
                            "timestamp": int(time.time() * 1000),
                            "location": "assistant.py:_maybe_apply_vague_close_heuristic",
                            "message": "vague_close_heuristic",
                            "hypothesisId": "H5",
                            "data": {
                                "wants_game": wants_game,
                                "wants_music": wants_music,
                                "candidate_count": len(candidates),
                                "llm_had_commands": bool(ai_response.get("commands")),
                            },
                        }
                    )
                    + "\n"
                )
        except Exception:
            pass
        # #endregion

        if len(candidates) == 1:
            name, pid, _ = candidates[0]
            out = dict(ai_response)
            out["commands"] = [{"type": "kill_process", "params": {"name": f"{name} (PID: {pid})"}}]
            out["response"] = f"Closing {name}."
            out["expecting_followup"] = False
            out["intent"] = "command"
            logger.info(f"Vague close heuristic: killing singleton {name} (PID {pid})")
            return out

        if len(candidates) > 1:
            kind = "games" if wants_game else "music apps"
            names = [c[0] for c in candidates[:6]]
            out = dict(ai_response)
            out["commands"] = []
            out["response"] = f"I see several {kind} running: {', '.join(names)}. Which one should I close?"
            out["expecting_followup"] = True
            out["intent"] = "command"
            logger.info("Vague close heuristic: listed multiple candidates for user choice")
            return out

        return ai_response

    def _maybe_apply_simple_fan_heuristic(
        self,
        user_text: str,
        ai_response: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Recover a simple fan power request when the LLM fails to emit a
        `fan_control` command for an obvious, short command.
        """
        if not ai_response:
            return ai_response

        commands = ai_response.get("commands") or []
        if commands:
            return ai_response

        fan_response = infer_simple_fan_command(user_text)
        if fan_response is None:
            return ai_response

        logger.info("Applied simple fan heuristic for request: %s", user_text)
        return fan_response

    async def _ensure_llm_client(self):
        """Lazy initialize LLM client based on provider setting"""
        if self.llm_client is None:
            if self.settings.app.llm_provider == "gemini":
                logger.info("Initializing Google Gemini client...")
                self.llm_client = await get_gemini_client()
            elif self.settings.app.llm_provider == "groq":
                logger.info("Initializing Groq client...")
                self.llm_client = await get_groq_client()
            else:
                logger.info("Initializing Ollama client...")
                self.llm_client = await get_ollama_client()
        return self.llm_client
    
    async def _auto_listen_for_followup(self):
        """
        Automatically listen for follow-up response without wake word
        Called when AI expects a follow-up (e.g., after asking a question)
        """
        try:
            import asyncio
            
            # Wait for TTS to finish speaking before listening
            logger.debug("Waiting for TTS to complete before auto-listen...")
            if not await self._wait_for_voice_output():
                logger.warning("Follow-up skipped because Aiden's audio has not finished")
                return
            
            # Brief pause after TTS for natural conversation flow
            await asyncio.sleep(0.3)
            
            if getattr(self, "_voice_stop_requested", False):
                return
            # Follow-ups need the same exclusive microphone handoff as wake
            # activation. TTS may have resumed the detector after its last word.
            if not await self._acquire_voice_capture():
                return
            try:
                self._is_listening = True
                success, user_text, error = await self.stt.transcribe(play_activation_sound=True)
            finally:
                self._is_listening = False
                await self._release_voice_capture()
            
            if not success:
                if error in {"non_speech", "cancelled", "No speech detected"}:
                    logger.info("No spoken follow-up; returning to standby (%s)", error)
                    return
                if error == "timeout":
                    logger.info("No follow-up response - timeout")
                    await self.context_manager.refresh_pending_clarification_grace()
                    retry_prompt = "I did not catch that. Please repeat briefly."
                    try:
                        context = await self.context_manager.get_context()
                        if context.get("pending_clarification"):
                            pending_slots = context.get("pending_slots") or []
                            if "app_name" in pending_slots:
                                retry_prompt = "I did not catch that. You can just say the app name."
                            elif "process_name" in pending_slots:
                                retry_prompt = "I did not catch that. You can just say the process name."
                            elif "song_name" in pending_slots:
                                retry_prompt = "I did not catch that. You can just say the song name."
                            elif "device_name" in pending_slots:
                                retry_prompt = "I did not catch that. You can just say the device name."
                            else:
                                retry_prompt = "I did not catch that. You can answer briefly."
                    except Exception:
                        pass
                    await self.tts.speak(retry_prompt)
                else:
                    logger.warning(f"STT failed during auto-listen: {error}")
                    await self.context_manager.refresh_pending_clarification_grace()
                return
            
            if not user_text:
                logger.warning("Empty transcription during auto-listen")
                return
            
            logger.info(f"📝 USER FOLLOW-UP: {user_text}")
            
            # Broadcast follow-up user message to dashboard
            try:
                from src.utils.websocket_broadcast import broadcast_message
                await broadcast_message("message", {
                    "role": "user",
                    "content": user_text,
                    "timestamp": __import__('datetime').datetime.now().isoformat()
                })
            except Exception:
                pass  # Non-critical
            
            # Process the follow-up message
            await self._process_user_message(user_text)
            
        except asyncio.CancelledError:
            logger.info("Auto-listen follow-up cancelled")
            raise
        except Exception as e:
            logger.error(f"Error during auto-listen: {e}", exc_info=True)
    
    async def _speak_async(self, text: str, wait: bool = False, source: str = "local"):
        """
        Wrapper to speak asynchronously without blocking - streams by sentence
        
        Args:
            text: Text to speak
            wait: If True, waits for TTS to complete
            source: Source of the request (e.g., 'local', 'web')
        """
        import asyncio
        task = asyncio.current_task()
        if task:
            self._speak_tasks.add(task)
            
        try:
            import re
            # Split text into sentences using regex, preserving punctuation
            sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+|\n+', text) if s.strip()]
            
            if not sentences:
                return

            # By queuing sentences individually, Aiden begins playing the first
            # sentence instantly while the rest are fetched in the background.
            for sentence in sentences:
                await self.tts.speak(sentence, source=source)

            if wait:
                await self.tts.wait_until_done()
                
        except asyncio.CancelledError:
            logger.info("Background TTS chunking cancelled (barge-in)")
        except Exception as e:
            logger.error(f"Background TTS error (non-critical): {e}")
        finally:
            if task:
                self._speak_tasks.discard(task)
    
    async def _enhance_response_with_feedback(
        self, 
        user_text: str, 
        original_response: str, 
        esp32_feedback: str
    ) -> Optional[str]:
        """
        Enhance AI response based on ESP32 feedback using prompts.yaml
        
        Args:
            user_text: Original user request
            original_response: AI's initial response
            esp32_feedback: Actual ESP32 response text
            
        Returns:
            Enhanced response or None if enhancement fails
        """
        try:
            llm = await self._ensure_llm_client()
            
            from src.utils.prompt_loader import get_prompt

            enhancement_template = get_prompt(
                "enhancement_prompt",
                "You are a voice assistant. Convert device responses to natural speech.",
            )
            enhancement_prompt = enhancement_template
            try:
                enhancement_prompt = enhancement_template.format(
                    user_request=user_text,
                    device_response=esp32_feedback
                )
            except Exception:
                pass
            
            # Build messages for AI - use direct API call instead of chat()
            # because chat() forces JSON response format which we don't need here
            import httpx
            
            enhancement_messages = [
                {
                    "role": "system",
                    "content": "You are a helpful voice assistant. Respond with natural speech only."
                },
                {
                    "role": "user",
                    "content": enhancement_prompt
                }
            ]
            
            # Make direct API call without JSON format requirement
            payload = {
                "model": self.settings.groq.model,
                "messages": enhancement_messages,
                "temperature": 0.3,
                "max_tokens": 50,
                # NO response_format - we want plain text response
            }
            
            headers = {
                "Authorization": f"Bearer {self.settings.groq.api_key}",
                "Content-Type": "application/json"
            }
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    json=payload,
                    headers=headers
                )
                response.raise_for_status()
                result = response.json()
                enhanced = result["choices"][0]["message"]["content"].strip()
            
            # Clean up any quotes or extra formatting
            enhanced = enhanced.strip('"\'')
            
            if enhanced and len(enhanced) > 0:
                logger.info(f"✨ Enhanced response: {enhanced}")
                return enhanced
            
            return None
            
        except Exception as e:
            logger.error(f"Error enhancing response: {e}")
            return None
    
    def _merge_command_responses(
        self,
        base_text: str,
        execution_results: List[Dict[str, Any]]
    ) -> str:
        """Append dynamic status messages from command execution to the spoken response."""
        status_messages: List[str] = []
        enriching_types = {"battery_status", "cpu_status", "gpu_status", "browser_media", "spotify", "media", "self_termination", "ups_status"}
        for result in execution_results:
            data = result.get("response_data")
            if not isinstance(data, dict):
                continue
            if data.get("type") in enriching_types:
                message = data.get("message")
                if message:
                    status_messages.append(message)
        if not status_messages:
            return base_text
        addition = " ".join(status_messages)
        return f"{base_text.strip()} {addition}".strip() if base_text else addition

    def _describe_failed_action(self, result: Dict[str, Any]) -> str:
        """Create a short, honest user-facing message for a failed command."""
        data = result.get("response_data")
        if isinstance(data, dict):
            data_type = (data.get("type") or "").strip().lower()
            message = (data.get("message") or "").strip()

            if data_type == "spotify":
                params = result.get("params") or {}
                action = (params.get("action") or "").lower()
                query = params.get("query")

                if action == "play_track" and query:
                    return f"I couldn't play {query} on Spotify."
                if action == "play_playlist" and query:
                    return f"I couldn't play the playlist {query} on Spotify."
                if action in {"play", "resume", "play_liked_songs"}:
                    return "I couldn't start Spotify playback."
                if action == "pause":
                    return "I couldn't pause Spotify."
                if action == "transfer":
                    return "I couldn't move Spotify to that device."
                return message or "I couldn't complete that on Spotify."

            if data_type == "jellyfin":
                lowered = message.casefold()
                if "viewer" in lowered or "watch progress" in lowered:
                    return "I found the show, but I couldn't tell which episode you were on. Open Jellyfin once, then ask me again."
                if "player" in lowered or "session" in lowered:
                    return "Jellyfin isn't ready yet. Open it, then try again."
                return message or "I couldn't play that in Jellyfin."

            if data_type == "browser_media":
                params = result.get("params") or {}
                action = (params.get("action") or "").lower()
                target = (params.get("target") or "browser media").replace("_", " ")

                if action in {"play", "resume", "play_pause"}:
                    return f"I couldn't control playback in {target}."
                if action == "play_track" and params.get("query"):
                    return f"I couldn't play {params.get('query')} in {target}."
                return message or f"I couldn't control {target}."

            if message:
                return message

        command = result.get("command")
        params = result.get("params") or {}

        if command == "system_command":
            action = (params.get("action") or "").lower()
            action_map = {
                "lock": "I couldn't lock your PC.",
                "shutdown": "I couldn't shut down your PC.",
                "restart": "I couldn't restart your PC.",
                "sleep": "I couldn't put the PC to sleep.",
                "hibernate": "I couldn't hibernate the PC.",
                "empty_recycle_bin": "I couldn't empty the recycle bin.",
                "clear_recycle_bin": "I couldn't empty the recycle bin.",
            }
            return action_map.get(action, "I couldn't complete that system action.")

        if command == "launch_app":
            app_name = params.get("name") or params.get("app_name") or "that app"
            return f"I couldn't open {app_name}."

        if command == "kill_process":
            process_name = params.get("name") or "that app"
            return f"I couldn't close {process_name}."

        if command == "scheduled_command":
            action = (params.get("action") or "that").lower()
            return f"I couldn't set the {action} timer."

        if command == "cancel_timer":
            return "I couldn't cancel the timer."

        if command == "shell_command":
            return "I couldn't run that command."

        if command == "media_control":
            return "I couldn't complete that media action."

        if command == "fan_control":
            return "I couldn't control the fan."

        return "I couldn't complete that action."

    def _build_failure_followup(
        self,
        execution_results: List[Dict[str, Any]]
    ) -> Optional[str]:
        """Create a follow-up line only when one or more commands failed."""
        failed = [r for r in execution_results if not r.get("success", False)]
        if not failed:
            return None

        failure_messages: List[str] = []
        for result in failed:
            message = self._describe_failed_action(result).strip()
            if message and message not in failure_messages:
                failure_messages.append(message)

        if not failure_messages:
            return "I couldn't complete that."

        if len(failed) == len(execution_results):
            return " ".join(failure_messages[:2])

        if len(failure_messages) == 1:
            return f"I completed part of that, but {failure_messages[0][0].lower()}{failure_messages[0][1:]}"

        return f"I completed part of that, but {' '.join(failure_messages[:2])}"

    def _response_after_execution(
        self,
        proposed_response: str,
        execution_results: List[Dict[str, Any]],
    ) -> str:
        """Use real command outcomes instead of a model's unverified claim."""
        if not execution_results:
            return "I couldn't confirm that action completed."
        failure = self._build_failure_followup(execution_results)
        if failure:
            return failure

        result_messages: List[str] = []
        for result in execution_results:
            data = result.get("response_data")
            if isinstance(data, dict):
                message = str(data.get("message") or "").strip()
            elif isinstance(data, str):
                message = data.strip()
            else:
                message = ""
            # The scheduler returns an internal action label such as
            # "launch_app".  The planned reply already says the useful part
            # in ordinary language, so never read that implementation detail.
            if result.get("command") == "scheduled_command" and message.casefold().startswith("timer created:"):
                continue
            if result.get("command") == "fan_control" and message.casefold().rstrip(".!") in {
                "signal sent", "toggle signal sent", "command sent", "done",
            }:
                continue
            if message and message not in result_messages:
                result_messages.append(message)

        if len(execution_results) == 1 and result_messages:
            return result_messages[0]

        response = (proposed_response or "").strip()
        if _is_capability_refusal(response):
            response = "Done."
        if not response:
            response = "Done."
        # The proposed response already combines all requested actions in the
        # user's language. Tool messages such as "Starting Spotify playback"
        # are per-command status strings, not extra spoken replies.
        return response

    async def _localized_failure_reply(
        self,
        llm: Any,
        user_text: str,
        proposed_response: str,
        execution_results: List[Dict[str, Any]],
        fallback: str,
    ) -> str:
        """Naturalize a mixed result without losing a failed action."""
        outcomes = []
        for result in execution_results:
            params = result.get("params") or {}
            success = bool(result.get("success"))
            outcomes.append({
                "command": result.get("command"),
                "action": params.get("action") or params.get("operation"),
                "target": params.get("target"),
                "duration_seconds": params.get("duration_seconds"),
                "success": success,
                "failure": None if success else self._describe_failed_action(result),
            })

        try:
            result = await llm.chat([
                {"role": "system", "content": (
                    "Write one short, natural spoken reply in the user's language. "
                    "Use only the actual execution outcomes provided. Say which action failed "
                    "and which succeeded; never say a failed action succeeded. "
                    "Avoid raw tool status phrases. Return JSON with commands: [] and the reply in response."
                )},
                {"role": "user", "content": json.dumps({
                    "request": user_text,
                    "draft_reply": proposed_response,
                    "outcomes": outcomes,
                }, ensure_ascii=False)},
            ])
            if isinstance(result, dict) and result.get("commands") == []:
                reply = result.get("response")
                if isinstance(reply, str) and reply.strip():
                    return reply.strip()
        except Exception as exc:
            logger.warning("Could not localize partial action result: %s", exc)
        return fallback
    
    async def handle_voice_activation(
        self,
        from_hotkey: bool = False,
        wake_detection: Optional[WakeDetection] = None,
        source: str = "local",
    ):
        """
        Handle voice activation (wake word or hotkey)
        Complete flow: Listen -> Understand -> Execute -> Respond
        
        Args:
            from_hotkey: True if activated via hotkey (plays activation sound)
        """
        import asyncio
        
        import time as _time
        _t0 = _time.monotonic()
        self._activation_started_at = _t0

        # BARGE-IN: Cancel the main conversation task if one is currently processing
        if self._current_request_task and not self._current_request_task.done():
            logger.warning("Barge-in: Cancelling old request context")
            self.request_immediate_stop()
            previous_request = self._current_request_task
            previous_request.cancel()
            await asyncio.gather(previous_request, return_exceptions=True)
            
        self._current_request_task = asyncio.current_task()
        self._voice_stop_requested = False
            
        # BARGE-IN: Cancel any currently downloading TTS sentences
        for task in list(self._speak_tasks):
            if not task.done():
                task.cancel()
        self._speak_tasks.clear()
        
        # BARGE-IN: Stop any currently playing audio instantly
        self.tts.stop()

        self.is_processing = True

        # The wake detector releases its PortAudio stream on another thread.
        # Wait for that handoff before reopening STT so the first command does
        # not land on a stale/silent stream after a long idle period.
        if not await self._acquire_voice_capture():
            self.is_processing = False
            from src.utils.websocket_broadcast import broadcast_voice_status
            await broadcast_voice_status("idle", speaking=False, active=False, source=source)
            return

        from src.utils.websocket_broadcast import broadcast_voice_status

        duck_state = None

        try:
            # Prepare media ducking before the mic-open cue so STT can start as soon
            # as the sound finishes instead of doing this work afterward.
            try:
                from src.media.media_router import get_media_router
                duck_state = await get_media_router().duck_for_listening()
            except Exception as exc:
                logger.debug(f"STT media ducking unavailable before activation cue: {exc}")

            captured_command = self._should_use_buffered_command(
                from_hotkey,
                wake_detection,
            )
            if captured_command:
                # Audio is already complete, so this is a confirmation rather than
                # a speak-now cue. Do not publish a misleading listening state.
                await self._play_continuous_command_confirmation()
            else:
                # Refresh the USB capture stream *before* the cue. A stream that
                # has been idle for a long time can appear open yet return silence.
                # The activation sound must mean the fresh microphone is already
                # ready, never that it is about to be opened.
                mic_ready = await asyncio.to_thread(self.stt.refresh_microphone)
                if not mic_ready:
                    logger.warning("STT microphone refresh failed; attempting normal listen")
                elif not from_hotkey:
                    # Keep the friendly acknowledgement before the speak-now
                    # cue. STT's readiness check clears its speaker echo before
                    # capture is armed; the beep itself never contains voice.
                    await self._play_wake_acknowledgement()
            # ── Step 1: STT ──────────────────────────────────────────────
            _t_stt_start = _time.monotonic()
            if captured_command and wake_detection is not None:
                success, user_text, error = await self.stt.transcribe_captured_pcm(
                    wake_detection.command_audio or b"",
                )
                if not success:
                    logger.info(
                        "Buffered wake command unavailable (%s); falling back to normal listening",
                        error,
                    )
                    mic_ready = await asyncio.to_thread(self.stt.refresh_microphone)
                    if not mic_ready:
                        logger.warning("STT microphone refresh failed; attempting normal listen")
                    self._is_listening = True
                    success, user_text, error = await self.stt.transcribe(
                        play_activation_sound=False,
                        duck_state=duck_state,
                        media_already_ducked=True,
                        restore_media=False,
                        request_source=source,
                        ready_cue=lambda: self._play_activation_ready_cue(from_hotkey=False),
                    )
                    self._is_listening = False
            else:
                self._is_listening = True
                success, user_text, error = await self.stt.transcribe(
                    play_activation_sound=False,
                    duck_state=duck_state,
                    media_already_ducked=True,
                    restore_media=False,
                    request_source=source,
                    ready_cue=lambda: self._play_activation_ready_cue(from_hotkey),
                )
                self._is_listening = False

            # Some USB audio drivers produce one silent capture immediately
            # after an extended idle period, even though wake-word detection
            # worked. Reopen the stream once and keep listening without
            # requiring the user to say "Hey Aiden" again.
            if not success and should_retry_listen_after_idle(error):
                logger.info("STT first capture was silent; rearming microphone for one recovery listen")
                await asyncio.to_thread(self.stt.refresh_microphone)
                self._is_listening = True
                success, user_text, error = await self.stt.transcribe(
                    play_activation_sound=False,
                    duck_state=duck_state,
                    media_already_ducked=True,
                    restore_media=False,
                    request_source=source,
                    ready_cue=lambda: self._play_activation_ready_cue(from_hotkey=False),
                )
                self._is_listening = False
            logger.info("[TIMING] STT: %.0f ms", (_time.monotonic() - _t_stt_start) * 1000)
            
            # Start conversation in background while user was speaking
            if not self.context_manager.current_conversation_id:
                conversation_id = await self.context_manager.start_conversation(mode="voice")
            
            if not success:
                await broadcast_voice_status("idle", speaking=False, active=False, source=source)
                if error == "timeout":
                    logger.info("No speech detected - timeout")
                elif error == "cancelled":
                    logger.info("Voice listening cancelled by user hotkey")
                elif error == "non_speech":
                    logger.info("Ignoring cue/noise recognition; returning to standby")
                else:
                    logger.warning(f"STT failed: {error}")
                    await self.tts.speak("Sorry, I didn't catch that.", source=source)
                return
            
            if not user_text:
                logger.warning("Empty transcription")
                await broadcast_voice_status("idle", speaking=False, active=False, source=source)
                return
            
            # Capture is complete; release the device so a new wake phrase can
            # interrupt background AI work instead of waiting for the reply.
            await self._release_voice_capture()
            logger.info(f"USER: {user_text}")
            
            # Broadcast user message to dashboard
            try:
                from src.utils.websocket_broadcast import broadcast_message
                await broadcast_message("message", {
                    "role": "user",
                    "content": user_text,
                    "source": source,
                    "timestamp": __import__('datetime').datetime.now().isoformat()
                })
            except Exception:
                pass  # Non-critical
            
            # Broadcast processing status
            await broadcast_voice_status("processing", speaking=False, active=True, source=source)
            
            # ── Step 2: AI ───────────────────────────────────────────────
            _t_ai_start = _time.monotonic()
            await self._process_user_message(user_text, source=source)
            logger.info("[TIMING] AI+TTS queue: %.0f ms | Total wall: %.0f ms",
                        (_time.monotonic() - _t_ai_start) * 1000,
                        (_time.monotonic() - _t0) * 1000)
            
        except asyncio.CancelledError:
            logger.info("Voice activation cancelled by user")
        except Exception as e:
            logger.error(f"Error handling voice activation: {e}", exc_info=True)
            await self.tts.speak("Sorry, something went wrong.", source=source)
            # Broadcast idle status on error
            await broadcast_voice_status("idle", speaking=False, active=False, source=source)
        finally:
            # Wake detection owns the microphone while idle. Do not leave an
            # STT stream open for hours until the next wake-word handoff.
            try:
                await asyncio.to_thread(self.stt.close)
            except Exception as exc:
                logger.warning("Could not release STT microphone after voice turn: %s", exc)
            if duck_state is not None:
                try:
                    from src.media.media_router import get_media_router
                    # The media state belongs to this whole voice interaction,
                    # not just microphone capture.  Keeping it paused until
                    # the queued reply is audible prevents music from fighting
                    # Aiden's response and reliably resumes only what Aiden
                    # paused once the interaction is complete.
                    try:
                        if not getattr(self, "_voice_stop_requested", False):
                            await self._wait_for_voice_output()
                    finally:
                        await get_media_router().restore_after_listening(duck_state)
                except Exception as exc:
                    logger.debug(f"Voice interaction media restore skipped: {exc}")
            from src.media.audio_session_ducker import get_audio_session_ducker
            get_audio_session_ducker().restore_all()
            self._is_listening = False
            self.is_processing = False
            # Broadcast idle status when conversation ends
            await broadcast_voice_status("idle", speaking=False, active=False, source=source)
            logger.info("=" * 60)
            
            # CRITICAL: Resume wake word detector at the end of voice activation
            # ONLY if no TTS speech is currently playing or queued (if queued, TTS queue will handle resume)
            try:
                if self.tts.audio_queue.empty() and not getattr(self.tts, "is_processing", False):
                    from src.core.wake_word_manager import get_wake_word_manager
                    ww_manager = get_wake_word_manager()
                    if ww_manager and ww_manager.get_state():
                        if ww_manager.detector:
                            ww_manager.detector.resume()
            except Exception as e:
                logger.debug(f"Could not resume wake word detector: {e}")

    async def _acquire_voice_capture(self) -> bool:
        """Pause wake detection and prove it released the shared microphone."""
        from src.core.wake_word_manager import get_wake_word_manager
        manager = get_wake_word_manager()
        detector = manager.detector if manager else None
        if detector is None:
            return True
        try:
            detector.pause()
            wait_for_release = getattr(detector, "wait_until_stream_released", None)
            if callable(wait_for_release):
                if not await asyncio.to_thread(wait_for_release, 5.0):
                    logger.error("Wake-word microphone did not release; listening aborted before cue")
                    detector.resume()
                    return False
            return True
        except asyncio.CancelledError:
            detector.resume()
            raise
        except Exception:
            logger.exception("Wake-word microphone handoff failed; listening aborted before cue")
            detector.resume()
            return False

    async def _release_voice_capture(self) -> None:
        """Return microphone ownership to wake detection during AI work."""
        await asyncio.to_thread(self.stt.close)
        from src.core.wake_word_manager import get_wake_word_manager
        manager = get_wake_word_manager()
        if manager and manager.get_state() and manager.detector:
            manager.detector.resume()

    async def _wait_for_voice_output(self) -> bool:
        """Wait for background response generation and queued playback to end."""
        # _process_user_message intentionally starts some replies in the
        # background. Yielding once lets those tasks register themselves before
        # inspecting the set, preventing a queue-empty race that could resume
        # music before the reply has even been generated.
        await asyncio.sleep(0)
        current_task = asyncio.current_task()
        speak_tasks = [
            task for task in self._speak_tasks
            if task is not current_task and not task.done()
        ]
        if speak_tasks:
            _, pending = await asyncio.wait(speak_tasks, timeout=60.0)
            if pending:
                logger.warning("Timed out waiting for response generation before media restore.")

        return await self.tts.wait_until_done(timeout=60.0)

    def request_immediate_stop(self) -> bool:
        """Best-effort synchronous stop for hotkey threads."""
        cancelled = False
        self._voice_stop_requested = True

        if self._is_listening:
            self.stt.request_stop()
            cancelled = True

        self.tts.stop_playback_now()
        return cancelled

    async def cancel_active_listening(self) -> bool:
        """Stop an active STT listen or current request pipeline."""
        cancelled = self.request_immediate_stop()

        if self._is_listening:
            logger.info("Cancelling active STT listen")

        if self._current_request_task and not self._current_request_task.done():
            logger.info("Cancelling active assistant request task")
            self._current_request_task.cancel()
            cancelled = True

        for task in list(self._speak_tasks):
            if not task.done():
                task.cancel()
                cancelled = True

        # Stop must immediately release Aiden's mutes even if capture was
        # cancelled before its per-listen state was returned.
        from src.media.audio_session_ducker import get_audio_session_ducker
        get_audio_session_ducker().restore_all()

        if cancelled:
            try:
                await self.tts.play_sound_now("stopped")
            except Exception as e:
                logger.debug(f"Could not play stopped sound: {e}")

        return cancelled
    
    async def handle_text_message(self, text: str, source: str = "local", client_message_id: Optional[str] = None) -> str:
        """
        Handle text-based message (from dashboard/API)
        
        Args:
            text: User's text message
            source: Where the message came from ('local' or 'web')
            
        Returns:
            Assistant's response text
        """
        from src.utils.websocket_broadcast import broadcast_voice_status, broadcast_message
        try:
            logger.info(f"TEXT MESSAGE: {text} (source: {source})")
            if not self.context_manager.current_conversation_id:
                await self.context_manager.start_conversation(mode="text")
            await broadcast_message("message", {
                "role": "user",
                "content": text,
                "source": source,
                "client_message_id": client_message_id,
                "timestamp": __import__('datetime').datetime.now().isoformat(),
            })
            
            # Broadcast processing status so the UI knows we're thinking
            if source != "web_text":
                await broadcast_voice_status("processing", speaking=False, active=True, source=source)
            
            # Process with AI
            options = {"client_message_id": client_message_id} if client_message_id else {}
            response = await self._process_user_message(text, source=source, **options)
            
            # Note: tts.speak (inside _process_user_message) will broadcast "speaking" and then "idle"
            # But if it didn't speak (e.g. error or silent), we ensure it returns to idle here.
            # However, since tts.speak might take time, we only broadcast idle if we aren't speaking.
            # For safety, let the TTS handle the "idle" broadcast when it finishes, 
            # unless an error occurred.
            
            return response
            
        except Exception as e:
            logger.error(f"Error handling text message: {e}", exc_info=True)
            if source != "web_text":
                await broadcast_voice_status("idle", speaking=False, active=False, source=source)
            return "Sorry, something went wrong."
    
    @staticmethod
    def _is_unhelpful_question_response(ai_response: Dict[str, Any]) -> bool:
        """
        Dynamically check if the AI returned a dead-end refusal or deferral phrase for a question
        without providing any executable commands.
        """
        if (
            not ai_response
            or ai_response.get("commands")
            or ai_response.get("intent") in {"command", "multi_command", "system_command"}
        ):
            return False
        
        response_text = (ai_response.get("response") or "").strip().lower()
        if not response_text:
            return True
            
        # Generalized regex patterns matching structural meta-refusal or deferral semantics
        meta_refusal_patterns = [
            r"\b(can'?t|cannot|unable|don'?t have|do not have|no access|not able)\b.*\b(provide|summary|summaries|answer|look|search|access|info|detail|details)\b",
            r"\b(let me|i'll|i can|i will)\s+(look|check|search)\b",
            r"\b(look|check|search)\s+(that|this|it)\s+up\b",
            r"\b(give|allow)\s+me\s+a\s+(moment|second|minute)\b",
            r"\b(as an ai|language model)\b",
        ]
        return any(re.search(pat, response_text) for pat in meta_refusal_patterns)

    def _build_search_fallback_response(self, user_text: str) -> Dict[str, Any]:
        """
        Dynamically build a Google Search shell command response when AI fails to answer a question.
        """
        import urllib.parse
        encoded_query = urllib.parse.quote_plus(user_text)
        search_cmd = f'start "" "https://www.google.com/search?q={encoded_query}"'
        return {
            "is_followup": False,
            "intent": "question",
            "commands": [{"type": "shell_command", "params": {"command": search_cmd}}],
            "response": f"Searching Google for {user_text}...",
            "update_context": True,
            "expecting_followup": False,
        }

    async def _process_user_message(self, user_text: str, source: str = "local", client_message_id: Optional[str] = None) -> str:
        """
        Core message processing logic with 2-pass AI system:
        Pass 1: AI decides what context it needs
        Pass 2: AI gets the context and responds
        
        Args:
            user_text: User's message
            source: Where the message came from ('local' or 'web')
            
        Returns:
            Assistant's response text
        """
        try:
            # Get conversation context
            plan_started_at = time.perf_counter()
            context = await self.context_manager.get_context()

            llm = await self._ensure_llm_client()

            # --- Fast path: skip Pass 1 for requests that obviously don't need system context ---
            # This saves a full LLM round trip (~300-800 ms) for the majority of commands.
            if self._no_context_needed(user_text, context):
                logger.info("⚡ Pass 1 skipped (local classifier: no system context needed)")
                messages_direct = await self.context_manager.build_messages(
                    user_text, context, needs_context=[]
                )
                ai_response = await llm.chat(messages_direct)
                if not ai_response:
                    logger.error(f"Empty response from {self.settings.app.llm_provider.upper()} AI (direct)")
                    response_text = "Sorry, I couldn't process that."
                    if source != "web_text":
                        await self.tts.speak(response_text, source=source)
                    return response_text
                needs_context = []
            else:
                # PASS 1: Ask AI what context it needs (lightweight, no system context)
                logger.info("🧠 Pass 1: AI analyzing request...")
                messages_pass1 = await self.context_manager.build_messages(user_text, context, needs_context=None)
                ai_response_pass1 = await llm.chat(messages_pass1)

                if not ai_response_pass1:
                    logger.error(f"Empty response from {self.settings.app.llm_provider.upper()} AI (Pass 1)")
                    response_text = "Sorry, I couldn't process that."
                    if source != "web_text":
                        await self.tts.speak(response_text, source=source)
                    return response_text

                needs_context = ai_response_pass1.get("needs_context", [])

                if needs_context:
                    # PASS 2: Provide requested context and get final response
                    logger.info(f"🧠 Pass 2: Fetching {needs_context} and re-processing...")
                    messages_pass2 = await self.context_manager.build_messages(
                        user_text, context, needs_context=needs_context
                    )
                    ai_response = await llm.chat(messages_pass2)
                    if not ai_response:
                        logger.warning("Pass 2 failed, using Pass 1 response")
                        ai_response = ai_response_pass1
                else:
                    logger.info("✅ No additional context needed")
                    ai_response = ai_response_pass1

            if needs_context and "running_processes" in needs_context:
                ai_response = await self._maybe_apply_vague_close_heuristic(
                    user_text, needs_context, ai_response
                )

            ai_response = self._maybe_apply_simple_fan_heuristic(user_text, ai_response)

            # Dynamic Safeguard for Question Refusals & Placeholders:
            # Step 1: Attempt dynamic re-prompt if response is an unhelpful refusal/deferral.
            if self._is_unhelpful_question_response(ai_response):
                logger.warning(
                    "Unhelpful/refusal response detected ('%s'). Re-prompting AI for direct knowledge answer...",
                    ai_response.get("response")
                )
                retry_messages = await self.context_manager.build_messages(
                    user_text + " (Answer directly with factual information or plot details. If uncertain, emit a shell_command with Google Search.)",
                    context,
                    needs_context=needs_context
                )
                retry_ai_response = await llm.chat(retry_messages)
                if retry_ai_response and not self._is_unhelpful_question_response(retry_ai_response):
                    logger.info("Successfully recovered direct response on retry: %s", retry_ai_response.get("response"))
                    ai_response = retry_ai_response
                else:
                    # Step 2: If LLM still fails to answer, dynamically fall back to opening Google Search
                    logger.warning("AI failed to provide an answer on retry. Dynamically falling back to Google Search.")
                    ai_response = self._build_search_fallback_response(user_text)

            if _needs_action_repair(user_text, ai_response):
                logger.warning("AI action plan contradicted its response; requesting one corrected plan")
                repair_messages = await self.context_manager.build_messages(
                    user_text, context, needs_context=needs_context
                )
                repair_messages.append({
                    "role": "system",
                    "content": (
                        "Re-evaluate the user's action request and return one consistent JSON plan. "
                        "Available media_control targets include Jellyfin and Spotify. "
                        "Treat an obvious speech-to-text spelling error in a provider name as that provider. "
                        "If a title and provider are clear, emit the playback command rather than a capability disclaimer. "
                        "Set expecting_followup only when a required detail is genuinely missing. "
                        "Do not claim an action succeeded or failed; the application will report the tool result."
                    ),
                })
                repaired_response = await llm.chat(repair_messages)
                if repaired_response:
                    original_commands = _validated_ai_commands(ai_response.get("commands"))
                    repaired_commands = _validated_ai_commands(repaired_response.get("commands"))
                    if repaired_commands or not original_commands:
                        ai_response = repaired_response
                    else:
                        # A retry must not erase a complete action the first
                        # pass found. Execution will supply the final answer.
                        logger.warning("AI repair omitted a runnable command; keeping the original plan")
                        ai_response = {
                            **ai_response,
                            "response": "I'll try that now.",
                            "expecting_followup": False,
                        }

            # AI decides first. If it still misses a plainly specified local
            # title/provider after the repair pass, use the typed media action
            # as a narrow recovery path, not a free-form shell command.
            jellyfin_title = extract_jellyfin_movie_request(user_text)
            if (
                jellyfin_title
                and _has_explicit_jellyfin_provider(user_text)
                and not _has_jellyfin_play_command(_validated_ai_commands(ai_response.get("commands")))
            ):
                logger.warning("AI missed explicit Jellyfin playback after repair; using media action fallback")
                ai_response = {
                    **ai_response,
                    "intent": "command",
                    "commands": [{
                        "type": "media_control",
                        "params": {"action": "play_title", "target": "jellyfin", "query": jellyfin_title},
                    }],
                    "response": f"I'll try {jellyfin_title} on Jellyfin.",
                    "expecting_followup": False,
                    "needs_context": [],
                }

            # Parse AI response
            intent = ai_response.get("intent", "unknown")
            raw_commands = ai_response.get("commands", [])
            commands = _validated_ai_commands(raw_commands)
            commands = _repair_youtube_search_request(user_text, commands)
            response_text = str(ai_response.get("response") or "Done.")
            update_context = ai_response.get("update_context", True)
            if isinstance(raw_commands, list) and len(commands) < len(raw_commands):
                logger.warning("Rejected %d incomplete AI command(s)", len(raw_commands) - len(commands))
                if not commands:
                    if not str(response_text).strip().endswith("?"):
                        response_text = "What details should I use for that action?"
                    ai_response["expecting_followup"] = True

            commands, delayed_reply = _keep_delayed_close_as_one_action(user_text, commands)
            if delayed_reply:
                response_text = delayed_reply
                ai_response["expecting_followup"] = False
                logger.warning("Corrected a split or mistimed delayed-close plan")
            commands, correction_reply = _keep_spotify_correction_as_one_action(user_text, commands)
            if correction_reply:
                response_text = correction_reply
                ai_response["expecting_followup"] = False
                logger.info("Using the final spoken Spotify correction as one action")
            contextual_commands = _repair_contextual_media_request(user_text, commands)
            if contextual_commands != commands:
                commands = contextual_commands
                response_text = "I'll control the current player."
                ai_response["expecting_followup"] = False
            
            logger.info(f"AI INTENT: {intent}")
            logger.info(f"AI COMMANDS: {len(commands)}")
            logger.info(f"AI RESPONSE: {response_text}")
            logger.info("[TIMING] Context + AI plan: %.0f ms",
                        (time.perf_counter() - plan_started_at) * 1000)

            expecting_followup = ai_response.get("expecting_followup", False)

            # A follow-up question can coexist with an executable command
            # (e.g. "open Chrome, and what else?"). Do not discard the command.
            if commands:
                try:
                    from src.utils.websocket_broadcast import broadcast_message
                    for cmd in commands:
                        await broadcast_message("message", {
                            "role": "action",
                            "action": cmd,
                            "timestamp": __import__('datetime').datetime.now().isoformat()
                        })
                except Exception as e:
                    logger.error(f"Failed to broadcast actions: {e}")

                execution_results = await self.executor.execute_multiple(commands)
                for result in execution_results:
                    if not result.get("success", False):
                        logger.warning(
                            "Command failed (%s): %s",
                            result.get("command"),
                            result.get("error") or result.get("response_data"),
                        )
                response_text = self._response_after_execution(response_text, execution_results)

                if len(execution_results) > 1 and any(not result.get("success") for result in execution_results):
                    response_text = await self._localized_failure_reply(
                        llm, user_text, str(ai_response.get("response") or ""),
                        execution_results, response_text,
                    )

                if len(execution_results) == 1 and execution_results[0].get("success"):
                    fan_result = execution_results[0]
                    if fan_result.get("command") == "fan_control" and fan_result.get("response_data"):
                        deterministic_fan_response = build_fan_spoken_response(fan_result["response_data"])
                        if deterministic_fan_response:
                            response_text = deterministic_fan_response

            # Present the verified outcome once, after the action has run.
            ai_response["commands"] = commands
            ai_response["response"] = response_text
            try:
                from src.utils.websocket_broadcast import broadcast_message
                await broadcast_message("message", {
                    "role": "assistant",
                    "source": source,
                    "client_message_id": client_message_id,
                    "content": response_text,
                    "timestamp": __import__('datetime').datetime.now().isoformat(),
                })
            except Exception:
                pass

            if source != "web_text":
                if commands or expecting_followup:
                    await self._speak_async(response_text, source=source)
                else:
                    asyncio.create_task(self._speak_async(response_text, source=source))
            
            # Update context if needed
            if update_context:
                context_started_at = time.perf_counter()
                await self.context_manager.update_context(
                    user_message=user_text,
                    ai_response=ai_response
                )
                logger.info("[TIMING] Conversation context save: %.0f ms",
                            (time.perf_counter() - context_started_at) * 1000)
            
            # Let AI decide if we should continue listening
            if expecting_followup:
                logger.info("🔄 AI expects follow-up")
                if source == "local":
                    logger.info("Auto-listening for response on local microphone...")
                    await self._auto_listen_for_followup()
                else:
                    logger.info("Source is web - skipping local microphone auto-listen.")
            else:
                logger.info("✅ Conversation complete - no follow-up expected")
                # Conversation stays active for 5 minutes (Redis TTL handles cleanup)
            
            return response_text
            
        except asyncio.CancelledError:
            logger.info("User message processing cancelled")
            raise
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            response_text = "Sorry, I encountered an error."
            if source != "web_text":
                await self.tts.speak(response_text, source=source)
            return response_text
    
    async def greet_user(self):
        """Greet the user on startup"""
        try:
            greeting = f"Hello {self.user_name}, Aiden is ready!"
            logger.info(f"GREETING: {greeting}")
            
            # Play startup sound
            await self.tts.play_sound("startup")
            
            # Speak greeting
            await self.tts.speak(greeting)
            
        except Exception as e:
            logger.error(f"Error greeting user: {e}")

    # ------------------------------------------------------------------
    # Pass-1 bypass classifier
    # ------------------------------------------------------------------

    def _no_context_needed(self, user_text: str, context: dict) -> bool:
        """
        Local heuristic: returns True when the request obviously doesn't need
        system context (running_processes / installed_apps) from the OS.

        When this returns True we skip Pass 1 entirely and send the request
        straight to Pass 2 with needs_context=[], saving one full LLM round
        trip (~300–800 ms depending on model/network).

        Conservative: when in doubt we return False and let Pass 1 decide.
        """
        import re

        # Never skip when the AI is expecting a follow-up answer — that turn
        # may need context to resolve a pending slot (e.g. "close which app?")
        if context.get("expecting_followup") or context.get("pending_clarification"):
            return False

        text = user_text.lower().strip()

        # Patterns that never need OS process / app lists:
        _SIMPLE_PATTERNS = (
            # Greetings / chitchat
            r"^(hi|hello|hey|good (morning|afternoon|evening|night))[\s!?.]*$",
            r"^(thank(s| you)|thanks!?)[\s!?.]*$",
            r"^(how are you|what('s| is) up)[\s!?.]*$",
            # Time / date
            r"\b(what('s| is)?\s+the\s+)?(time|date|day|month|year)\b",
            # Fan / oscillation / UPS — all handled by deterministic heuristics already
            r"\b(fan|oscillat|swing|rotate)\b",
            r"\b(turn (on|off) the fan)\b",
            r"\b(ups|power|battery (status|level)?)\b",
            # Timers / alarms / reminders (no app lookup needed)
            r"\b(set (a |an )?(timer|alarm|reminder)|remind me)\b",
            # Volume (system volume, no process lookup)
            r"\b(volume|mute|unmute)\b",
            # Weather
            r"\b(weather|forecast|temperature outside|rain|snow|humid)\b",
            # Jokes / facts / trivia (pure LLM)
            r"\b(tell me (a )?joke|fun fact|trivia|what is|who is|when (was|did|is|are))\b",
            # Arithmetic / conversions
            r"\b(calc(ulate)?|how many|convert|what('s| is) \d+)\b",
            # Simple smart home that doesn't need process lists
            r"\b(light(s)?|lamp|dimmer|bulb|switch)\b",
        )

        for pattern in _SIMPLE_PATTERNS:
            if re.search(pattern, text):
                logger.debug(f"[FAST-PATH] Skipping Pass 1 — matched no-context pattern: {pattern!r}")
                return True

        return False


# Global instance
_assistant: Optional[AidenAssistant] = None


async def get_assistant() -> AidenAssistant:
    """Get or create global assistant instance"""
    global _assistant
    if _assistant is None:
        _assistant = AidenAssistant()
    return _assistant


def reset_assistant() -> None:
    global _assistant
    _assistant = None
