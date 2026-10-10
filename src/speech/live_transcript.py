"""Display-only Vosk previews; Whisper remains the command recognizer."""
import json
import queue
import threading
import time
from pathlib import Path
from typing import Callable

from src.utils.logger import get_logger
from src.utils.paths import resource_path

logger = get_logger(__name__)
_models = {}
_model_lock = threading.Lock()


def load_model(path: str):
    import vosk
    configured = Path(path or "vosk_models/vosk-model-small-en-us-0.15")
    resolved = str(configured if configured.is_absolute() else resource_path(*configured.parts))
    with _model_lock:
        if resolved not in _models:
            _models[resolved] = vosk.Model(resolved)
        return _models[resolved]


class LiveTranscript:
    """Consume the capture stream off-thread without blocking microphone reads."""
    def __init__(self, model_path: str, sample_rate: int, publish: Callable[[str], None]):
        self.frames = queue.Queue(maxsize=512)
        self.closed = threading.Event()
        self.publish = publish
        self.model_path = model_path
        self.sample_rate = sample_rate
        threading.Thread(target=self._run, daemon=True, name="speech-preview").start()

    def feed(self, frame: bytes):
        if not self.closed.is_set():
            try:
                self.frames.put_nowait(frame)
            except queue.Full:
                # Display is expendable; never delay authoritative capture.
                self.close()

    def reset(self):
        try:
            self.frames.put_nowait(None)
        except queue.Full:
            self.close()

    def close(self):
        self.closed.set()

    def _run(self):
        try:
            import vosk
            model = load_model(self.model_path)
            recognizer = vosk.KaldiRecognizer(model, self.sample_rate)
            committed = ""
            previous = ""
            updated = 0.0
            while not self.closed.is_set():
                try:
                    frame = self.frames.get(timeout=.1)
                except queue.Empty:
                    continue
                if frame is None:
                    recognizer = vosk.KaldiRecognizer(model, self.sample_rate)
                    committed = previous = ""
                    self.publish("")
                    continue
                if recognizer.AcceptWaveform(frame):
                    committed = " ".join(filter(None, [committed, json.loads(recognizer.Result()).get("text", "")]))
                    text = committed
                else:
                    text = " ".join(filter(None, [committed, json.loads(recognizer.PartialResult()).get("partial", "")]))
                now = time.monotonic()
                if text != previous and now - updated >= .1 and not self.closed.is_set():
                    self.publish(text)
                    previous, updated = text, now
        except Exception as exc:
            logger.debug("Live preview unavailable; final Whisper recognition is unaffected: %s", exc)
