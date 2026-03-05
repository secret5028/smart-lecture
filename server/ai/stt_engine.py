from __future__ import annotations

import tempfile
from pathlib import Path

try:
    from faster_whisper import WhisperModel  # type: ignore
except Exception:  # pragma: no cover
    WhisperModel = None


class STTEngine:
    def __init__(self, model_name: str = "small") -> None:
        self.model_name = model_name
        self.model = None
        if WhisperModel is not None:
            self.model = WhisperModel(model_name, device="cpu", compute_type="int8")

    def transcribe_chunk(self, audio_bytes: bytes) -> str:
        if self.model is None or not audio_bytes:
            return ""

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as fp:
            fp.write(audio_bytes)
            wav_path = Path(fp.name)

        try:
            segments, _ = self.model.transcribe(str(wav_path), language="ko")
            return " ".join(segment.text.strip() for segment in segments).strip()
        finally:
            wav_path.unlink(missing_ok=True)


_stt_engine: STTEngine | None = None


def load_stt_engine(model_name: str = "small") -> STTEngine:
    global _stt_engine
    if _stt_engine is None:
        _stt_engine = STTEngine(model_name)
    return _stt_engine


def get_stt_engine() -> STTEngine:
    if _stt_engine is None:
        return load_stt_engine()
    return _stt_engine
