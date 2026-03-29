import logging
import os
import tempfile
import time
from dataclasses import dataclass

import requests

logger = logging.getLogger("uvicorn.error")

_LOCAL_WHISPER_MODEL = None
_LOCAL_WHISPER_MODEL_NAME = None


@dataclass
class TranscriptionResult:
    text: str
    backend: str
    duration_ms: int


class SttAdapter:
    backend_name = "unknown"

    def transcribe(self, audio_bytes: bytes, filename: str, content_type: str) -> str | None:
        raise NotImplementedError


class NvidiaSttAdapter(SttAdapter):
    backend_name = "nvidia"

    def transcribe(self, audio_bytes: bytes, filename: str, content_type: str) -> str | None:
        api_key = os.getenv("STT_API_KEY", "").strip()
        if not api_key:
            return None

        base_url = os.getenv("STT_BASE_URL", "https://integrate.api.nvidia.com/v1").rstrip("/")
        model_alias = os.getenv("STT_MODEL", "")
        timeout_raw = os.getenv("STT_TIMEOUT_SECONDS", "25")
        try:
            timeout_seconds = float(timeout_raw)
        except ValueError:
            timeout_seconds = 25.0

        data: dict[str, str] = {}
        if model_alias:
            data["model"] = model_alias

        try:
            response = requests.post(
                f"{base_url}/audio/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                data=data,
                files={"file": (filename or "voice.webm", audio_bytes, content_type or "audio/webm")},
                timeout=timeout_seconds,
            )
        except requests.RequestException:
            return None

        if response.status_code >= 400:
            return None

        try:
            payload = response.json()
        except ValueError:
            return None

        text = payload.get("text") or payload.get("transcript")
        if isinstance(text, str) and text.strip():
            return text.strip()
        return None


class LocalWhisperSttAdapter(SttAdapter):
    backend_name = "local_whisper"

    def _load_model(self):
        global _LOCAL_WHISPER_MODEL
        global _LOCAL_WHISPER_MODEL_NAME

        model_name = os.getenv("LOCAL_STT_MODEL", "tiny")
        device = os.getenv("LOCAL_STT_DEVICE", "cpu")
        compute_type = os.getenv("LOCAL_STT_COMPUTE_TYPE", "int8")

        if _LOCAL_WHISPER_MODEL is not None and _LOCAL_WHISPER_MODEL_NAME == model_name:
            return _LOCAL_WHISPER_MODEL

        from faster_whisper import WhisperModel

        _LOCAL_WHISPER_MODEL = WhisperModel(model_name, device=device, compute_type=compute_type)
        _LOCAL_WHISPER_MODEL_NAME = model_name
        return _LOCAL_WHISPER_MODEL

    def transcribe(self, audio_bytes: bytes, filename: str, content_type: str) -> str | None:
        _ = content_type
        language = os.getenv("LOCAL_STT_LANGUAGE", "").strip() or None

        try:
            model = self._load_model()
        except Exception:
            return None

        suffix = ".webm"
        if filename and "." in filename:
            suffix = f".{filename.rsplit('.', 1)[-1]}"

        temp_path = ""
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp:
                temp.write(audio_bytes)
                temp_path = temp.name

            segments, _info = model.transcribe(
                temp_path,
                language=language,
                vad_filter=False,
                condition_on_previous_text=False,
            )
            text = " ".join(segment.text.strip() for segment in segments if segment.text and segment.text.strip())
            return text.strip() or None
        except Exception:
            return None
        finally:
            if temp_path:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass


def _stt_adapter_chain() -> list[SttAdapter]:
    backend = os.getenv("STT_BACKEND", "auto").strip().lower()
    if backend == "nvidia":
        return [NvidiaSttAdapter()]
    if backend == "local_whisper":
        return [LocalWhisperSttAdapter()]
    return [NvidiaSttAdapter(), LocalWhisperSttAdapter()]


def transcribe_audio_with_telemetry(audio_bytes: bytes, filename: str, content_type: str) -> TranscriptionResult | None:
    size_bytes = len(audio_bytes)
    adapters = _stt_adapter_chain()

    for adapter in adapters:
        started = time.perf_counter()
        text = adapter.transcribe(audio_bytes, filename, content_type)
        duration_ms = int((time.perf_counter() - started) * 1000)

        logger.info(
            "voice_transcribe backend=%s ok=%s duration_ms=%s bytes=%s",
            adapter.backend_name,
            bool(text),
            duration_ms,
            size_bytes,
        )

        if text:
            return TranscriptionResult(text=text, backend=adapter.backend_name, duration_ms=duration_ms)

    return None
