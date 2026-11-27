from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship
from app.database import Base
from app.core.config import settings

if settings.database_url.startswith("postgresql"):
    from pgvector.sqlalchemy import Vector
    embedding_type = Vector(settings.embedding_dimensions)
else:
    embedding_type = JSON


def utcnow():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id = Column(String(36), primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    videos = relationship("Video", back_populates="user", cascade="all, delete-orphan")


class Video(Base):
    __tablename__ = "videos"
    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(500), nullable=False)
    source_type = Column(String(30), nullable=False)
    source_url = Column(Text, nullable=True)
    media_filename = Column(String(500), nullable=True)
    thumbnail_url = Column(Text, nullable=True)
    duration = Column(Float, nullable=True)
    language = Column(String(20), nullable=True)
    status = Column(String(30), default="queued", nullable=False, index=True)
    rag_status = Column(String(30), default="pending", nullable=False)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    user = relationship("User", back_populates="videos")
    segments = relationship("TranscriptSegment", back_populates="video", cascade="all, delete-orphan", order_by="TranscriptSegment.segment_index")
    slides = relationship("Slide", back_populates="video", cascade="all, delete-orphan", order_by="Slide.slide_index")
    slide_jobs = relationship("SlideExtractionJob", back_populates="video", cascade="all, delete-orphan", order_by="SlideExtractionJob.created_at.desc()")


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"
    id = Column(Integer, primary_key=True, autoincrement=True)
    video_id = Column(String(36), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True)
    segment_index = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    start = Column(Float, nullable=False)
    end = Column(Float, nullable=False)
    speaker = Column(String(100), nullable=True)
    video = relationship("Video", back_populates="segments")


class TranscriptChunk(Base):
    __tablename__ = "transcript_chunks"
    id = Column(Integer, primary_key=True, autoincrement=True)
    video_id = Column(String(36), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    start = Column(Float, nullable=False)
    end = Column(Float, nullable=False)
    language = Column(String(20), nullable=True)
    embedding = Column(embedding_type, nullable=False)


class Translation(Base):
    __tablename__ = "translations"
    id = Column(Integer, primary_key=True, autoincrement=True)
    video_id = Column(String(36), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True)
    language = Column(String(20), nullable=False)
    segments = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class Summary(Base):
    __tablename__ = "summaries"
    id = Column(Integer, primary_key=True, autoincrement=True)
    video_id = Column(String(36), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = Column(String(50), nullable=False)
    language = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(Integer, primary_key=True, autoincrement=True)
    video_id = Column(String(36), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    sources = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class StudyMaterial(Base):
    __tablename__ = "study_materials"
    id = Column(Integer, primary_key=True, autoincrement=True)
    video_id = Column(String(36), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = Column(String(40), nullable=False)
    language = Column(String(20), nullable=False)
    content = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class Chapter(Base):
    __tablename__ = "chapters"
    id = Column(Integer, primary_key=True, autoincrement=True)
    video_id = Column(String(36), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(500), nullable=False)
    summary = Column(Text, nullable=True)
    start = Column(Float, nullable=False)
    end = Column(Float, nullable=False)


class Slide(Base):
    __tablename__ = "slides"
    id = Column(Integer, primary_key=True, autoincrement=True)
    video_id = Column(String(36), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    slide_index = Column(Integer, nullable=False)
    image_filename = Column(String(500), nullable=False)
    thumbnail_filename = Column(String(500), nullable=True)
    timestamp_seconds = Column(Float, nullable=False)
    timestamp_formatted = Column(String(20), nullable=False)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    perceptual_hash = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    video = relationship("Video", back_populates="slides")


class SlideExtractionJob(Base):
    __tablename__ = "slide_extraction_jobs"
    id = Column(String(36), primary_key=True)
    video_id = Column(String(36), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(30), default="pending", nullable=False, index=True)
    progress = Column(Float, default=0.0, nullable=False)
    current_stage = Column(String(50), default="pending", nullable=False)
    total_frames_processed = Column(Integer, default=0, nullable=False)
    total_slides_detected = Column(Integer, default=0, nullable=False)
    settings_json = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    pdf_filename = Column(String(500), nullable=True)
    zip_filename = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    video = relationship("Video", back_populates="slide_jobs")

