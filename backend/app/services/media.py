import os
import subprocess
from pathlib import Path
from fastapi import HTTPException


def extract_audio(video_path: str, audio_path: str) -> None:
    Path(audio_path).parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg", "-y", "-i", video_path, "-vn", "-ac", "1", "-ar", "16000",
        "-c:a", "mp3", "-b:a", "64k", audio_path,
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=60 * 60)
    except FileNotFoundError as exc:
        raise RuntimeError("FFmpeg is not installed or not available in PATH.") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Audio extraction timed out. Try a shorter video.") from exc
    if completed.returncode != 0 or not os.path.exists(audio_path):
        raise RuntimeError(f"FFmpeg could not extract audio: {completed.stderr[-1200:]}")
