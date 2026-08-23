"""Download and normalize public audio assets used by openWakeWord training.

Run this inside the Linux/WSL training environment, not Aiden's app runtime.
"""

from __future__ import annotations

import argparse
import itertools
import tarfile
from pathlib import Path


def write_streaming_audio(dataset, output: Path, limit: int | None = None) -> None:
    import numpy as np
    import scipy.io.wavfile
    from tqdm import tqdm

    output.mkdir(parents=True, exist_ok=True)
    rows = dataset if limit is None else itertools.islice(dataset, limit)
    for index, row in enumerate(tqdm(rows)):
        audio = row["audio"]
        source_name = Path(audio.get("path") or f"clip-{index}.wav").stem
        samples = np.asarray(audio["array"], dtype=np.float32)
        samples = np.clip(samples, -1.0, 1.0)
        scipy.io.wavfile.write(
            output / f"{index:05d}-{source_name}.wav",
            16_000,
            (samples * 32_767).astype(np.int16),
        )


def prepare_rirs(root: Path) -> None:
    import datasets

    output = root / "mit_rirs"
    if any(output.glob("*.wav")):
        return
    dataset = datasets.load_dataset(
        "davidscripka/MIT_environmental_impulse_responses",
        split="train",
        streaming=True,
    ).cast_column("audio", datasets.Audio(sampling_rate=16_000))
    write_streaming_audio(dataset, output)


def prepare_audioset(root: Path) -> None:
    import datasets
    import requests

    output = root / "audioset_16k"
    if any(output.glob("*.wav")):
        return
    archive = root / "bal_train09.tar"
    if not archive.exists():
        url = "https://huggingface.co/datasets/agkphysics/AudioSet/resolve/main/data/bal_train09.tar"
        with requests.get(url, stream=True, timeout=60) as response:
            response.raise_for_status()
            with archive.open("wb") as destination:
                for chunk in response.iter_content(1024 * 1024):
                    destination.write(chunk)
    extracted = root / "audioset"
    if not extracted.exists():
        with tarfile.open(archive) as source:
            # Python 3.10 does not support tarfile's ``filter=`` argument.
            # Validate every member explicitly before extraction so the
            # isolated CUDA environment can remain on the planned version.
            extraction_root = extracted.resolve()
            for member in source.getmembers():
                if member.issym() or member.islnk():
                    raise ValueError(f"Links are not allowed in AudioSet archive: {member.name}")
                target = (extracted / member.name).resolve()
                if target != extraction_root and extraction_root not in target.parents:
                    raise ValueError(f"Unsafe path in AudioSet archive: {member.name}")
            source.extractall(extracted)
    clips = list(extracted.rglob("*.flac"))
    dataset = datasets.Dataset.from_dict({"audio": [str(path) for path in clips]})
    dataset = dataset.cast_column("audio", datasets.Audio(sampling_rate=16_000))
    write_streaming_audio(dataset, output)


def prepare_music(root: Path) -> None:
    import datasets

    output = root / "fma"
    if any(output.glob("*.wav")):
        return
    dataset = datasets.load_dataset(
        "rudraml/fma",
        name="small",
        split="train",
        streaming=True,
    ).cast_column("audio", datasets.Audio(sampling_rate=16_000))
    # 120 x 30-second clips = one hour of varied music.
    write_streaming_audio(dataset, output, limit=120)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".local/wake-training")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    prepare_rirs(root)
    prepare_audioset(root)
    prepare_music(root)
    print(f"Training audio assets ready under {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
