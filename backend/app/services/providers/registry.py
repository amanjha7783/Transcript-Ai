from __future__ import annotations

import shutil
from typing import Any, Optional
from urllib.parse import urlparse

from app.services.providers.base import BaseVideoProvider
from app.services.providers.direct_url import DirectUrlProvider
from app.services.providers.generic_extractor import GenericExtractorProvider
from app.services.providers.youtube import YouTubeProvider

# Ordered list of providers: YouTube -> Direct file URL -> Generic extractor
PROVIDERS: list[BaseVideoProvider] = [
    YouTubeProvider(),
    DirectUrlProvider(),
    GenericExtractorProvider(),
]


def get_provider(url: str) -> BaseVideoProvider:
    """Find the appropriate provider for a given URL."""
    cleaned = url.strip()
    for provider in PROVIDERS:
        if provider.can_handle(cleaned):
            return provider
    raise ValueError(
        f"No supported provider found for URL '{url}'. "
        "Supported inputs: YouTube links, Vimeo/Dailymotion links, or direct public video files (.mp4, .webm, .mov, etc.). "
        "Or you can upload the video file directly."
    )


def detect_platform(url: str) -> str:
    """Detect platform name from URL."""
    try:
        provider = get_provider(url)
        return provider.name
    except ValueError:
        parsed = urlparse(url.strip())
        return parsed.hostname or "unknown"


def get_system_capabilities() -> dict[str, Any]:
    """Inspect and return system capabilities for video processing and slide extraction."""
    ffmpeg_path = shutil.which("ffmpeg")
    ffprobe_path = shutil.which("ffprobe")

    has_yt_dlp = False
    yt_dlp_version = None
    try:
        import yt_dlp
        import yt_dlp.version
        has_yt_dlp = True
        yt_dlp_version = yt_dlp.version.__version__
    except (ImportError, AttributeError):
        pass

    has_cv2 = False
    cv2_version = None
    try:
        import cv2
        has_cv2 = True
        cv2_version = cv2.__version__
    except ImportError:
        pass

    has_pil = False
    try:
        import PIL
        has_pil = True
    except ImportError:
        pass

    runtimes = {}
    for rt in ["deno", "node", "bun", "qjs"]:
        p = shutil.which(rt)
        runtimes[rt] = {"available": bool(p), "path": p}

    return {
        "ffmpeg": {"available": bool(ffmpeg_path), "path": ffmpeg_path},
        "ffprobe": {"available": bool(ffprobe_path), "path": ffprobe_path},
        "opencv": {"available": has_cv2, "version": cv2_version},
        "pillow": {"available": has_pil},
        "yt_dlp": {"available": has_yt_dlp, "version": yt_dlp_version},
        "javascript_runtimes": runtimes,
        "slide_extraction_ready": bool(ffmpeg_path and has_cv2 and has_pil),
    }
