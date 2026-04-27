import os
import tempfile
import threading
from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

router = APIRouter(prefix="/api/transcribe", tags=["transcribe"])

_model = None
_model_lock = threading.Lock()


def _resolve_device_and_compute() -> tuple[str, str]:
    device = os.environ.get("WHISPER_DEVICE", "auto").lower()
    compute = os.environ.get("WHISPER_COMPUTE_TYPE", "auto").lower()

    if device == "auto":
        try:
            import ctranslate2
            device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
        except Exception:
            device = "cpu"

    if compute == "auto":
        compute = "float16" if device == "cuda" else "int8"

    return device, compute


def get_model():
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is not None:
            return _model
        from faster_whisper import WhisperModel
        model_name = os.environ.get("WHISPER_MODEL", "kotoba-tech/kotoba-whisper-v2.0-faster")
        device, compute = _resolve_device_and_compute()
        _model = WhisperModel(model_name, device=device, compute_type=compute)
    return _model


class TranscribeOut(BaseModel):
    text: str
    language: str
    duration: float


def whisper_enabled() -> bool:
    return os.environ.get("WHISPER_ENABLED", "true").lower() not in ("false", "0", "no")


@router.post("", response_model=TranscribeOut)
@router.post("/", response_model=TranscribeOut)
async def transcribe(audio: UploadFile = File(...)):
    if not whisper_enabled():
        raise HTTPException(503, "Speech-to-text is not available in this deployment")

    data = await audio.read()
    if not data:
        raise HTTPException(400, "Empty audio upload")

    suffix = os.path.splitext(audio.filename or "")[1] or ".webm"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(data)
        tmp.close()
        try:
            model = get_model()
        except Exception as e:
            raise HTTPException(500, f"Failed to load Whisper model: {e}")

        segments, info = model.transcribe(
            tmp.name,
            language="ja",
            vad_filter=True,
            beam_size=5,
            condition_on_previous_text=False,
        )
        text = "".join(seg.text for seg in segments).strip()
        return TranscribeOut(
            text=text,
            language=info.language,
            duration=info.duration,
        )
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
