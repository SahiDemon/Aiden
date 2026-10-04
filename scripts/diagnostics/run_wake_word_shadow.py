"""Run a no-audio-retention false-trigger evaluation on the live microphone."""

from __future__ import annotations

import argparse
import json
import os
import threading
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=float, default=8.0)
    parser.add_argument("--profile", default=".local/wake-word/profile.json")
    parser.add_argument("--output", default=".local/wake-word/shadow-report.json")
    args = parser.parse_args()

    profile = Path(args.profile).resolve()
    if not profile.exists():
        raise SystemExit(f"Calibration profile is missing: {profile}")
    if args.hours <= 0:
        raise SystemExit("--hours must be positive")

    # Configure before Settings is first constructed. This script deliberately
    # receives callbacks so it can count candidates, but never launches Aiden.
    os.environ["SPEECH_OWW_PROFILE_PATH"] = str(profile)
    os.environ["SPEECH_OWW_SHADOW_MODE"] = "false"
    os.environ["SPEECH_OWW_CAPTURE_DIAGNOSTICS"] = "false"

    from src.speech.openwakeword_wake import OpenWakeWordDetector
    from src.speech.wake_detection import WakeDetection

    detections: list[dict] = []
    lock = threading.Lock()

    def on_detection(detection: WakeDetection) -> None:
        with lock:
            detections.append(
                {
                    "timestamp": detection.timestamp,
                    "model": detection.model_name,
                    "confidence": round(detection.confidence, 4),
                    "metadata": detection.metadata,
                }
            )
        print(
            f"Candidate #{len(detections)}: {detection.model_name} "
            f"score={detection.confidence:.3f}",
            flush=True,
        )

    detector = OpenWakeWordDetector(callback=on_detection)
    detector.capture_diagnostics = False
    detector.shadow_mode = False
    started = time.monotonic()
    detector.start()
    try:
        if not detector.wait_until_ready(timeout=20.0):
            raise SystemExit("Wake model or selected microphone did not become ready")
        deadline = started + (args.hours * 3_600)
        print(
            "Shadow evaluation running. Do not intentionally say either wake phrase. "
            "Press Ctrl+C to stop early.",
            flush=True,
        )
        while time.monotonic() < deadline:
            time.sleep(min(30.0, deadline - time.monotonic()))
    except KeyboardInterrupt:
        print("Stopping early; report will be marked incomplete.", flush=True)
    finally:
        detector.stop()

    elapsed_hours = (time.monotonic() - started) / 3_600
    false_positives_per_hour = len(detections) / elapsed_hours if elapsed_hours else 0.0
    completed = elapsed_hours >= args.hours * 0.99
    report = {
        "version": 1,
        "requested_hours": args.hours,
        "elapsed_hours": round(elapsed_hours, 4),
        "completed": completed,
        "false_activations": len(detections),
        "false_positives_per_hour": round(false_positives_per_hour, 4),
        "target_false_positives_per_hour": 0.125,
        "passed": completed and false_positives_per_hour <= 0.125,
        "detections": detections,
        "raw_audio_saved": False,
    }
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
