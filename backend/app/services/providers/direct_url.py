from __future__ import annotations

import ipaddress
import os
import socket
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse

import httpx

from app.core.config import settings
from app.services.providers.base import BaseVideoProvider, VideoMetadata


class DirectUrlProvider(BaseVideoProvider):
    """Secure direct HTTP/HTTPS video URL downloader with SSRF protection."""

    name: str = "direct"
    SUPPORTED_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v", ".mpg", ".mpeg"}

    def can_handle(self, url: str) -> bool:
        parsed = urlparse(url.strip())
        if parsed.scheme not in {"http", "https"}:
            return False
        path_lower = parsed.path.lower()
        return any(path_lower.endswith(ext) for ext in self.SUPPORTED_EXTENSIONS)

    def _validate_ssrf_safety(self, url: str) -> tuple[str, int]:
        """Validate that host does not resolve to loopback, private, or metadata IPs."""
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError(f"Unsupported URL scheme: {parsed.scheme}. Only HTTP/HTTPS are allowed.")

        hostname = parsed.hostname
        if not hostname:
            raise ValueError("URL has no hostname.")

        port = parsed.port or (443 if parsed.scheme == "https" else 80)

        # Disallow explicit localhost or metadata hostnames
        lowered = hostname.lower()
        if lowered in {"localhost", "127.0.0.1", "::1", "metadata.google.internal"}:
            raise ValueError("Access to internal/loopback hosts is not permitted.")

        # Resolve IP addresses
        try:
            addr_info = socket.getaddrinfo(hostname, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise ValueError(f"Could not resolve host '{hostname}': {exc}") from exc

        if not addr_info:
            raise ValueError(f"Could not resolve IP for host '{hostname}'.")

        for entry in addr_info:
            sockaddr = entry[4]
            ip_str = sockaddr[0]
            ip_obj = ipaddress.ip_address(ip_str)

            # Block private, loopback, link-local, multicast, reserved addresses
            if (
                ip_obj.is_private
                or ip_obj.is_loopback
                or ip_obj.is_link_local
                or ip_obj.is_multicast
                or ip_obj.is_reserved
                or str(ip_obj) == "169.254.169.254"  # AWS / GCP metadata IP
            ):
                raise ValueError(
                    f"Access to private/internal network addresses ({ip_str}) is blocked for security."
                )

        return hostname, port

    def get_metadata(self, url: str) -> VideoMetadata:
        self._validate_ssrf_safety(url)
        parsed = urlparse(url)
        filename = Path(parsed.path).name or "direct_video.mp4"
        title = Path(filename).stem.replace("_", " ").replace("-", " ").capitalize()

        try:
            with httpx.Client(timeout=10.0, follow_redirects=False) as client:
                res = client.head(url)
                filesize = None
                if "content-length" in res.headers:
                    try:
                        filesize = int(res.headers["content-length"])
                    except ValueError:
                        pass
                return VideoMetadata(
                    title=title[:200],
                    source_type="direct_url",
                    source_url=url,
                    extractor="direct",
                    filesize=filesize,
                )
        except Exception:
            return VideoMetadata(
                title=title[:200],
                source_type="direct_url",
                source_url=url,
                extractor="direct",
            )

    def download(
        self,
        url: str,
        output_path: str,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> VideoMetadata:
        current_url = url
        max_redirects = 5
        max_bytes = settings.slide_max_video_size_mb * 1024 * 1024

        client = httpx.Client(timeout=httpx.Timeout(connect=15.0, read=60.0, write=60.0, pool=60.0))
        try:
            # Handle redirects securely by checking SSRF on every hop
            redirects = 0
            while redirects <= max_redirects:
                self._validate_ssrf_safety(current_url)
                req = client.build_request("GET", current_url)
                res = client.send(req, stream=True)

                if res.status_code in {301, 302, 303, 307, 308}:
                    location = res.headers.get("location")
                    if not location:
                        raise ValueError("Redirect response missing Location header.")
                    res.close()
                    # Resolve relative redirect if needed
                    parsed_loc = urlparse(location)
                    if not parsed_loc.netloc:
                        base = urlparse(current_url)
                        location = f"{base.scheme}://{base.netloc}{location}"
                    current_url = location
                    redirects += 1
                    continue
                break

            if res.status_code >= 400:
                res.close()
                raise ValueError(f"HTTP error {res.status_code} downloading video from URL.")

            content_type = res.headers.get("content-type", "").lower()
            if content_type and not (
                content_type.startswith("video/")
                or content_type.startswith("application/octet-stream")
                or content_type.startswith("binary/octet-stream")
            ):
                res.close()
                raise ValueError(
                    f"URL returned non-video content-type: '{content_type}'. Please verify direct video link."
                )

            content_length = res.headers.get("content-length")
            total_size = int(content_length) if content_length and content_length.isdigit() else None
            if total_size and total_size > max_bytes:
                res.close()
                raise ValueError(
                    f"Video file size ({total_size / (1024*1024):.1f} MB) exceeds maximum allowed limit ({settings.slide_max_video_size_mb} MB)."
                )

            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            downloaded = 0

            with open(output_path, "wb") as out_file:
                for chunk in res.iter_bytes(chunk_size=128 * 1024):
                    if not chunk:
                        continue
                    downloaded += len(chunk)
                    if downloaded > max_bytes:
                        out_file.close()
                        try:
                            os.remove(output_path)
                        except OSError:
                            pass
                        raise ValueError(
                            f"Downloaded size exceeded maximum allowed limit of {settings.slide_max_video_size_mb} MB."
                        )

                    out_file.write(chunk)
                    if progress_callback and total_size:
                        pct = (downloaded / total_size) * 100.0
                        progress_callback(pct, f"Downloaded {downloaded / (1024*1024):.1f} MB")
            res.close()

            parsed = urlparse(url)
            filename = Path(parsed.path).name or "direct_video.mp4"
            title = Path(filename).stem.replace("_", " ").replace("-", " ").capitalize()

            return VideoMetadata(
                title=title[:200],
                source_type="direct_url",
                source_url=url,
                extractor="direct",
                filesize=downloaded,
            )
        finally:
            client.close()
