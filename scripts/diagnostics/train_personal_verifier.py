"""Train an openWakeWord personal verifier from the guided dataset."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import openwakeword


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default=".local/wake-word")
    parser.add_argument("--model", default="vosk_models/aiden_v2.onnx")
    parser.add_argument("--output", default="vosk_models/aiden_v2_verifier.pkl")
    args = parser.parse_args()

    dataset = Path(args.dataset).resolve()
    model = Path(args.model).resolve()
    output = Path(args.output).resolve()
    manifest = json.loads((dataset / "manifest.json").read_text(encoding="utf-8"))

    positives = [
        str(dataset / item["path"])
        for item in manifest["samples"]
        if item["label"] == "positive" and item["split"] == "train"
    ]
    negatives = [
        str(dataset / item["path"])
        for item in manifest["samples"]
        if item["label"] == "negative" and item["split"] == "train"
    ]
    if not model.exists():
        raise SystemExit(f"Base model is missing: {model}")
    if len(positives) < 6 or len(negatives) < 2:
        raise SystemExit("Dataset is incomplete; run record_wake_word_dataset.py first")

    output.parent.mkdir(parents=True, exist_ok=True)
    openwakeword.train_custom_verifier(
        positive_reference_clips=positives,
        negative_reference_clips=negatives,
        output_path=str(output),
        model_name=str(model),
        vad_threshold=0.2,
        inference_framework="onnx",
    )
    print(f"Personal verifier created: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
