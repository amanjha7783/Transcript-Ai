from __future__ import annotations

import io
import os
import shutil
import tempfile
import uuid
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.database import Base, SessionLocal, engine
from app.main import app, UPLOADS_DIR
from app.models import Slide, SlideExtractionJob, User, Video
from app.security import create_access_token, hash_password
from app.services.slide_pipeline import SLIDES_DIR


def create_mini_video(path: str) -> None:
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(path, fourcc, 10.0, (320, 240))
    for color in [(255, 0, 0), (0, 255, 0)]:
        frame = np.full((240, 320, 3), color, dtype=np.uint8)
        for _ in range(15):
            out.write(frame)
    out.release()


@pytest.fixture(scope="module")
def client():
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_user():
    db = SessionLocal()
    user_id = str(uuid.uuid4())
    user = User(
        id=user_id,
        email=f"test_{user_id[:8]}@example.com",
        password_hash=hash_password("password123"),
    )
    db.add(user)
    db.commit()
    token = create_access_token(user.id)
    db.close()
    return {"id": user.id, "email": user.email, "token": token}


def test_system_capabilities_endpoint(client):
    res = client.get("/api/system/capabilities")
    assert res.status_code == 200
    data = res.json()
    assert "ffmpeg" in data
    assert "opencv" in data
    assert "pillow" in data


def test_extract_slides_on_uploaded_video(client, auth_user):
    headers = {"Authorization": f"Bearer {auth_user['token']}"}

    # Upload video
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        mini_path = f.name
    create_mini_video(mini_path)

    try:
        with open(mini_path, "rb") as video_file:
            upload_res = client.post(
                "/api/videos/upload",
                files={"file": ("mini_lecture.mp4", video_file, "video/mp4")},
                headers=headers,
            )
        assert upload_res.status_code == 200
        video_data = upload_res.json()
        video_id = video_data["id"]

        # Call extract slides
        extract_res = client.post(
            f"/api/videos/{video_id}/slides/extract",
            json={"sample_fps": 1.0, "output_width": 640},
            headers=headers,
        )
        assert extract_res.status_code == 200
        extract_data = extract_res.json()
        assert "job_id" in extract_data
        assert extract_data["video_id"] == video_id

        # Check status
        status_res = client.get(f"/api/videos/{video_id}/slides/status", headers=headers)
        assert status_res.status_code == 200
        status_data = status_res.json()
        assert status_data["status"] in ["pending", "processing", "completed"]

        # Check list endpoint
        list_res = client.get(f"/api/videos/{video_id}/slides", headers=headers)
        assert list_res.status_code == 200
        assert "slides" in list_res.json()

        # Check delete slides endpoint
        del_res = client.delete(f"/api/videos/{video_id}/slides", headers=headers)
        assert del_res.status_code == 200

        # Delete video
        del_vid_res = client.delete(f"/api/videos/{video_id}", headers=headers)
        assert del_vid_res.status_code == 200
    finally:
        if os.path.exists(mini_path):
            try:
                os.remove(mini_path)
            except OSError:
                pass


def test_slide_endpoints_unauthorized(client):
    fake_vid = str(uuid.uuid4())
    res = client.post(f"/api/videos/{fake_vid}/slides/extract", json={})
    assert res.status_code == 401

    res = client.get(f"/api/videos/{fake_vid}/slides/status")
    assert res.status_code == 401

    res = client.delete(f"/api/videos/{fake_vid}/slides")
    assert res.status_code == 401
