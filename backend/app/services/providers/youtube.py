from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import parse_qs, urlparse

from app.core.config import settings
from app.services.providers.base import BaseVideoProvider, VideoMetadata


class YouTubeProvider(BaseVideoProvider):
    """YouTube provider using yt-dlp with JavaScript runtime detection and error handling."""

    name: str = "youtube"
    ALLOWED_HOSTS = {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "youtu.be",
        "www.youtube-nocookie.com",
    }

    def can_handle(self, url: str) -> bool:
        parsed = urlparse(url.strip())
        if parsed.scheme not in {"http", "https"}:
            return False
        hostname = (parsed.hostname or "").lower()
        return hostname in self.ALLOWED_HOSTS

    def extract_video_id(self, url: str) -> str:
        parsed = urlparse(url.strip())
        host = (parsed.hostname or "").lower()
        if host == "youtu.be":
            video_id = parsed.path.strip("/").split("/")[0]
        elif parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [""])[0]
        else:
            parts = [part for part in parsed.path.split("/") if part]
            video_id = parts[1] if len(parts) >= 2 and parts[0] in {"embed", "shorts", "live"} else ""

        if not video_id or len(video_id) > 20 or not all(ch.isalnum() or ch in "-_" for ch in video_id):
            raise ValueError("Could not identify a valid YouTube video ID in this URL.")
        return video_id

    def check_prerequisites(self) -> dict[str, Any]:
        """Check availability of yt-dlp and JS runtimes (Deno, Node, etc.)."""
        has_yt_dlp = False
        try:
            import yt_dlp
            has_yt_dlp = True
        except ImportError:
            pass

        runtimes = {}
        for rt in ["deno", "node", "bun", "qjs"]:
            path = shutil.which(rt)
            runtimes[rt] = {"available": bool(path), "path": path}

        js_ready = any(r["available"] for r in runtimes.values())
        return {
            "ready": has_yt_dlp,
            "has_yt_dlp": has_yt_dlp,
            "has_js_runtime": js_ready,
            "runtimes": runtimes,
            "recommended_runtime": "deno" if not js_ready else None,
        }

    def _get_ydl_opts(
        self,
        output_template: Optional[str] = None,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> dict[str, Any]:
        max_bytes = settings.slide_max_video_size_mb * 1024 * 1024
        opts: dict[str, Any] = {
            "format": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best[height<=1080]/best",
            "noplaylist": True,
            "max_filesize": max_bytes,
            "quiet": True,
            "no_warnings": True,
            "retries": 3,
            "socket_timeout": 30,
        }

        if output_template:
            opts["outtmpl"] = output_template

        if progress_callback:
            def hook(d: dict[str, Any]) -> None:
                status = d.get("status")
                if status == "downloading":
                    total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                    downloaded = d.get("downloaded_bytes", 0)
                    pct = (downloaded / total * 100.0) if total > 0 else 0.0
                    speed = d.get("speed")
                    speed_str = f" @ {speed / (1024*1024):.1f} MB/s" if speed else ""
                    progress_callback(pct, f"Downloading video: {pct:.1f}%{speed_str}")
                elif status == "finished":
                    progress_callback(100.0, "Video download completed")

            opts["progress_hooks"] = [hook]

        return opts

    def get_metadata(self, url: str) -> VideoMetadata:
        try:
            import yt_dlp
        except ImportError as exc:
            raise RuntimeError("yt-dlp is not installed. Please install it with pip.") from exc

        video_id = self.extract_video_id(url)
        opts = self._get_ydl_opts()
        opts["extract_flat"] = True

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if not info:
                    raise ValueError("Could not retrieve video information from YouTube.")

                title = info.get("title") or f"YouTube video {video_id}"
                duration = info.get("duration")
                thumbnail = info.get("thumbnail") or f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"

                return VideoMetadata(
                    title=title[:500],
                    duration=float(duration) if duration else None,
                    thumbnail_url=thumbnail,
                    source_type="youtube",
                    source_url=url,
                    extractor="youtube",
                    width=info.get("width"),
                    height=info.get("height"),
                )
        except Exception as exc:
            err_msg = str(exc)
            if "Sign in to confirm" in err_msg or "bot" in err_msg.lower():
                raise RuntimeError(
                    "YouTube restricted direct media access for this video (bot challenge/sign-in required). "
                    "Please download or record the lecture video and use the 'Upload Video' tab directly."
                ) from exc
            if "Private video" in err_msg or "Video unavailable" in err_msg:
                raise RuntimeError(
                    "This YouTube video is private or unavailable. Please verify the URL or upload the video file directly."
                ) from exc
            raise RuntimeError(f"Could not access YouTube video: {err_msg}") from exc

    def download(
        self,
        url: str,
        output_path: str,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> VideoMetadata:
        try:
            import yt_dlp
        except ImportError as exc:
            raise RuntimeError("yt-dlp is not installed. Please install it with pip.") from exc

        video_id = self.extract_video_id(url)
        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # yt-dlp may append extension or merge formats; use explicit target
        temp_tmpl = str(out_path.parent / f"{out_path.stem}.%(ext)s")
        opts = self._get_ydl_opts(output_template=temp_tmpl, progress_callback=progress_callback)
        opts["merge_output_format"] = "mp4"

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if not info:
                    raise ValueError("Could not download YouTube video.")

                title = info.get("title") or f"YouTube video {video_id}"
                duration = info.get("duration")
                thumbnail = info.get("thumbnail") or f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"

                # Locate actual downloaded file
                expected_mp4 = out_path.parent / f"{out_path.stem}.mp4"
                if expected_mp4.exists() and expected_mp4 != out_path:
                    if out_path.exists():
                        out_path.unlink()
                    expected_mp4.rename(out_path)
                elif not out_path.exists():
                    # Check if another extension was produced
                    candidates = list(out_path.parent.glob(f"{out_path.stem}.*"))
                    if candidates:
                        candidates[0].rename(out_path)
                    else:
                        raise RuntimeError("Downloaded media file was not found on disk.")

                filesize = out_path.stat().st_size if out_path.exists() else None

                return VideoMetadata(
                    title=title[:500],
                    duration=float(duration) if duration else None,
                    thumbnail_url=thumbnail,
                    source_type="youtube",
                    source_url=url,
                    extractor="youtube",
                    filesize=filesize,
                    width=info.get("width"),
                    height=info.get("height"),
                )
        except Exception as exc:
            err_msg = str(exc)
            if "Sign in to confirm" in err_msg or "bot" in err_msg.lower():
                raise RuntimeError(
                    "YouTube requested sign-in or anti-bot verification for media download. "
                    "In accordance with access limits, please upload the video file directly instead."
                ) from exc
            if "DRM" in err_msg or "protected" in err_msg.lower():
                raise RuntimeError(
                    "This video is DRM protected and cannot be downloaded. Please upload an unprotected lecture recording."
                ) from exc
            raise RuntimeError(f"YouTube media extraction failed: {err_msg}") from exc
