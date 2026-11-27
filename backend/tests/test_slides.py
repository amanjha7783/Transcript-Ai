from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.services.providers.direct_url import DirectUrlProvider
from app.services.providers.registry import detect_platform, get_provider, get_system_capabilities
from app.services.providers.youtube import YouTubeProvider
from app.services.slide_export import generate_slide_pdf, generate_slide_zip
from app.services.slide_extractor import (
    SlideExtractor, compute_dhash, compute_sharpness,
    compute_structural_similarity, format_timestamp, hamming_distance,
)


def create_synthetic_test_video(output_path: str, fps: int = 10) -> list[dict]:
    """Generate a 6-second synthetic lecture video with 3 distinct slides."""
    w, h = 640, 360
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(output_path, fourcc, float(fps), (w, h))

    # 3 distinct slides: Blue, Green, Red
    slides_info = [
        {"title": "Slide 1: Introduction", "color": (180, 50, 50), "seconds": 2.0},
        {"title": "Slide 2: Computer Vision", "color": (50, 180, 50), "seconds": 2.0},
        {"title": "Slide 3: Neural Networks", "color": (50, 50, 180), "seconds": 2.0},
    ]

    for slide in slides_info:
        frame = np.full((h, w, 3), slide["color"], dtype=np.uint8)
        # Add high-contrast text
        cv2.putText(
            frame,
            slide["title"],
            (40, 180),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        total_frames = int(slide["seconds"] * fps)
        for _ in range(total_frames):
            out.write(frame)

    out.release()
    return slides_info


def test_dhash_and_hamming_distance():
    # Two identical images should have Hamming distance 0
    img1 = np.zeros((100, 100), dtype=np.uint8)
    cv2.circle(img1, (50, 50), 20, 255, -1)

    img2 = img1.copy()
    h1 = compute_dhash(img1)
    h2 = compute_dhash(img2)
    assert hamming_distance(h1, h2) == 0

    # A significantly different image should have high Hamming distance
    img3 = np.zeros((100, 100), dtype=np.uint8)
    cv2.rectangle(img3, (10, 10), (90, 90), 255, -1)
    h3 = compute_dhash(img3)
    assert hamming_distance(h1, h3) > 0


def test_sharpness_and_structural_similarity():
    # Crisp image with sharp edges has higher sharpness than blurred image
    sharp_img = np.zeros((100, 100), dtype=np.uint8)
    cv2.putText(sharp_img, "SHARP", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.0, 255, 2)
    blurred_img = cv2.GaussianBlur(sharp_img, (9, 9), 5.0)

    sharp_score = compute_sharpness(sharp_img)
    blur_score = compute_sharpness(blurred_img)
    assert sharp_score > blur_score

    # Same image has correlation ~ 1.0
    sim = compute_structural_similarity(sharp_img, sharp_img)
    assert sim >= 0.99


def test_format_timestamp():
    assert format_timestamp(0) == "00:00:00"
    assert format_timestamp(65) == "00:01:05"
    assert format_timestamp(3665) == "01:01:05"


def test_ssrf_protection_direct_url_provider():
    provider = DirectUrlProvider()

    # Public safe URLs pass scheme/extension check
    assert provider.can_handle("https://example.com/lecture.mp4")
    assert provider.can_handle("http://example.org/video.webm")
    assert not provider.can_handle("https://example.com/page.html")

    # Localhost, private IPs, metadata IP must be blocked
    with pytest.raises(ValueError, match="Access to internal/loopback hosts is not permitted."):
        provider._validate_ssrf_safety("http://localhost/test.mp4")

    with pytest.raises(ValueError, match="Access to internal/loopback hosts is not permitted."):
        provider._validate_ssrf_safety("http://127.0.0.1:8080/video.mp4")


def test_provider_registry_and_detection():
    assert detect_platform("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "youtube"
    assert detect_platform("https://youtu.be/dQw4w9WgXcQ") == "youtube"
    assert detect_platform("https://example.com/files/slides.mp4") == "direct"

    yt_provider = get_provider("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert isinstance(yt_provider, YouTubeProvider)

    direct_provider = get_provider("https://example.com/files/slides.mp4")
    assert isinstance(direct_provider, DirectUrlProvider)

    with pytest.raises(ValueError, match="No supported provider found"):
        get_provider("ftp://invalid.protocol/video.mp4")


def test_system_capabilities():
    caps = get_system_capabilities()
    assert "ffmpeg" in caps
    assert "ffprobe" in caps
    assert "opencv" in caps
    assert "pillow" in caps
    assert "yt_dlp" in caps
    assert "javascript_runtimes" in caps
    assert caps["opencv"]["available"] is True
    assert caps["pillow"]["available"] is True


def test_slide_extraction_on_synthetic_video():
    with tempfile.TemporaryDirectory() as tmp_dir:
        video_path = os.path.join(tmp_dir, "synthetic_lecture.mp4")
        create_synthetic_test_video(video_path, fps=10)

        extractor = SlideExtractor(
            sample_fps=1.0,
            output_width=640,
            min_interval_seconds=1.0,
            detection_threshold=0.02,
            similarity_threshold=0.88,
        )

        frames_dir = os.path.join(tmp_dir, "frames")
        candidates = extractor.extract_candidate_frames(video_path, frames_dir)
        assert len(candidates) >= 5

        slides_out_dir = os.path.join(tmp_dir, "output_slides")
        accepted = extractor.analyze_and_deduplicate(candidates, slides_out_dir)

        # There are exactly 3 distinct slides in the synthetic video
        assert len(accepted) == 3
        assert accepted[0].frame_index == 1
        assert accepted[1].frame_index == 2
        assert accepted[2].frame_index == 3

        # Check timestamp ordering
        assert accepted[0].timestamp < accepted[1].timestamp < accepted[2].timestamp
        assert accepted[0].timestamp_formatted == "00:00:00"

        # Check output images exist
        for slide in accepted:
            full_path = os.path.join(slides_out_dir, slide.image_path)
            assert os.path.isfile(full_path)
            thumb_path = full_path.replace(".jpg", "_thumb.jpg")
            assert os.path.isfile(thumb_path)

        # Test PDF generation
        pdf_path = os.path.join(slides_out_dir, "test_slides.pdf")
        slides_info = [
            {"image_filename": s.image_path, "timestamp_formatted": s.timestamp_formatted}
            for s in accepted
        ]
        generate_slide_pdf(slides_info, slides_out_dir, pdf_path, video_title="Synthetic Lecture")
        assert os.path.isfile(pdf_path)
        assert os.path.getsize(pdf_path) > 1000

        # Test ZIP generation
        zip_path = os.path.join(slides_out_dir, "test_slides.zip")
        generate_slide_zip(slides_info, slides_out_dir, zip_path, video_title="Synthetic Lecture")
        assert os.path.isfile(zip_path)
        assert os.path.getsize(zip_path) > 1000
