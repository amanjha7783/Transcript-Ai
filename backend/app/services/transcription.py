from functools import lru_cache
from app.core.config import settings


@lru_cache(maxsize=1)
def get_whisper_model():
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("faster-whisper is not installed. Install backend requirements.") from exc
    return WhisperModel(
        settings.whisper_model,
        device=settings.whisper_device,
        compute_type=settings.whisper_compute_type,
    )


def transcribe_audio(audio_path: str) -> tuple[list[dict], str | None, float | None]:
    model = get_whisper_model()
    segments_iter, info = model.transcribe(audio_path, beam_size=5, vad_filter=True)
    segments = []
    for index, segment in enumerate(segments_iter):
        text = segment.text.strip()
        if text:
            segments.append({
                "segment_index": index,
                "text": text,
                "start": float(segment.start),
                "end": float(segment.end),
                "speaker": None,
            })
    return segments, getattr(info, "language", None), getattr(info, "duration", None)
