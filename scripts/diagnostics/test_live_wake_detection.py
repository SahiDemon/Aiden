"""Measure live Aiden wake-word recall with user-confirmed trials.

This tool saves scores and results, but never saves microphone audio. Stop the
main Aiden process before running it so both processes do not compete for the
same USB microphone.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import msvcrt


# Direct execution from ``scripts/diagnostics`` does not put the repository
# root on Python's import path. Add it so the documented command works from
# any current directory.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _read_choice(valid: set[str]) -> str:
    """Wait for one of the requested console keys, case-insensitively."""
    while True:
        key = msvcrt.getwch().lower()
        if key == "\x03":
            return "q"
        if key in valid:
            return key


def _beep() -> None:
    try:
        import winsound

        winsound.MessageBeep(winsound.MB_OK)
    except Exception:
        print("\a", end="", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Press Space, say Aiden once, and measure whether it was detected."
    )
    parser.add_argument("--trials", type=int, default=15)
    parser.add_argument("--window", type=float, default=4.0)
    parser.add_argument("--phrase", default="Aiden")
    parser.add_argument("--profile", default=".local/wake-word/profile.json")
    parser.add_argument("--output", default=".local/wake-word/live-recall-report.json")
    args = parser.parse_args()

    if args.trials < 1:
        raise SystemExit("--trials must be at least 1")
    if args.window <= 0:
        raise SystemExit("--window must be positive")

    profile = Path(args.profile).resolve()
    if not profile.exists():
        raise SystemExit(f"Calibration profile is missing: {profile}")

    # Settings must be configured before importing the detector singleton data.
    os.environ["SPEECH_OWW_PROFILE_PATH"] = str(profile)
    os.environ["SPEECH_OWW_SHADOW_MODE"] = "false"
    os.environ["SPEECH_OWW_CAPTURE_DIAGNOSTICS"] = "false"
    os.environ["SPEECH_OWW_CONTINUATION_WINDOW_MS"] = "0"

    from src.speech.openwakeword_wake import OpenWakeWordDetector
    from src.speech.wake_detection import WakeDetection

    events: list[dict] = []
    score_events: list[dict] = []
    event_lock = threading.Lock()

    def on_detection(detection: WakeDetection) -> None:
        with event_lock:
            events.append(
                {
                    "observed_at": time.monotonic(),
                    "timestamp": detection.timestamp,
                    "model": detection.model_name,
                    "confidence": round(detection.confidence, 4),
                    "metadata": detection.metadata,
                }
            )

    detector = OpenWakeWordDetector(callback=on_detection)
    detector.capture_diagnostics = False
    detector.shadow_mode = False
    detector.continuation_window_ms = 0

    # The production callback is intentionally sparse: it only receives a
    # completed activation. For diagnosis we also retain the best *in-memory*
    # score in every user-confirmed trial, so a miss can be attributed to the
    # model/verifier rather than guessed from an absent callback. No audio is
    # stored or written anywhere.
    original_apply_verifier = detector._apply_personal_verifier

    def capture_score(model_name: str, base_score: float):
        score, verifier_score = original_apply_verifier(model_name, base_score)
        with event_lock:
            score_events.append(
                {
                    "observed_at": time.monotonic(),
                    "model": model_name,
                    "base_score": round(base_score, 4),
                    "verifier_score": (
                        round(verifier_score, 4) if verifier_score is not None else None
                    ),
                    "score": round(score, 4),
                }
            )
        return score, verifier_score

    detector._apply_personal_verifier = capture_score
    detector.start()

    confirmed_trials: list[dict] = []
    discarded_trials = 0

    try:
        if not detector.wait_until_ready(timeout=25.0):
            detail = getattr(detector, "_startup_error", None) or "unknown startup error"
            raise SystemExit(f"Wake model or microphone did not become ready: {detail}")

        print("\nAiden live wake-word recall test")
        print(f"Phrase: {args.phrase!r} | Confirmed trials: {args.trials}")
        print("No microphone audio will be saved.")
        print("\nFor each trial: press SPACE, wait for the beep, then say the phrase ONCE.")
        print("After the result, press Y if you really spoke it, or R to discard/retry.")
        print("Press Q at a ready prompt to finish early.\n")

        while len(confirmed_trials) < args.trials:
            number = len(confirmed_trials) + 1
            print(f"Trial {number}/{args.trials}: SPACE=start, Q=finish > ", end="", flush=True)
            choice = _read_choice({" ", "q"})
            print()
            if choice == "q":
                break

            # Isolate this utterance from scores and debounce left by anything
            # heard while the user was waiting at the prompt.
            with event_lock:
                first_event = len(events)
                first_score = len(score_events)
            detector._score_history.clear()
            detector._last_trigger_time = time.monotonic() - detector.debounce

            print(f"  BEEP — say {args.phrase!r} once now...", flush=True)
            # Include the cue itself in the window. This avoids falsely
            # recording a prompt response as a miss when it begins immediately
            # after the Windows beep returns.
            started = time.monotonic()
            _beep()
            deadline = started + args.window
            while time.monotonic() < deadline:
                time.sleep(0.04)

            with event_lock:
                trial_events = [
                    event.copy()
                    for event in events[first_event:]
                    if started <= event["observed_at"] <= deadline
                ]
                trial_scores = [
                    score.copy()
                    for score in score_events[first_score:]
                    if started <= score["observed_at"] <= deadline
                ]

            best_score = max(trial_scores, key=lambda score: score["score"], default=None)

            if trial_events:
                best = max(trial_events, key=lambda event: event["confidence"])
                metadata = best.get("metadata") or {}
                print(
                    "  DETECTED "
                    f"score={best['confidence']:.3f} "
                    f"base={metadata.get('base_score', 'n/a')} "
                    f"verifier={metadata.get('verifier_score', 'n/a')}"
                )
            else:
                best = None
                if best_score:
                    print(
                        "  MISSED "
                        f"best_score={best_score['score']:.3f} "
                        f"base={best_score['base_score']:.3f} "
                        f"verifier={best_score['verifier_score']}"
                    )
                else:
                    print("  MISSED — no model scores inside the test window")

            print("  Did you actually say it clearly? Y=yes, R=discard/retry, Q=finish > ", end="", flush=True)
            confirmation = _read_choice({"y", "r", "q"})
            print()
            if confirmation == "q":
                break
            if confirmation == "r":
                discarded_trials += 1
                print("  Trial discarded.\n")
                continue

            confirmed_trials.append(
                {
                    "trial": number,
                    "phrase": args.phrase,
                    "detected": best is not None,
                    "confidence": best["confidence"] if best else None,
                    "model": best["model"] if best else None,
                    "metadata": best.get("metadata") if best else None,
                    "best_model_score": best_score,
                }
            )
            hits = sum(trial["detected"] for trial in confirmed_trials)
            recall = hits / len(confirmed_trials)
            print(f"  Running recall: {hits}/{len(confirmed_trials)} ({recall:.1%})\n")
    except KeyboardInterrupt:
        print("\nStopped early.")
    finally:
        detector.stop()

    hits = sum(trial["detected"] for trial in confirmed_trials)
    misses = len(confirmed_trials) - hits
    recall = hits / len(confirmed_trials) if confirmed_trials else 0.0
    report = {
        "version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "profile": str(profile),
        "phrase": args.phrase,
        "requested_trials": args.trials,
        "confirmed_trials": len(confirmed_trials),
        "discarded_trials": discarded_trials,
        "hits": hits,
        "misses": misses,
        "recall": round(recall, 4),
        "completed": len(confirmed_trials) == args.trials,
        "raw_audio_saved": False,
        "trials": confirmed_trials,
    }

    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Result: {hits}/{len(confirmed_trials)} detected ({recall:.1%})")
    print(f"Misses: {misses} | Discarded: {discarded_trials}")
    print(f"Report saved to: {output}")
    return 0 if confirmed_trials and misses == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
