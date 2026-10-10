"""Compare hosted Kitten speech with Edge/Groq without executing commands.

Run from the repository: .venv/Scripts/python.exe tools/benchmark_kitten_speech.py
Use --audio command.wav --expected "Open Chrome" for a real recording.
Artifacts contain audio/transcripts and stay in ignored .local/kitten-speech.
"""
from __future__ import annotations

import argparse
import asyncio
import io
import json
import re
import sys
import time
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import edge_tts
import httpx
import numpy as np

from src.speech.kitten_client import KittenClient, KittenRealtime, pcm_wav
from src.utils.config import get_settings


def word_error_rate(expected: str, actual: str) -> float:
    reference = re.findall(r"\w+", expected.lower())
    hypothesis = re.findall(r"\w+", actual.lower())
    previous = list(range(len(hypothesis) + 1))
    for i, word in enumerate(reference, 1):
        current = [i]
        for j, other in enumerate(hypothesis, 1):
            current.append(min(current[-1] + 1, previous[j] + 1,
                               previous[j - 1] + (word != other)))
        previous = current
    return previous[-1] / max(1, len(reference))


def read_pcm(path: Path) -> tuple[bytes, int]:
    with wave.open(str(path), "rb") as audio:
        if audio.getsampwidth() != 2:
            raise ValueError("Benchmark audio must be PCM16 WAV")
        rate = audio.getframerate()
        data = np.frombuffer(audio.readframes(audio.getnframes()), dtype="<i2")
        if audio.getnchannels() > 1:
            data = data.reshape(-1, audio.getnchannels()).mean(axis=1)
    # Use exactly the same 16kHz input for both recognizers.
    if rate != 16000:
        count = round(len(data) * 16000 / rate)
        data = np.interp(np.arange(count) * rate / 16000, np.arange(len(data)), data)
    return data.astype("<i2").tobytes(), 16000


async def benchmark(args) -> None:
    settings = get_settings()
    client = KittenClient(settings.speech)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    results = {"scope": "Network/inference measurements, no cache, no command execution",
               "tts": [], "stt": [], "audio_source": "recorded" if args.audio else "synthetic Eleanor"}
    texts = ["Opening Chrome.", "Play something on Spotify and turn off the fan.",
             "Hello, I am Aiden. I can help you open applications, control your music, and manage your smart home. "
             "Tell me what you would like to do next, and I will get started."]
    for trial in range(args.repeats):
        for index, text in enumerate(texts):
            # Alternate order to reduce a systematic warmup/order bias.
            providers = ["kitten", "edge"] if trial % 2 == 0 else ["edge", "kitten"]
            for provider in providers:
                start = time.perf_counter()
                first = buffered = None
                audio = bytearray()
                try:
                    if provider == "kitten":
                        async for chunk in client.speech_pcm(text):
                            if first is None:
                                first = time.perf_counter() - start
                            audio.extend(chunk)
                            if buffered is None and len(audio) >= 16800:
                                buffered = time.perf_counter() - start
                        data = pcm_wav(bytes(audio))
                        extension = "wav"
                    else:
                        rate = "+25%" if settings.speech.tts_rate > 1.2 else "+5%" if settings.speech.tts_rate < .8 else "+15%"
                        async for event in edge_tts.Communicate(text, settings.speech.tts_voice,
                                                               rate=rate, boundary="WordBoundary").stream():
                            if event["type"] == "audio":
                                if first is None:
                                    first = time.perf_counter() - start
                                audio.extend(event["data"])
                        data, extension = bytes(audio), "mp3"
                    total = time.perf_counter() - start
                    (output / f"{provider}-{trial}-{index}.{extension}").write_bytes(data)
                    row = {"provider": provider, "trial": trial, "text": text,
                           "first_audio_s": first, "total_s": total,
                           "playable_ready_s": buffered if provider == "kitten" else total,
                           "audio_bytes": len(audio)}
                except Exception as exc:
                    row = {"provider": provider, "trial": trial, "text": text,
                           "error": type(exc).__name__}
                results["tts"].append(row)
                print(json.dumps(row), flush=True)
    audio_path = Path(args.audio) if args.audio else output / "kitten-0-1.wav"
    if audio_path.exists():
        pcm, rate = read_pcm(audio_path)
        wav = pcm_wav(pcm, rate)
        duration = len(pcm) / (rate * 2)
        expected = args.expected or (texts[1] if not args.audio else "")
        for trial in range(args.repeats):
            for provider in ("kitten_upload", "groq", "kitten_realtime"):
                start = time.perf_counter()
                first_partial = None
                session = None
                try:
                    if provider == "kitten_upload":
                        transcript = await client.transcribe(wav)
                        wait_after_capture = time.perf_counter() - start
                    elif provider == "groq":
                        async with httpx.AsyncClient(timeout=30) as http:
                            response = await http.post("https://api.groq.com/openai/v1/audio/transcriptions",
                                headers={"Authorization": f"Bearer {settings.groq.api_key}"},
                                data={"model": "whisper-large-v3-turbo", "response_format": "json", "language": "en"},
                                files={"file": ("command.wav", wav, "audio/wav")})
                            response.raise_for_status()
                            transcript = response.json().get("text", "")
                        wait_after_capture = time.perf_counter() - start
                    else:
                        def publish(text):
                            nonlocal first_partial
                            if text and first_partial is None:
                                first_partial = time.perf_counter() - start
                        session = KittenRealtime(settings.speech, rate, publish)
                        chunk_bytes = int(rate * 2 * .2)
                        for offset in range(0, len(pcm), chunk_bytes):
                            chunk = pcm[offset:offset + chunk_bytes]
                            session.feed(chunk)
                            await asyncio.sleep(len(chunk) / (rate * 2))
                        committed = time.perf_counter()
                        transcript = await session.finish()
                        wait_after_capture = time.perf_counter() - committed
                    row = {"provider": provider, "trial": trial, "audio_duration_s": duration,
                           "total_s": time.perf_counter() - start, "after_capture_s": wait_after_capture,
                           "first_partial_s": first_partial, "transcript": transcript,
                           "wer": word_error_rate(expected, transcript) if expected else None}
                except Exception as exc:
                    row = {"provider": provider, "trial": trial, "error": type(exc).__name__}
                finally:
                    if session is not None:
                        await session.aclose()
                results["stt"].append(row)
                print(json.dumps(row), flush=True)
    (output / "benchmark.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Results: {(output / 'benchmark.json').resolve()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=3, choices=range(1, 11))
    parser.add_argument("--audio", help="PCM16 WAV recording; sent to KittenML and Groq")
    parser.add_argument("--expected", default="", help="Reference transcript for word error rate")
    parser.add_argument("--output", default=".local/kitten-speech")
    asyncio.run(benchmark(parser.parse_args()))
