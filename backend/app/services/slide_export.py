from __future__ import annotations

import os
import zipfile
from pathlib import Path
from typing import Sequence

from PIL import Image
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, A4
from reportlab.pdfgen import canvas


def generate_slide_pdf(
    slides_info: Sequence[dict],
    slides_base_dir: str,
    output_pdf_path: str,
    video_title: str = "Presentation Slides",
) -> str:
    """Generate a presentation PDF containing one slide per page with timestamp and title footer."""
    if not slides_info:
        raise ValueError("Cannot generate PDF: No slides provided.")

    pdf_path = Path(output_pdf_path)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    base_dir = Path(slides_base_dir)

    # Use landscape A4 (841.89 x 595.27 points)
    page_width, page_height = landscape(A4)
    margin_x = 28.0
    margin_top = 24.0
    footer_height = 36.0

    usable_width = page_width - (2 * margin_x)
    usable_height = page_height - margin_top - footer_height

    c = canvas.Canvas(str(pdf_path), pagesize=landscape(A4))

    total_slides = len(slides_info)
    clean_title = (video_title or "Presentation Slides").strip()
    if len(clean_title) > 65:
        clean_title = clean_title[:62] + "..."

    for index, slide in enumerate(slides_info, start=1):
        image_rel_path = slide.get("image_filename") or slide.get("image_path")
        if not image_rel_path:
            continue

        full_img_path = base_dir / image_rel_path
        if not full_img_path.is_file():
            continue

        # Get image dimensions using PIL
        try:
            with Image.open(full_img_path) as pil_img:
                img_w, img_h = pil_img.size
        except Exception:
            img_w, img_h = 1280, 720

        # Calculate aspect-ratio preserving dimensions to fit inside usable area
        scale = min(usable_width / img_w, usable_height / img_h)
        draw_w = img_w * scale
        draw_h = img_h * scale

        # Center horizontally and place above footer
        draw_x = margin_x + (usable_width - draw_w) / 2.0
        draw_y = footer_height + ((usable_height - draw_h) / 2.0)

        # Draw slide image
        c.drawImage(
            str(full_img_path),
            draw_x,
            draw_y,
            width=draw_w,
            height=draw_h,
            preserveAspectRatio=True,
            anchor="c",
        )

        # Footer styling
        c.setStrokeColor(colors.HexColor("#2a354d"))
        c.setLineWidth(0.75)
        c.line(margin_x, footer_height - 6, page_width - margin_x, footer_height - 6)

        c.setFont("Helvetica-Bold", 8.5)
        c.setFillColor(colors.HexColor("#333f56"))
        c.drawString(margin_x, footer_height - 18, clean_title)

        c.setFont("Helvetica", 8)
        c.setFillColor(colors.HexColor("#6b7a99"))
        center_text = "VideoMind AI  —  AI Slide Extractor"
        c.drawCentredString(page_width / 2.0, footer_height - 18, center_text)

        ts_str = slide.get("timestamp_formatted") or "00:00:00"
        right_text = f"Slide {index} of {total_slides}  |  Timestamp: {ts_str}"
        c.drawRightString(page_width - margin_x, footer_height - 18, right_text)

        c.showPage()

    c.save()
    return str(pdf_path)


def generate_slide_zip(
    slides_info: Sequence[dict],
    slides_base_dir: str,
    output_zip_path: str,
    video_title: str = "slides",
) -> str:
    """Package all extracted slide images into a single ZIP archive."""
    if not slides_info:
        raise ValueError("Cannot generate ZIP: No slides provided.")

    zip_path = Path(output_zip_path)
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    base_dir = Path(slides_base_dir)

    with zipfile.ZipFile(str(zip_path), "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for index, slide in enumerate(slides_info, start=1):
            image_rel_path = slide.get("image_filename") or slide.get("image_path")
            if not image_rel_path:
                continue

            full_img_path = base_dir / image_rel_path
            if not full_img_path.is_file():
                continue

            ts_formatted = slide.get("timestamp_formatted", "00-00-00").replace(":", "-")
            archive_filename = f"slide_{index:03d}_{ts_formatted}.jpg"
            zf.write(full_img_path, arcname=archive_filename)

    return str(zip_path)
