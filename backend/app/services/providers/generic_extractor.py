from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import urlparse

from app.core.config import settings
from app.services.providers.base import BaseVideoProvider, VideoMetadata


class GenericExtractorProvider(BaseVideoProvider):
    """Provider for non-YouTube platforms supported by yt-dlp (e.g. Vimeo, Dailymotion, etc.)."""

    name: str = "generic_extractor"

    EXCLUDED_HOSTS = {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "youtu.be",
        "www.youtube-nocookie.com",
        "localhost",
        "127.0.0.1",
    }

    def can_handle(self, url: str) -> bool:
        parsed = urlparse(url.strip())
        if parsed.scheme not in {"http", "https"}:
            return False
        hostname = (parsed.hostname or "").lower()
        if not hostname or hostname in self.EXCLUDED_HOSTS:
            return False

        # Known common domains supported by yt-dlp
        supported_domains = ["vimeo.com", "dailymotion.com", "dai.ly", "ted.com", "coursera.org", "bilibili.com", "archive.org"]
        return any(hostname.endswith(d) for d in supported_domains)

    def get_metadata(self, url: str) -> VideoMetadata:
        try:
            import yt_dlp
        except ImportError as exc:
            raise RuntimeError("yt-dlp is not installed.") from exc

        opts = {
            "extract_flat": True,
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if not info:
                    raise ValueError("Could not extract metadata from this URL.")
                return VideoMetadata(
                    title=(info.get("title") or "Online Video")[:500],
                    duration=info.get("duration"),
                    thumbnail_url=info.get("thumbnail"),
                    source_type="url",
                    source_url=url,
                    extractor=info.get("extractor", "generic"),
                    width=info.get("width"),
                    height=info.get("height"),
                )
        except Exception as exc:
            raise RuntimeError(f"Could not retrieve video information from {url}: {exc}") from exc

    def download(
        self,
        url: str,
        output_path: str,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> VideoMetadata:
        try:
            import yt_dlp
        except ImportError as exc:
            raise RuntimeError("yt-dlp is not installed.") from exc

        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        temp_tmpl = str(out_path.parent / f"{out_path.stem}.%(ext)s")
        max_bytes = settings.slide_max_video_size_mb * 1024 * 1024

        opts: dict[str, Any] = {
            "format": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best[height<=1080]/best",
            "noplaylist": True,
            "max_filesize": max_bytes,
            "outtmpl": temp_tmpl,
            "merge_output_format": "mp4",
            "quiet": True,
            "no_warnings": True,
        }

        if progress_callback:
            def hook(d: dict[str, Any]) -> None:
                if d.get("status") == "downloading":
                    total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                    downloaded = d.get("downloaded_bytes", 0)
                    pct = (downloaded / total * 100.0) if total > 0 else 0.0
                    progress_callback(pct, f"Downloading video: {pct:.1f}%")
                elif d.get("status") == "finished":
                    progress_callback(100.0, "Download completed")
            opts["progress_hooks"] = [hook]

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if not info:
                    raise ValueError("Could not download video from platform.")

                expected_mp4 = out_path.parent / f"{out_path.stem}.mp4"
                if expected_mp4.exists() and expected_mp4 != out_path:
                    if out_path.exists():
                        out_path.unlink()
                    expected_mp4.rename(out_path)
                elif not out_path.exists():
                    candidates = list(out_path.parent.glob(f"{out_path.stem}.*"))
                    if candidates:
                        candidates[0].rename(out_path)
                    else:
                        raise RuntimeError("Downloaded media file was not found.")

                return VideoMetadata(
                    title=(info.get("title") or "Online Video")[:500],
                    duration=info.get("duration"),
                    thumbnail_url=info.get("thumbnail"),
                    source_type="url",
                    source_url=url,
                    extractor=info.get("extractor", "generic"),
                    filesize=out_path.stat().st_size if out_path.exists() else None,
                )
        except Exception as exc:
            raise RuntimeError(f"Video download failed for {url}: {exc}") from exc
