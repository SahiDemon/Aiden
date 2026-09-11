"""Guided local recorder for Aiden wake-word personalization.

Audio is written only beneath .local/wake-word, which is ignored by Git.
"""

from __future__ import annotations

import argparse
import json
import time
import wave
from pathlib import Path

import pyaudio


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_RATE = 16_000
SAMPLE_WIDTH = 2
CHANNELS = 1
CHUNK = 1_280


def _name_matches(preferred_name: str, candidate_name: str) -> bool:
    needle = preferred_name.casefold().strip()
    folded = candidate_name.casefold()
    if not needle:
        return True
    if needle in folded:
        return True
    tokens = [token for token in needle.replace("-", " ").split() if len(token) >= 3]
    matching_tokens = sum(token in folded for token in tokens)
    return bool(tokens and matching_tokens >= max(1, len(tokens) - 1))


def _can_open_device(audio: pyaudio.PyAudio, device_index: int) -> bool:
    """Probe the exact PCM stream used for recording before prompting."""
    stream = None
    try:
        stream = audio.open(
            format=pyaudio.paInt16,
            channels=CHANNELS,
            rate=SAMPLE_RATE,
            input=True,
            input_device_index=device_index,
            frames_per_buffer=CHUNK,
            start=False,
        )
        return True
    except OSError:
        return False
    finally:
        if stream is not None:
            stream.close()


def find_device(audio: pyaudio.PyAudio, preferred_name: str) -> tuple[int | None, str]:
    candidates: list[tuple[int, str]] = []
    try:
        default = audio.get_default_input_device_info()
        default_index = int(default["index"])
        default_name = str(default["name"])
        if _name_matches(preferred_name, default_name):
            candidates.append((default_index, default_name))
    except Exception:
        pass

    for index in range(audio.get_device_count()):
        info = audio.get_device_info_by_index(index)
        if int(info.get("maxInputChannels", 0)) <= 0:
            continue
        name = str(info.get("name", ""))
        candidate = (index, name)
        if _name_matches(preferred_name, name) and candidate not in candidates:
            candidates.append(candidate)

    for index, name in candidates:
        if _can_open_device(audio, index):
            return index, name
    raise RuntimeError(
        f"No 16 kHz mono input endpoint could be opened for '{preferred_name}'. "
        "Close Aiden and other microphone applications, then retry."
    )


def record_clip(
    audio: pyaudio.PyAudio,
    device_index: int | None,
    duration: float,
) -> bytes:
    stream = audio.open(
        format=pyaudio.paInt16,
        channels=CHANNELS,
        rate=SAMPLE_RATE,
        input=True,
        input_device_index=device_index,
        frames_per_buffer=CHUNK,
    )
    try:
        print("RECORDING", flush=True)
        frames = []
        for _ in range(int(SAMPLE_RATE / CHUNK * duration)):
            frames.append(stream.read(CHUNK, exception_on_overflow=False))
        return b"".join(frames)
    finally:
        stream.stop_stream()
        stream.close()


def save_wav(path: Path, pcm: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(CHANNELS)
        output.setsampwidth(SAMPLE_WIDTH)
        output.setframerate(SAMPLE_RATE)
        output.writeframes(pcm)


def countdown(label: str) -> None:
    input(f"\n{label}\nPress Enter when positioned and ready...")
    for value in (3, 2, 1):
        print(value, flush=True)
        time.sleep(0.6)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default=str(PROJECT_ROOT / ".local" / "wake-word"),
        help="Local dataset directory (defaults to this repository's .local/wake-word)",
    )
    parser.add_argument("--device-name", default="USB PnP Audio Device")
    parser.add_argument("--skip-long-negatives", action="store_true")
    parser.add_argument(
        "--acceptance-only",
        action="store_true",
        help="Record the separate 48-activation acceptance matrix",
    )
    parser.add_argument(
        "--refine-personalization",
        action="store_true",
        help=(
            "Append a targeted live-microphone refinement set without replacing "
            "the existing dataset"
        ),
    )
    parser.add_argument("--list-devices", action="store_true")
    args = parser.parse_args()

    root = Path(args.output).resolve()
    audio = pyaudio.PyAudio()
    try:
        if args.list_devices:
            for index in range(audio.get_device_count()):
                info = audio.get_device_info_by_index(index)
                if int(info.get("maxInputChannels", 0)) > 0:
                    print(f"{index}: {info.get('name')}")
            return 0

        device_index, device_name = find_device(audio, args.device_name)
        print(f"Using input {device_index}: {device_name}")
        print(f"All recordings stay local in {root}")

        manifest_path = root / "manifest.json"
        if args.acceptance_only and args.refine_personalization:
            raise SystemExit("Choose either --acceptance-only or --refine-personalization")

        if args.acceptance_only:
            if not manifest_path.exists():
                raise SystemExit("Record the training dataset before acceptance samples")
            manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest = [
                item
                for item in manifest_data.get("samples", [])
                if item.get("split") != "acceptance"
            ]
            for phrase_slug, phrase in (("aiden", "Aiden"), ("hey_aiden", "Hey Aiden")):
                for distance in ("0.5m", "1.5m", "3m"):
                    for volume in ("normal", "quiet"):
                        for repetition in range(1, 5):
                            relative = Path("positive") / "acceptance" / phrase_slug / (
                                f"{distance}-{volume}-{repetition}.wav"
                            )
                            countdown(
                                f'Say "{phrase}" once — {volume} voice at {distance} '
                                f"({repetition}/4)"
                            )
                            save_wav(root / relative, record_clip(audio, device_index, 2.5))
                            manifest.append(
                                {
                                    "path": relative.as_posix(),
                                    "label": "positive",
                                    "phrase": phrase,
                                    "distance": distance,
                                    "volume": volume,
                                    "split": "acceptance",
                                }
                            )
        elif args.refine_personalization:
            if not manifest_path.exists():
                raise SystemExit("Record the base training dataset before refining it")

            manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest = list(manifest_data.get("samples", []))
            print(
                "This adds 44 short, labelled clips to the existing dataset. "
                "Use your normal wake-word voice; the files remain local."
            )

            # A verifier learns the user's voice, not just the phrase. The
            # base dataset deliberately has broad coverage but only eight
            # training clips per phrase. Add enough natural USB-microphone
            # examples and confusable words to make the verifier discriminative
            # without discarding the original holdout material.
            for phrase_slug, phrase in (("aiden", "Aiden"), ("hey_aiden", "Hey Aiden")):
                for repetition in range(1, 13):
                    split = "holdout" if repetition in {4, 8, 12} else "train"
                    distance = ("0.5m", "1.5m", "3m")[(repetition - 1) % 3]
                    volume = "quiet" if repetition % 4 == 0 else "normal"
                    relative = (
                        Path("positive")
                        / split
                        / "refinement"
                        / phrase_slug
                        / f"{repetition:02d}.wav"
                    )
                    countdown(
                        f'Say "{phrase}" once — {volume} voice at {distance} '
                        f"(refinement {repetition}/12)"
                    )
                    save_wav(root / relative, record_clip(audio, device_index, 2.5))
                    manifest.append(
                        {
                            "path": relative.as_posix(),
                            "label": "positive",
                            "phrase": phrase,
                            "distance": distance,
                            "volume": volume,
                            "split": split,
                            "source": "personalization_refinement",
                        }
                    )

            for phrase in ("Hayden", "maiden", "aid in", "aiding", "eight"):
                slug = phrase.replace(" ", "_")
                for repetition in range(1, 5):
                    split = "holdout" if repetition == 4 else "train"
                    relative = (
                        Path("negative")
                        / split
                        / "hard"
                        / "refinement"
                        / f"{slug}-{repetition}.wav"
                    )
                    countdown(
                        f'Say the non-wake phrase "{phrase}" once '
                        f"(refinement {repetition}/4)"
                    )
                    save_wav(root / relative, record_clip(audio, device_index, 2.5))
                    manifest.append(
                        {
                            "path": relative.as_posix(),
                            "label": "negative",
                            "category": "hard",
                            "phrase": phrase,
                            "split": split,
                            "source": "personalization_refinement",
                        }
                    )
        else:
            manifest = []
            for phrase_slug, phrase in (("aiden", "Aiden"), ("hey_aiden", "Hey Aiden")):
                sample_number = 0
                for distance in ("0.5m", "1.5m", "3m"):
                    for volume in ("normal", "quiet"):
                        for repetition in range(1, 3):
                            sample_number += 1
                            split = "holdout" if sample_number % 3 == 0 else "train"
                            relative = Path("positive") / split / phrase_slug / (
                                f"{distance}-{volume}-{repetition}.wav"
                            )
                            countdown(
                                f'Say "{phrase}" once — {volume} voice at {distance} '
                                f"({repetition}/2)"
                            )
                            save_wav(root / relative, record_clip(audio, device_index, 2.5))
                            manifest.append(
                                {
                                    "path": relative.as_posix(),
                                    "label": "positive",
                                    "phrase": phrase,
                                    "distance": distance,
                                    "volume": volume,
                                    "split": split,
                                }
                            )

            hard_negatives = ("Hayden", "maiden", "aid in", "aiding", "eight")
            for phrase in hard_negatives:
                for repetition in range(1, 3):
                    split = "holdout" if repetition == 2 else "train"
                    slug = phrase.replace(" ", "_")
                    relative = Path("negative") / split / "hard" / f"{slug}-{repetition}.wav"
                    countdown(f'Say the non-wake phrase "{phrase}" ({repetition}/2)')
                    save_wav(root / relative, record_clip(audio, device_index, 2.5))
                    manifest.append(
                        {
                            "path": relative.as_posix(),
                            "label": "negative",
                            "category": "hard",
                            "phrase": phrase,
                            "split": split,
                        }
                    )

            if not args.skip_long_negatives:
                for category, count, duration, prompt in (
                    ("speech", 6, 10.0, "Speak normally without saying Aiden"),
                    ("background", 3, 10.0, "Capture normal room, TV, or music sound"),
                ):
                    for index in range(1, count + 1):
                        split = "holdout" if index % 3 == 0 else "train"
                        relative = Path("negative") / split / category / f"{index:02d}.wav"
                        countdown(f"{prompt} — clip {index}/{count}")
                        save_wav(root / relative, record_clip(audio, device_index, duration))
                        manifest.append(
                            {
                                "path": relative.as_posix(),
                                "label": "negative",
                                "category": category,
                                "split": split,
                            }
                        )

        manifest_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "sample_rate": SAMPLE_RATE,
                    "device_name": device_name,
                    "samples": manifest,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\nDataset complete: {manifest_path}")
        return 0
    finally:
        audio.terminate()


if __name__ == "__main__":
    raise SystemExit(main())
