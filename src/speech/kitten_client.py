"""Server-side KittenML cloud speech adapters; no model download is required.

Protocols: https://docs.kittenml.com/tts/stream-output and /stt/realtime.
Provisional ASR events are snapshots and must never execute commands.
"""
from __future__ import annotations

import asyncio
import base64
import contextlib
import io
import json
import threading
import wave
from collections.abc import AsyncIterator, Callable
from urllib.parse import urlencode

import httpx
from websockets.asyncio.client import connect

from src.utils.config import SpeechConfig

API_URL = "https://api.kittenml.com/v1"
PCM_RATE = 24000


class KittenError(RuntimeError):
    """An error safe to log: never includes request headers or provider text."""


def pcm_wav(pcm: bytes, sample_rate: int = PCM_RATE) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(pcm)
    return output.getvalue()


class KittenClient:
    def __init__(self, settings: SpeechConfig):
        self.settings = settings
        if not settings.kitten_api_key:
            raise KittenError("SPEECH_KITTEN_API_KEY is missing")

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.settings.kitten_api_key}"}

    async def speech_pcm(self, text: str) -> AsyncIterator[bytes]:
        if not text or len(text) > 40000:
            raise KittenError("Kitten speech requires 1–40000 characters")
        payload = {
            "model": self.settings.kitten_tts_model,
            "input": text,
            "voice": self.settings.kitten_tts_voice,
            "speed": self.settings.kitten_tts_speed,
            "response_format": "pcm",
            "stream_format": "sse",
        }
        try:
            async with httpx.AsyncClient(timeout=self.settings.kitten_timeout) as client:
                async with client.stream("POST", f"{API_URL}/audio/speech", headers=self.headers,
                                         json=payload) as response:
                    if response.status_code != 200:
                        raise KittenError(f"Kitten TTS HTTP {response.status_code}")
                    complete = False
                    received = 0
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        event = json.loads(data)
                        if event.get("type") == "speech.audio.delta":
                            pcm = base64.b64decode(event["audio"], validate=True)
                            if len(pcm) % 2:
                                raise KittenError("Kitten returned unaligned PCM")
                            received += len(pcm)
                            if received > PCM_RATE * 2 * 1800:
                                raise KittenError("Kitten audio exceeded 30 minutes")
                            if pcm:
                                yield pcm
                        elif event.get("type") == "speech.audio.done":
                            complete = True
                            break
                        elif event.get("type") == "error":
                            raise KittenError("Kitten TTS stream reported an error")
                    if not complete or not received:
                        raise KittenError("Kitten TTS stream ended without complete audio")
        except KittenError:
            raise
        except Exception as exc:
            raise KittenError(f"Kitten TTS transport failed ({type(exc).__name__})") from None

    async def speech(self, text: str) -> bytes:
        pcm = bytearray()
        async for chunk in self.speech_pcm(text):
            pcm.extend(chunk)
        return pcm_wav(bytes(pcm))

    async def transcribe(self, wav_bytes: bytes) -> str:
        if not wav_bytes or len(wav_bytes) > 25 * 1024 * 1024:
            raise KittenError("Kitten ASR requires a recording under 25 MiB")
        try:
            async with httpx.AsyncClient(timeout=self.settings.kitten_timeout) as client:
                response = await client.post(
                    f"{API_URL}/audio/transcriptions", headers=self.headers,
                    data={"model": self.settings.kitten_stt_model, "response_format": "json",
                          "language": self.settings.stt_language.split("-")[0]},
                    files={"file": ("command.wav", wav_bytes, "audio/wav")},
                )
                if response.status_code != 200:
                    raise KittenError(f"Kitten ASR HTTP {response.status_code}")
                return response.json().get("text", "").strip()
        except KittenError:
            raise
        except Exception as exc:
            raise KittenError(f"Kitten ASR transport failed ({type(exc).__name__})") from None


class KittenRealtime:
    """Bridge capture-thread PCM into one bounded, manually committed ASR turn."""
    def __init__(self, settings: SpeechConfig, sample_rate: int, publish: Callable[[str], None]):
        self.client = KittenClient(settings)
        if sample_rate not in (16000, 24000):
            raise KittenError("Kitten realtime requires 16 or 24 kHz mono PCM16")
        self.sample_rate = sample_rate
        self.publish = publish
        self.closed = threading.Event()
        self.loop = asyncio.get_running_loop()
        self.frames = asyncio.Queue(maxsize=512)
        self.final = self.loop.create_future()
        self.error: Exception | None = None
        self.task = asyncio.create_task(self._run())

    def feed(self, frame: bytes) -> None:
        self.loop.call_soon_threadsafe(self._put, frame)

    def reset(self) -> None:
        self.loop.call_soon_threadsafe(self._put, "reset")

    def _put(self, value) -> None:
        if self.closed.is_set() or self.error:
            return
        try:
            self.frames.put_nowait(value)
        except asyncio.QueueFull:
            self.error = KittenError("Kitten realtime capture queue overflowed")
            self.task.cancel()

    def close(self) -> None:
        self.closed.set()
        self.task.cancel()

    async def aclose(self) -> None:
        self.close()
        with contextlib.suppress(asyncio.CancelledError):
            await self.task

    async def finish(self) -> str:
        # The capture thread has finished before this call; FIFO retains all frames.
        try:
            if self.error:
                raise self.error
            self._put(None)
            return await asyncio.wait_for(asyncio.shield(self.final), self.client.settings.kitten_timeout)
        finally:
            await self.aclose()

    async def _event(self, socket, expected: str) -> dict:
        async def receive():
            while True:
                event = json.loads(await socket.recv())
                if event.get("type") == "error":
                    raise KittenError("Kitten realtime reported a server error")
                if event.get("type") == expected:
                    return event
        return await asyncio.wait_for(receive(), self.client.settings.kitten_timeout)

    async def _receive(self, socket) -> None:
        while True:
            event = json.loads(await socket.recv())
            kind = event.get("type")
            if kind == "error":
                raise KittenError("Kitten realtime transcription failed")
            if kind == "conversation.item.input_audio_transcription.delta":
                # These are replacement snapshots, not append-only token deltas.
                self.publish(event.get("clean_text", event.get("delta", "")))
            elif kind == "conversation.item.input_audio_transcription.completed":
                if not self.final.done():
                    self.final.set_result(event.get("transcript", event.get("clean_text", "")).strip())
                return
            elif kind == "session.closed":
                raise KittenError("Kitten realtime closed before the final transcript")

    async def _send(self, socket) -> None:
        pending = bytearray()
        append_bytes = int(self.sample_rate * 2 * .2)
        while True:
            frame = await self.frames.get()
            if frame == "reset":
                pending.clear()
                await socket.send(json.dumps({"type": "input_audio_buffer.clear"}))
                continue
            if frame is None:
                if pending:
                    await socket.send(json.dumps({"type": "input_audio_buffer.append",
                                                  "audio": base64.b64encode(pending).decode()}))
                await socket.send(json.dumps({"type": "input_audio_buffer.commit"}))
                return
            pending.extend(frame)
            while len(pending) >= append_bytes:
                chunk = pending[:append_bytes]
                del pending[:append_bytes]
                await socket.send(json.dumps({"type": "input_audio_buffer.append",
                                              "audio": base64.b64encode(chunk).decode()}))

    async def _run(self) -> None:
        settings = self.client.settings
        query = urlencode({"model": settings.kitten_stt_model})
        try:
            async with connect(f"wss://api.kittenml.com/v1/realtime?{query}",
                               additional_headers=self.client.headers,
                               open_timeout=settings.kitten_timeout, max_size=1024 * 1024) as socket:
                await self._event(socket, "session.created")
                await socket.send(json.dumps({"type": "session.update", "session": {
                    "type": "transcription", "audio": {"input": {
                        "format": {"type": "audio/pcm", "rate": self.sample_rate},
                        "transcription": {"model": settings.kitten_stt_model,
                                          "delay": settings.kitten_stt_delay,
                                          "language": settings.stt_language.split("-")[0]},
                        "turn_detection": None,
                    }},
                }}))
                await self._event(socket, "session.updated")
                tasks = [asyncio.create_task(self._send(socket)), asyncio.create_task(self._receive(socket))]
                try:
                    await asyncio.gather(*tasks)
                finally:
                    for task in tasks:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
                await socket.send(json.dumps({"type": "session.close"}))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.error = KittenError(f"Kitten realtime transport failed ({type(exc).__name__})")
            if not self.final.done():
                self.final.set_exception(self.error)
                # Retrieve it even when capture is aborted; finish still raises it.
                self.final.exception()
