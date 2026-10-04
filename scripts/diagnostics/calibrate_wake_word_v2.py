"""Choose a wake threshold from held-out personalized recordings."""

from __future__ import annotations

import argparse
import collections
import json
import wave
from pathlib import Path

import numpy as np
from openwakeword.model import Model


FRAME_SAMPLES = 1_280
MAX_FALSE_POSITIVES_PER_HOUR = 1 / 8


def read_pcm(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as source:
        if source.getframerate() != 16_000 or source.getnchannels() != 1 or source.getsampwidth() != 2:
            raise ValueError(f"Expected 16 kHz mono PCM16 WAV: {path}")
        return np.frombuffer(source.readframes(source.getnframes()), dtype=np.int16)


def score_clip(model: Model, path: Path, label: str) -> tuple[list[float], float]:
    model.reset()
    source_pcm = read_pcm(path)
    # Streaming models need warm-up context. Match openWakeWord's predict_clip
    # behavior with one second of silence at each edge.
    pcm = np.concatenate(
        (
            np.zeros(16_000, dtype=np.int16),
            source_pcm,
            np.zeros(16_000, dtype=np.int16),
        )
    )
    scores: list[float] = []
    for start in range(0, max(0, len(pcm) - FRAME_SAMPLES + 1), FRAME_SAMPLES):
        prediction = model.predict(pcm[start : start + FRAME_SAMPLES])
        scores.append(float(prediction.get(label, 0.0)))
    return scores, len(source_pcm) / 16_000


def activates(scores: list[float], threshold: float, strong: float) -> bool:
    history: collections.deque[float] = collections.deque(maxlen=3)
    for score in scores:
        history.append(score)
        if score >= strong or sum(value >= threshold for value in history) >= 2:
            return True
    return False


def recall_for(rows: list[tuple[dict, list[float], float]], threshold: float, strong: float) -> float:
    if not rows:
        return 0.0
    return sum(activates(scores, threshold, strong) for _, scores, _ in rows) / len(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default=".local/wake-word")
    parser.add_argument("--model", default="vosk_models/aiden_v2.onnx")
    parser.add_argument("--verifier", default="vosk_models/aiden_v2_verifier.pkl")
    parser.add_argument("--output", default=".local/wake-word/profile.json")
    parser.add_argument("--input-device-name", default="USB PnP Audio Device")
    parser.add_argument(
        "--verifier-gate",
        type=float,
        default=0.25,
        help="Base-model score at which the personal verifier is evaluated",
    )
    parser.add_argument(
        "--target-phrase",
        default="",
        help="Evaluate only this positive phrase; negatives are always retained",
    )
    args = parser.parse_args()

    if not 0.0 <= args.verifier_gate <= 1.0:
        raise SystemExit("--verifier-gate must be between 0 and 1")

    dataset = Path(args.dataset).resolve()
    model_path = Path(args.model).resolve()
    verifier_path = Path(args.verifier).resolve()
    output_path = Path(args.output).resolve()
    manifest = json.loads((dataset / "manifest.json").read_text(encoding="utf-8"))
    label = model_path.stem

    model = Model(
        wakeword_models=[str(model_path)],
        custom_verifier_models={label: str(verifier_path)},
        custom_verifier_threshold=args.verifier_gate,
        vad_threshold=0.2,
        inference_framework="onnx",
    )

    target_phrase = args.target_phrase.strip().casefold()
    evaluated = []
    for item in manifest["samples"]:
        if item["split"] not in {"holdout", "acceptance"}:
            continue
        if (
            target_phrase
            and item["label"] == "positive"
            and str(item.get("phrase", "")).strip().casefold() != target_phrase
        ):
            continue
        scores, duration = score_clip(model, dataset / item["path"], label)
        evaluated.append((item, scores, duration))

    holdout = [row for row in evaluated if row[0]["split"] == "holdout"]
    if not any(row[0]["label"] == "positive" for row in holdout):
        raise SystemExit("No positive holdout recordings found")
    if not any(row[0]["label"] == "negative" for row in holdout):
        raise SystemExit("No negative holdout recordings found")

    candidates = []
    for threshold in np.arange(0.30, 0.851, 0.025):
        threshold = round(float(threshold), 3)
        strong = min(0.95, round(threshold + 0.20, 3))
        positive = [row for row in holdout if row[0]["label"] == "positive"]
        negative = [row for row in holdout if row[0]["label"] == "negative"]
        true_positives = sum(activates(scores, threshold, strong) for _, scores, _ in positive)
        false_positives = sum(activates(scores, threshold, strong) for _, scores, _ in negative)
        recall = true_positives / len(positive) if positive else 0.0
        negative_hours = sum(duration for _, _, duration in negative) / 3_600
        fp_per_hour = false_positives / negative_hours if negative_hours else float("inf")
        candidates.append((false_positives, -recall, threshold, strong, recall, fp_per_hour))

    valid = [
        candidate
        for candidate in candidates
        if candidate[0] == 0
        and candidate[4] >= 0.85
        and candidate[5] <= MAX_FALSE_POSITIVES_PER_HOUR
    ]
    if not valid:
        raise SystemExit("No threshold met recall and zero-false-positive requirements; keep hey_aiden.onnx")

    selected = min(valid, key=lambda item: (item[1], item[2]))
    _, _, threshold, strong, recall, fp_per_hour = selected
    acceptance = [row for row in evaluated if row[0]["split"] == "acceptance"]
    acceptance_metrics = {}
    deployment_ready = False
    if acceptance:
        groups = {
            "normal_within_1_5m": [
                row
                for row in acceptance
                if row[0].get("volume") == "normal"
                and row[0].get("distance") in {"0.5m", "1.5m"}
            ],
            "normal_at_3m": [
                row
                for row in acceptance
                if row[0].get("volume") == "normal" and row[0].get("distance") == "3m"
            ],
            "quiet_at_1_5m": [
                row
                for row in acceptance
                if row[0].get("volume") == "quiet" and row[0].get("distance") == "1.5m"
            ],
        }
        acceptance_metrics = {
            name: round(recall_for(rows, threshold, strong), 4)
            for name, rows in groups.items()
        }
        deployment_ready = (
            acceptance_metrics["normal_within_1_5m"] >= 0.95
            and acceptance_metrics["normal_at_3m"] >= 0.90
            and acceptance_metrics["quiet_at_1_5m"] >= 0.85
        )
    profile = {
        "version": 1,
        "model_path": str(Path(args.model).as_posix()),
        "verifier_path": str(Path(args.verifier).as_posix()),
        "verifier_gate": args.verifier_gate,
        "threshold": threshold,
        "strong_threshold": strong,
        "vad_threshold": 0.2,
        "smoothing_window": 3,
        "smoothing_hits": 2,
        "input_device_name": args.input_device_name,
        "validation": {
            "positive_recall": round(recall, 4),
            "false_positives": 0,
            "estimated_false_positives_per_hour": round(fp_per_hour, 4),
            "maximum_false_positives_per_hour": MAX_FALSE_POSITIVES_PER_HOUR,
            "holdout_clips": len(holdout),
            "target_phrase": args.target_phrase or None,
            "acceptance": acceptance_metrics,
            "deployment_ready": deployment_ready,
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    print(json.dumps(profile, indent=2))
    print(f"Calibration profile created: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
