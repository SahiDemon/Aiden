"""Download and normalize public audio assets used by openWakeWord training.

Run this inside the Linux/WSL training environment, not Aiden's app runtime.
"""

from __future__ import annotations

import argparse
import itertools
import subprocess
import tarfile
import tempfile
import zipfile
from pathlib import Path


def download_resumable(url: str, destination: Path) -> None:
    import requests
    from tqdm import tqdm

    partial = destination.with_suffix(destination.suffix + ".part")
    downloaded = partial.stat().st_size if partial.exists() else 0
    headers = {"Range": f"bytes={downloaded}-"} if downloaded else {}
    with requests.get(url, headers=headers, stream=True, timeout=60) as response:
        response.raise_for_status()
        resumed = downloaded > 0 and response.status_code == 206
        mode = "ab" if resumed else "wb"
        initial = downloaded if resumed else 0
        remaining = int(response.headers.get("content-length", 0))
        total = initial + remaining if remaining else None
        with partial.open(mode) as output, tqdm(
            total=total,
            initial=initial,
            unit="B",
            unit_scale=True,
            desc=destination.name,
        ) as progress:
            for chunk in response.iter_content(1024 * 1024):
                if chunk:
                    output.write(chunk)
                    progress.update(len(chunk))
    partial.replace(destination)


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

    output = root / "audioset_16k"
    if any(output.glob("*.wav")):
        return
    archive = root / "bal_train09.tar"
    if not archive.exists():
        # The dataset's main branch was converted to Parquet in 2026. Pin the
        # original immutable revision so this training recipe remains stable.
        url = (
            "https://huggingface.co/datasets/agkphysics/AudioSet/resolve/"
            "728fffe80088808b49db5aa700f2e264c035c880/data/bal_train09.tar"
        )
        download_resumable(url, archive)
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
    output = root / "fma"
    if any(output.glob("*.wav")):
        return
    archive = root / "fma_small.zip"
    if not archive.exists():
        download_resumable(
            "https://os.unil.cloud.switch.ch/fma/fma_small.zip",
            archive,
        )

    output.mkdir(parents=True, exist_ok=True)
    # The legacy Hugging Face loader cannot seek its remote ZIP in streaming
    # mode. Read the official archive locally and convert only the clips we
    # need, one at a time, instead of extracting the entire dataset.
    with zipfile.ZipFile(archive) as source:
        members = [
            member
            for member in source.infolist()
            if not member.is_dir() and member.filename.lower().endswith(".mp3")
        ][:120]
        if len(members) < 120:
            raise ValueError(f"FMA archive contains only {len(members)} MP3 clips")
        with tempfile.TemporaryDirectory(dir=root) as temporary:
            temporary_root = Path(temporary)
            for index, member in enumerate(members):
                if member.filename.startswith(("/", "\\")) or ".." in Path(member.filename).parts:
                    raise ValueError(f"Unsafe path in FMA archive: {member.filename}")
                input_path = temporary_root / f"{index:05d}.mp3"
                output_path = output / f"{index:05d}-{Path(member.filename).stem}.wav"
                with source.open(member) as compressed, input_path.open("wb") as extracted:
                    while chunk := compressed.read(1024 * 1024):
                        extracted.write(chunk)
                subprocess.run(
                    [
                        "ffmpeg",
                        "-nostdin",
                        "-loglevel",
                        "error",
                        "-y",
                        "-i",
                        str(input_path),
                        "-ac",
                        "1",
                        "-ar",
                        "16000",
                        str(output_path),
                    ],
                    check=True,
                )
                input_path.unlink()


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
