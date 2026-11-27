from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np
from PIL import Image

from app.core.config import settings


@dataclass
class ExtractedSlideCandidate:
    frame_index: int
    timestamp: float
    timestamp_formatted: str
    image_path: str
    sharpness: float
    phash: str
    width: int
    height: int


def format_timestamp(seconds: float) -> str:
    """Format seconds into HH:MM:SS string."""
    s = max(0, int(round(seconds)))
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    return f"{h:02d}:{m:02d}:{sec:02d}"


def get_video_info(video_path: str) -> dict:
    """Extract video duration, resolution, and fps using ffprobe."""
    command = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,duration,r_frame_rate,nb_frames:format=duration",
        "-of", "json",
        video_path,
    ]
    try:
        proc = subprocess.run(command, capture_output=True, text=True, check=True, timeout=30)
        data = json.loads(proc.stdout)
    except Exception as exc:
        raise RuntimeError(f"FFprobe could not read video metadata: {exc}") from exc

    streams = data.get("streams", [])
    if not streams:
        raise RuntimeError("No video stream found in the media file.")

    v_stream = streams[0]
    width = int(v_stream.get("width") or 1280)
    height = int(v_stream.get("height") or 720)

    duration = 0.0
    if "duration" in v_stream and v_stream["duration"]:
        try:
            duration = float(v_stream["duration"])
        except ValueError:
            pass

    if duration <= 0 and "format" in data and "duration" in data["format"]:
        try:
            duration = float(data["format"]["duration"])
        except ValueError:
            pass

    fps = 30.0
    r_frame_rate = v_stream.get("r_frame_rate", "30/1")
    if "/" in r_frame_rate:
        num, den = r_frame_rate.split("/", 1)
        try:
            den_val = float(den)
            fps = float(num) / den_val if den_val > 0 else 30.0
        except ValueError:
            fps = 30.0

    return {"width": width, "height": height, "duration": duration, "fps": fps}


def compute_dhash(image_gray: np.ndarray, hash_size: int = 16) -> str:
    """Compute difference hash (dHash) for fast perceptual comparison."""
    # Resize to (hash_size + 1, hash_size)
    resized = cv2.resize(image_gray, (hash_size + 1, hash_size), interpolation=cv2.INTER_AREA)
    # Compare adjacent pixels
    diff = resized[:, 1:] > resized[:, :-1]
    # Convert binary array to hex string
    decimal_val = 0
    hex_str = []
    for index, val in enumerate(diff.flatten()):
        if val:
            decimal_val += 1 << (index % 4)
        if index % 4 == 3:
            hex_str.append(hex(decimal_val)[2:])
            decimal_val = 0
    if decimal_val:
        hex_str.append(hex(decimal_val)[2:])
    return "".join(hex_str)


def hamming_distance(hash1: str, hash2: str) -> int:
    """Calculate Hamming distance between two hex hashes."""
    if len(hash1) != len(hash2):
        return 256
    x = int(hash1, 16) ^ int(hash2, 16)
    return bin(x).count("1")



def compute_sharpness(image_gray: np.ndarray) -> float:
    """Compute image sharpness score using variance of the Laplacian."""
    return float(cv2.Laplacian(image_gray, cv2.CV_64F).var())


def compute_structural_similarity(img1_gray: np.ndarray, img2_gray: np.ndarray) -> float:
    """Compute normalized correlation coefficient on downsampled images."""
    thumb1 = cv2.resize(img1_gray, (64, 64), interpolation=cv2.INTER_AREA)
    thumb2 = cv2.resize(img2_gray, (64, 64), interpolation=cv2.INTER_AREA)
    # Correlation coefficient
    res = cv2.matchTemplate(thumb1, thumb2, cv2.TM_CCOEFF_NORMED)
    return float(res[0][0])


class SlideExtractor:
    """Computer-vision slide extraction engine using FFmpeg and OpenCV."""

    def __init__(
        self,
        sample_fps: float = 1.0,
        output_width: int = 1280,
        min_interval_seconds: float = 1.5,
        detection_threshold: float = 0.02,
        similarity_threshold: float = 0.88,
        max_slides: int = 200,
    ):
        self.sample_fps = max(0.2, min(5.0, sample_fps))
        self.output_width = max(640, min(1920, output_width))
        self.min_interval_seconds = max(0.5, min_interval_seconds)
        self.detection_threshold = max(0.005, min(0.2, detection_threshold))
        self.similarity_threshold = max(0.70, min(0.99, similarity_threshold))
        self.max_slides = max(10, min(500, max_slides))

    def extract_candidate_frames(
        self,
        video_path: str,
        temp_frames_dir: str,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> list[tuple[int, float, str]]:
        """Extract candidate frames from video using FFmpeg at configured sampling rate and width."""
        frames_dir = Path(temp_frames_dir)
        frames_dir.mkdir(parents=True, exist_ok=True)

        # Scale preserving aspect ratio (width=output_width, height computed to be even number)
        scale_filter = f"fps={self.sample_fps},scale={self.output_width}:-2"
        out_pattern = str(frames_dir / "frame_%06d.jpg")

        cmd = [
            "ffmpeg",
            "-y",
            "-i", video_path,
            "-vf", scale_filter,
            "-q:v", "2",  # High JPEG quality
            out_pattern,
        ]

        if progress_callback:
            progress_callback(10.0, "Decoding video frames with FFmpeg...")

        try:
            completed = subprocess.run(cmd, capture_output=True, text=True, timeout=60 * 60)
            if completed.returncode != 0:
                raise RuntimeError(f"FFmpeg frame extraction failed: {completed.stderr[-1000:]}")
        except FileNotFoundError as exc:
            raise RuntimeError("FFmpeg is not installed or not available on PATH.") from exc

        # Read generated frame files
        frame_files = sorted(frames_dir.glob("frame_*.jpg"))
        if not frame_files:
            raise RuntimeError("No frames could be extracted from this video.")

        # Compute accurate timestamps based on frame index and sample_fps
        frame_candidates: list[tuple[int, float, str]] = []
        for index, frame_path in enumerate(frame_files):
            timestamp = index / self.sample_fps
            frame_candidates.append((index, timestamp, str(frame_path)))

        if progress_callback:
            progress_callback(35.0, f"Extracted {len(frame_candidates)} candidate frames.")

        return frame_candidates

    def analyze_and_deduplicate(
        self,
        candidates: list[tuple[int, float, str]],
        output_dir: str,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> list[ExtractedSlideCandidate]:
        """Analyze candidates using perceptual hashing, sharpness, and stability to remove duplicates."""
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        accepted_slides: list[ExtractedSlideCandidate] = []
        last_accepted_gray: Optional[np.ndarray] = None
        last_accepted_hash: Optional[str] = None
        last_accepted_time = -999.0

        total_frames = len(candidates)
        sharpness_history: list[float] = []

        # Buffer to find the sharpest frame across a stable window
        # When a slide change occurs, we inspect the next 1-2 frames to select the crispest non-blurry transition frame
        i = 0
        while i < total_frames and len(accepted_slides) < self.max_slides:
            idx, timestamp, frame_path = candidates[i]

            img_bgr = cv2.imread(frame_path)
            if img_bgr is None:
                i += 1
                continue

            h, w = img_bgr.shape[:2]
            img_gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
            phash = compute_dhash(img_gray)
            sharpness = compute_sharpness(img_gray)
            sharpness_history.append(sharpness)

            # Check if this frame is a new slide
            is_new_slide = False
            if last_accepted_gray is None:
                # First slide
                is_new_slide = True
            else:
                time_diff = timestamp - last_accepted_time
                if time_diff >= self.min_interval_seconds:
                    # Perceptual hash Hamming distance
                    h_dist = hamming_distance(phash, last_accepted_hash)
                    # Downsampled structural correlation
                    similarity = compute_structural_similarity(img_gray, last_accepted_gray)

                    # A slide is new if structural correlation is below threshold or hash differs
                    if similarity < self.similarity_threshold or h_dist >= 14:
                        is_new_slide = True

            if is_new_slide:
                # Lookahead 1-2 frames of the SAME slide to choose the sharpest, stable frame
                best_i = i
                best_sharpness = sharpness
                best_gray = img_gray
                best_hash = phash
                slide_timestamp = timestamp
                best_path = frame_path

                lookahead_limit = min(i + 3, total_frames)
                for look_i in range(i + 1, lookahead_limit):
                    l_idx, l_time, l_path = candidates[look_i]
                    l_bgr = cv2.imread(l_path)
                    if l_bgr is None:
                        continue
                    l_gray = cv2.cvtColor(l_bgr, cv2.COLOR_BGR2GRAY)
                    l_hash = compute_dhash(l_gray)

                    # Check if lookahead frame is still the SAME slide
                    sim_with_candidate = compute_structural_similarity(l_gray, img_gray)
                    if sim_with_candidate < self.similarity_threshold:
                        # Hit transition to next slide; break lookahead
                        break

                    l_sharpness = compute_sharpness(l_gray)
                    if l_sharpness > best_sharpness:
                        best_sharpness = l_sharpness
                        best_i = look_i
                        best_gray = l_gray
                        best_hash = l_hash
                        best_path = l_path

                # Copy best frame to final slide output destination
                slide_num = len(accepted_slides) + 1
                final_filename = f"slide_{slide_num:04d}.jpg"
                final_path = str(out_dir / final_filename)
                shutil.copyfile(best_path, final_path)

                # Generate lightweight thumbnail for UI gallery
                thumb_filename = f"slide_{slide_num:04d}_thumb.jpg"
                thumb_path = str(out_dir / thumb_filename)
                try:
                    with Image.open(best_path) as pil_img:
                        pil_img.thumbnail((480, 270), Image.Resampling.LANCZOS)
                        pil_img.save(thumb_path, "JPEG", quality=82)
                except Exception:
                    # Fallback to OpenCV if PIL thumbnail fails
                    thumb_cv = cv2.resize(img_bgr, (480, int(480 * h / w)), interpolation=cv2.INTER_AREA)
                    cv2.imwrite(thumb_path, thumb_cv)

                candidate_obj = ExtractedSlideCandidate(
                    frame_index=slide_num,
                    timestamp=slide_timestamp,
                    timestamp_formatted=format_timestamp(slide_timestamp),
                    image_path=final_filename,
                    sharpness=best_sharpness,
                    phash=best_hash,
                    width=w,
                    height=h,
                )
                accepted_slides.append(candidate_obj)

                last_accepted_gray = best_gray
                last_accepted_hash = best_hash
                last_accepted_time = slide_timestamp


                # Advance past any examined lookahead frames
                i = max(i, best_i)

            i += 1

            if progress_callback and total_frames > 0:
                pct = 35.0 + (i / total_frames) * 45.0
                progress_callback(
                    pct,
                    f"Analyzed {i}/{total_frames} frames ({len(accepted_slides)} unique slides found)...",
                )

        return accepted_slides
