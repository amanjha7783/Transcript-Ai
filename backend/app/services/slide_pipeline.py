from __future__ import annotations

import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.database import SessionLocal
from app.models import Slide, SlideExtractionJob, Video
from app.services.providers.registry import get_provider
from app.services.slide_export import generate_slide_pdf, generate_slide_zip
from app.services.slide_extractor import SlideExtractor, format_timestamp, get_video_info

BASE_DIR = Path(__file__).resolve().parents[2]
UPLOADS_DIR = Path(settings.uploads_dir)
if not UPLOADS_DIR.is_absolute():
    UPLOADS_DIR = (BASE_DIR / UPLOADS_DIR).resolve()

SLIDES_DIR = Path(settings.slides_dir)
if not SLIDES_DIR.is_absolute():
    SLIDES_DIR = (BASE_DIR / SLIDES_DIR).resolve()

TEMP_DIR = Path(settings.temp_dir)
if not TEMP_DIR.is_absolute():
    TEMP_DIR = (BASE_DIR / TEMP_DIR).resolve()

SLIDES_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)


def get_video_slides_dir(user_id: str, video_id: str) -> Path:
    """Get absolute directory for a video's extracted slides."""
    p = SLIDES_DIR / str(user_id) / str(video_id)
    p.mkdir(parents=True, exist_ok=True)
    return p


def run_slide_extraction_job(video_id: str, job_id: str, user_settings: Optional[dict[str, Any]] = None) -> None:
    """Execute the full slide extraction pipeline as a background task."""
    db: Session = SessionLocal()
    temp_video_path: Optional[Path] = None
    temp_frames_dir: Optional[Path] = None

    try:
        job = db.query(SlideExtractionJob).filter(SlideExtractionJob.id == job_id).first()
        video = db.query(Video).filter(Video.id == video_id).first()

        if not job or not video:
            return

        cfg = user_settings or {}
        sample_fps = float(cfg.get("sample_fps", settings.slide_sample_fps))
        output_width = int(cfg.get("output_width", settings.slide_output_width))
        min_interval = float(cfg.get("min_interval_seconds", settings.slide_min_interval_seconds))
        detection_thresh = float(cfg.get("detection_threshold", settings.slide_detection_threshold))
        similarity_thresh = float(cfg.get("similarity_threshold", settings.slide_similarity_threshold))
        duplicate_removal = bool(cfg.get("duplicate_removal", True))

        extractor = SlideExtractor(
            sample_fps=sample_fps,
            output_width=output_width,
            min_interval_seconds=min_interval,
            detection_threshold=detection_thresh,
            similarity_threshold=similarity_thresh if duplicate_removal else 0.999,
            max_slides=settings.slide_max_extracted,
        )

        job.status = "processing"
        job.current_stage = "resolving_source"
        job.progress = 5.0
        db.commit()

        # Step 1: Resolve video source file
        video_source_path: Path
        is_temp_download = False

        if video.source_type == "upload" and video.media_filename:
            video_source_path = UPLOADS_DIR / video.media_filename
            if not video_source_path.is_file():
                raise FileNotFoundError(f"Uploaded media file '{video.media_filename}' is missing from storage.")
        elif video.source_url:
            job.current_stage = "downloading_video"
            job.progress = 8.0
            db.commit()

            provider = get_provider(video.source_url)
            temp_video_path = TEMP_DIR / f"{video_id}_{uuid.uuid4().hex[:8]}.mp4"
            is_temp_download = True

            def download_progress(pct: float, msg: str) -> None:
                # Progress from 8% to 25%
                job.progress = 8.0 + (pct * 0.17)
                job.current_stage = msg[:50]
                db.commit()

            meta = provider.download(video.source_url, str(temp_video_path), progress_callback=download_progress)
            video_source_path = temp_video_path
            if meta.title and video.title.startswith("YouTube video"):
                video.title = meta.title
                db.commit()
        else:
            raise ValueError("Video has neither an uploaded file nor a valid source URL.")

        # Step 2: Probe video metadata with ffprobe
        info = get_video_info(str(video_source_path))
        if info.get("duration") and (not video.duration or video.duration <= 0):
            video.duration = float(info["duration"])
            db.commit()

        # Step 3: Extract candidate frames
        job.current_stage = "extracting_frames"
        job.progress = 25.0
        db.commit()

        temp_frames_dir = TEMP_DIR / f"{video_id}_frames_{uuid.uuid4().hex[:8]}"

        def frame_progress(pct: float, msg: str) -> None:
            job.progress = pct
            job.current_stage = msg[:50]
            db.commit()

        candidates = extractor.extract_candidate_frames(
            str(video_source_path),
            str(temp_frames_dir),
            progress_callback=frame_progress,
        )

        job.total_frames_processed = len(candidates)
        job.current_stage = "detecting_slides"
        job.progress = 35.0
        db.commit()

        # Step 4: Perceptual similarity analysis and deduplication
        video_slide_dir = get_video_slides_dir(str(video.user_id), str(video.id))

        def analysis_progress(pct: float, msg: str) -> None:
            job.progress = pct
            job.current_stage = msg[:50]
            db.commit()

        accepted = extractor.analyze_and_deduplicate(
            candidates,
            str(video_slide_dir),
            progress_callback=analysis_progress,
        )

        if not accepted:
            raise RuntimeError(
                "No distinct presentation slides could be detected in this video. "
                "Ensure the video contains presentation slides or try adjusting detection sensitivity."
            )

        job.total_slides_detected = len(accepted)
        job.current_stage = "saving_slides"
        job.progress = 82.0
        db.commit()

        # Delete previous slide records for this video to keep clean state
        db.query(Slide).filter(Slide.video_id == video.id).delete()

        saved_slides_info = []
        for slide_obj in accepted:
            db_slide = Slide(
                video_id=video.id,
                user_id=video.user_id,
                slide_index=slide_obj.frame_index,
                image_filename=slide_obj.image_path,
                thumbnail_filename=slide_obj.image_path.replace(".jpg", "_thumb.jpg"),
                timestamp_seconds=slide_obj.timestamp,
                timestamp_formatted=slide_obj.timestamp_formatted,
                width=slide_obj.width,
                height=slide_obj.height,
                perceptual_hash=slide_obj.phash,
            )
            db.add(db_slide)
            saved_slides_info.append({
                "slide_index": slide_obj.frame_index,
                "image_filename": slide_obj.image_path,
                "timestamp_formatted": slide_obj.timestamp_formatted,
                "timestamp_seconds": slide_obj.timestamp,
            })

        db.flush()

        # Step 5: Generate PDF and ZIP export
        job.current_stage = "generating_pdf"
        job.progress = 90.0
        db.commit()

        pdf_path = video_slide_dir / "slides.pdf"
        generate_slide_pdf(
            saved_slides_info,
            str(video_slide_dir),
            str(pdf_path),
            video_title=video.title,
        )
        job.pdf_filename = "slides.pdf"

        zip_path = video_slide_dir / "slides.zip"
        generate_slide_zip(
            saved_slides_info,
            str(video_slide_dir),
            str(zip_path),
            video_title=video.title,
        )
        job.zip_filename = "slides.zip"

        # Finalize job
        job.status = "completed"
        job.progress = 100.0
        job.current_stage = "completed"
        job.completed_at = datetime.now(timezone.utc)
        job.error_message = None
        db.commit()

    except Exception as exc:
        db.rollback()
        job = db.query(SlideExtractionJob).filter(SlideExtractionJob.id == job_id).first()
        if job:
            job.status = "failed"
            job.current_stage = "failed"
            job.error_message = str(exc)[:1000]
            db.commit()
    finally:
        # Clean up temporary frames directory
        if temp_frames_dir and temp_frames_dir.exists():
            try:
                shutil.rmtree(temp_frames_dir, ignore_errors=True)
            except OSError:
                pass
        # Clean up temporary downloaded video
        if temp_video_path and temp_video_path.exists():
            try:
                temp_video_path.unlink(missing_ok=True)
            except OSError:
                pass
        db.close()
