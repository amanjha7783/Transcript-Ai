from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Optional


@dataclass
class VideoMetadata:
    title: str
    duration: Optional[float] = None
    thumbnail_url: Optional[str] = None
    source_type: str = "url"
    source_url: str = ""
    extractor: str = "unknown"
    width: Optional[int] = None
    height: Optional[int] = None
    filesize: Optional[int] = None


class BaseVideoProvider(ABC):
    """Abstract base provider for video extraction."""

    name: str = "base"

    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """Check if this provider can handle the given URL."""
        pass

    @abstractmethod
    def get_metadata(self, url: str) -> VideoMetadata:
        """Extract metadata without necessarily downloading full video."""
        pass

    @abstractmethod
    def download(
        self,
        url: str,
        output_path: str,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> VideoMetadata:
        """Download video to target output_path."""
        pass

    def check_prerequisites(self) -> dict[str, Any]:
        """Check runtime dependencies for this provider."""
        return {"ready": True, "details": "No special prerequisites"}
