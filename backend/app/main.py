from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database import SessionLocal, get_db, init_db
from app.models import (
    Chapter, ChatMessage, Summary, StudyMaterial, TranscriptChunk,
    TranscriptSegment, Translation, User, Video,
)
from app.security import create_access_token, get_current_user, hash_password, verify_password
from app.services.embeddings import embed_texts
from app.services.llm import generate
from app.services.media import extract_audio
from app.services.rag import index_video, retrieve, transcript_segments
from app.services.subtitles import make_subtitles
from app.services.transcription import transcribe_audio
from app.services.youtube import extract_youtube_id, fetch_youtube_transcript

BASE_DIR = Path(__file__).resolve().parents[1]
UPLOADS_DIR = Path(settings.uploads_dir)
if not UPLOADS_DIR.is_absolute():
    UPLOADS_DIR = (BASE_DIR / UPLOADS_DIR).resolve()
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="VideoMind AI API",
    version="1.0.0",
    description="Multilingual video transcription, translation, summarization, and RAG-based learning API.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AuthRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UrlRequest(BaseModel):
    url: str = Field(min_length=10, max_length=2000)


class TranslateRequest(BaseModel):
    language: str = Field(min_length=2, max_length=20)
    language_name: str = Field(default="", max_length=80)


class SummaryRequest(BaseModel):
    kind: str = Field(default="detailed", max_length=50)
    language: str = Field(default="original", max_length=20)


class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=5000)
    language: str = Field(default="auto", max_length=30)
    top_k: int = Field(default=5, ge=1, le=12)


class StudyRequest(BaseModel):
    kind: str = Field(pattern="^(notes|mcqs|flashcards|viva)$")
    language: str = Field(default="original", max_length=20)
    difficulty: str = Field(default="medium", pattern="^(easy|medium|hard|mixed)$")
    count: int = Field(default=10, ge=1, le=50)


class TranscriptUpdate(BaseModel):
    segments: list[dict[str, Any]]


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=1000)
    top_k: int = Field(default=8, ge=1, le=20)


def _video_dict(video: Video) -> dict[str, Any]:
    return {
        "id": video.id,
        "title": video.title,
        "source_type": video.source_type,
        "source_url": video.source_url,
        "thumbnail_url": video.thumbnail_url,
        "duration": video.duration,
        "language": video.language,
        "status": video.status,
        "rag_status": video.rag_status,
        "error_message": video.error_message,
        "created_at": video.created_at.isoformat() if video.created_at else None,
    }


def _get_video(db: Session, video_id: str, user: User) -> Video:
    video = db.query(Video).filter(Video.id == video_id, Video.user_id == user.id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return video


def _save_segments(db: Session, video: Video, segments: list[dict[str, Any]], language: str | None, duration: float | None = None) -> None:
    db.query(TranscriptSegment).filter(TranscriptSegment.video_id == video.id).delete()
    clean_segments = []
    for index, segment in enumerate(segments):
        text = str(segment.get("text", "")).strip()
        if not text:
            continue
        start = max(0.0, float(segment.get("start", 0)))
        end = max(start, float(segment.get("end", start)))
        clean_segments.append({"text": text, "start": start, "end": end, "speaker": segment.get("speaker")})
        db.add(TranscriptSegment(
            video_id=video.id,
            segment_index=len(clean_segments) - 1,
            text=text,
            start=start,
            end=end,
            speaker=segment.get("speaker"),
        ))
    video.language = language or video.language or "unknown"
    video.duration = duration or (clean_segments[-1]["end"] if clean_segments else None)
    db.flush()
    try:
        index_video(db, video, clean_segments)
        video.rag_status = "indexed"
    except Exception as exc:  # transcription should remain available when embedding setup is incomplete
        db.query(TranscriptChunk).filter(TranscriptChunk.video_id == video.id).delete()
        video.rag_status = "indexing_failed"
        video.error_message = f"Transcript ready; RAG indexing failed: {str(exc)[:350]}"
    video.status = "ready"
    db.commit()


def _process_uploaded_video(video_id: str) -> None:
    db = SessionLocal()
    try:
        video = db.query(Video).filter(Video.id == video_id).first()
        if not video or not video.media_filename:
            return
        video.status = "processing"
        db.commit()
        video_path = UPLOADS_DIR / video.media_filename
        audio_path = UPLOADS_DIR / f"{video.id}.audio.mp3"
        extract_audio(str(video_path), str(audio_path))
        segments, language, duration = transcribe_audio(str(audio_path))
        _save_segments(db, video, segments, language, duration)
        try:
            audio_path.unlink(missing_ok=True)
        except OSError:
            pass
    except Exception as exc:
        db.rollback()
        video = db.query(Video).filter(Video.id == video_id).first()
        if video:
            video.status = "failed"
            video.error_message = str(exc)[:1000]
            db.commit()
    finally:
        db.close()


def _process_youtube_video(video_id: str) -> None:
    db = SessionLocal()
    try:
        video = db.query(Video).filter(Video.id == video_id).first()
        if not video or not video.source_url:
            return
        video.status = "processing"
        db.commit()
        youtube_id = extract_youtube_id(video.source_url)
        segments, language = fetch_youtube_transcript(youtube_id)
        if not segments:
            raise RuntimeError("No captions were returned for this video. Upload a video file or try a video with captions enabled.")
        video.title = f"YouTube video {youtube_id}"
        video.thumbnail_url = f"https://img.youtube.com/vi/{youtube_id}/hqdefault.jpg"
        _save_segments(db, video, segments, language)
    except Exception as exc:
        db.rollback()
        video = db.query(Video).filter(Video.id == video_id).first()
        if video:
            video.status = "failed"
            video.error_message = str(exc)[:1000]
            db.commit()
    finally:
        db.close()


def _require_transcript(db: Session, video: Video) -> list[dict[str, Any]]:
    segments = transcript_segments(db, video.id)
    if not segments:
        raise HTTPException(status_code=409, detail="The transcript is not ready yet.")
    return segments


def _parse_json_response(text: str) -> Any:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start_candidates = [pos for pos in (cleaned.find("{"), cleaned.find("[")) if pos >= 0]
        if not start_candidates:
            raise ValueError("Model response did not contain JSON")
        start = min(start_candidates)
        end = max(cleaned.rfind("}"), cleaned.rfind("]"))
        return json.loads(cleaned[start:end + 1])


def _get_language_segments(db: Session, video: Video, language: str) -> list[dict[str, Any]]:
    if language in {"original", video.language, ""}:
        return _require_transcript(db, video)
    translation = db.query(Translation).filter(
        Translation.video_id == video.id, Translation.language == language
    ).order_by(Translation.created_at.desc()).first()
    if not translation:
        raise HTTPException(status_code=404, detail=f"No translation found for language '{language}'.")
    return translation.segments


def _require_llm() -> None:
    if not settings.llm_api_key and not settings.llm_base_url:
        raise HTTPException(
            status_code=503,
            detail="LLM is not configured. Set LLM_API_KEY, or set LLM_BASE_URL and LLM_MODEL for an OpenAI-compatible local model.",
        )


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/api/health")
def health():
    return {"status": "ok", "app": settings.app_name, "llm_configured": bool(settings.llm_api_key or settings.llm_base_url)}


@app.post("/api/auth/register")
def register(payload: AuthRequest, db: Session = Depends(get_db)):
    email = payload.email.lower().strip()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    user = User(id=str(uuid.uuid4()), email=email, password_hash=hash_password(payload.password))
    db.add(user)
    db.commit()
    return {"access_token": create_access_token(user.id), "token_type": "bearer", "user": {"id": user.id, "email": user.email}}


@app.post("/api/auth/login")
def login(payload: AuthRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email.lower().strip()).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    return {"access_token": create_access_token(user.id), "token_type": "bearer", "user": {"id": user.id, "email": user.email}}


@app.get("/api/auth/me")
def me(user: User = Depends(get_current_user)):
    return {"id": user.id, "email": user.email}


@app.post("/api/videos/upload")
async def upload_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    allowed = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".mpeg", ".mpg"}
    suffix = Path(file.filename or "video.mp4").suffix.lower()
    if suffix not in allowed:
        raise HTTPException(status_code=415, detail=f"Unsupported video extension '{suffix}'. Supported: {', '.join(sorted(allowed))}")
    video_id = str(uuid.uuid4())
    safe_name = f"{video_id}{suffix}"
    destination = UPLOADS_DIR / safe_name
    size = 0
    try:
        with destination.open("wb") as output:
            while True:
                data = await file.read(1024 * 1024)
                if not data:
                    break
                size += len(data)
                if size > settings.max_upload_mb * 1024 * 1024:
                    raise HTTPException(status_code=413, detail=f"File exceeds the {settings.max_upload_mb} MB limit.")
                output.write(data)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await file.close()
    video = Video(
        id=video_id,
        user_id=user.id,
        title=Path(file.filename or "Uploaded video").stem[:500],
        source_type="upload",
        media_filename=safe_name,
        status="queued",
        rag_status="pending",
    )
    db.add(video)
    db.commit()
    background_tasks.add_task(_process_uploaded_video, video_id)
    return _video_dict(video)


@app.post("/api/videos/process-url")
def process_url(payload: UrlRequest, background_tasks: BackgroundTasks, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        youtube_id = extract_youtube_id(payload.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    video = Video(
        id=str(uuid.uuid4()),
        user_id=user.id,
        title=f"YouTube video {youtube_id}",
        source_type="youtube",
        source_url=payload.url,
        thumbnail_url=f"https://img.youtube.com/vi/{youtube_id}/hqdefault.jpg",
        status="queued",
        rag_status="pending",
    )
    db.add(video)
    db.commit()
    background_tasks.add_task(_process_youtube_video, video.id)
    return _video_dict(video)


@app.get("/api/videos")
def list_videos(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    videos = db.query(Video).filter(Video.user_id == user.id).order_by(Video.created_at.desc()).all()
    return [_video_dict(video) for video in videos]


@app.get("/api/videos/{video_id}")
def get_video(video_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _video_dict(_get_video(db, video_id, user))


@app.get("/api/videos/{video_id}/status")
def video_status(video_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    video = _get_video(db, video_id, user)
    return {"id": video.id, "status": video.status, "rag_status": video.rag_status, "error_message": video.error_message}


@app.get("/api/videos/{video_id}/transcript")
def get_transcript(video_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    video = _get_video(db, video_id, user)
    segments = transcript_segments(db, video.id)
    return {
        "video_id": video.id,
        "language": video.language,
        "segments": segments,
        "text": "\n".join(segment["text"] for segment in segments),
        "word_count": sum(len(segment["text"].split()) for segment in segments),
    }


@app.put("/api/videos/{video_id}/transcript")
def update_transcript(video_id: str, payload: TranscriptUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    video = _get_video(db, video_id, user)
    if not payload.segments:
        raise HTTPException(status_code=400, detail="Transcript cannot be empty.")
    _save_segments(db, video, payload.segments, video.language)
    return {"message": "Transcript updated and RAG index refreshed.", "rag_status": video.rag_status}


@app.post("/api/videos/{video_id}/translate")
def translate_video(video_id: str, payload: TranslateRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    video = _get_video(db, video_id, user)
    segments = _require_transcript(db, video)
    _require_llm()
    language_name = payload.language_name.strip() or payload.language
    translated: list[dict[str, Any]] = []
    # Batch transcript segments to preserve timestamps while keeping prompts bounded.
    for offset in range(0, len(segments), 20):
        batch = segments[offset:offset + 20]
        source = [{"index": offset + i, "text": item["text"]} for i, item in enumerate(batch)]
        result = generate(
            "You are a professional subtitle translator. Translate faithfully, retain technical terms where appropriate, and return ONLY valid JSON as an array of objects with index and text fields.",
            f"Translate these transcript segments into {language_name} ({payload.language}). Preserve every index and do not merge or omit segments.\nINPUT JSON:\n{json.dumps(source, ensure_ascii=False)}",
            temperature=0.1,
        )
        try:
            parsed = _parse_json_response(result)
            mapped = {int(item["index"]): str(item["text"]) for item in parsed}
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Could not parse translation response: {exc}") from exc
        for i, original in enumerate(batch):
            global_index = offset + i
            translated.append({
                "text": mapped.get(global_index, original["text"]),
                "start": original["start"],
                "end": original["end"],
                "speaker": original.get("speaker"),
            })
    existing = db.query(Translation).filter(Translation.video_id == video.id, Translation.language == payload.language).first()
    if existing:
        existing.segments = translated
    else:
        db.add(Translation(video_id=video.id, language=payload.language, segments=translated))
    db.commit()
    return {"language": payload.language, "language_name": language_name, "segments": translated}


@app.get("/api/videos/{video_id}/translations")
def list_translations(video_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _get_video(db, video_id, user)
    return [{"language": item.language, "created_at": item.created_at.isoformat()} for item in db.query(Translation).filter(Translation.video_id == video_id).all()]


@app.get("/api/videos/{video_id}/translations/{language}")
def get_translation(video_id: str, language: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _get_video(db, video_id, user)
    translation = db.query(Translation).filter(
        Translation.video_id == video_id, Translation.language == language
    ).order_by(Translation.created_at.desc()).first()
    if not translation:
        raise HTTPException(status_code=404, detail="Translation not found.")
    return {"language": translation.language, "segments": translation.segments}


@app.post("/api/videos/{video_id}/summarize")
def summarize_video(video_id: str, payload: SummaryRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    video = _get_video(db, video_id, user)
    segments = _get_language_segments(db, video, payload.language)
    _require_llm()
    transcript = "\n".join(f"[{item['start']:.1f}s-{item['end']:.1f}s] {item['text']}" for item in segments)
    if len(transcript) > 18000:
        partials = []
        for offset in range(0, len(transcript), 15000):
            partials.append(generate(
                "Summarize only the supplied transcript. Do not add outside facts.",
                f"Create concise notes from this section:\n{transcript[offset:offset + 15000]}",
            ))
        source_text = "\n\n".join(partials)
    else:
        source_text = transcript
    language = "the original transcript language" if payload.language == "original" else payload.language
    content = generate(
        "You are a careful video summarization assistant. Use only the provided source content. Preserve important facts, and state uncertainty rather than inventing details.",
        f"Create a {payload.kind} summary in {language}. Use clear headings and bullets where helpful.\nSOURCE TRANSCRIPT:\n{source_text}",
    )
    db.add(Summary(video_id=video.id, kind=payload.kind, language=payload.language, content=content))
    db.commit()
    return {"kind": payload.kind, "language": payload.language, "content": content}


@app.post("/api/videos/{video_id}/chat")
def chat_with_video(video_id: str, payload: ChatRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    video = _get_video(db, video_id, user)
    _require_transcript(db, video)
    _require_llm()
    try:
        sources = retrieve(db, video.id, payload.question, payload.top_k)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"RAG retrieval is unavailable: {exc}") from exc
    if not sources:
        raise HTTPException(status_code=409, detail="No indexed transcript chunks were found. Check the video's RAG indexing status.")
    history = db.query(ChatMessage).filter(
        ChatMessage.video_id == video.id, ChatMessage.user_id == user.id
    ).order_by(ChatMessage.created_at.desc()).limit(8).all()
    history_text = "\n".join(f"{item.role}: {item.content}" for item in reversed(history))
    context = "\n\n".join(
        f"[Source {i + 1}; {item['start']:.2f}s-{item['end']:.2f}s]\n{item['text']}"
        for i, item in enumerate(sources)
    )
    answer = generate(
        "You are VideoMind AI, a grounded video question-answering assistant. Answer primarily from the supplied transcript excerpts. If the excerpts do not support an answer, say that the video transcript does not provide enough information. Do not invent quotes or timestamps. The user may ask in a different language; answer in the requested language or mirror the user's language. Cite relevant sources using [Source 1], [Source 2], etc.",
        f"VIDEO: {video.title}\nANSWER LANGUAGE: {payload.language}\nRECENT CHAT:\n{history_text or '(none)'}\n\nRETRIEVED TRANSCRIPT CONTEXT:\n{context}\n\nQUESTION:\n{payload.question}",
        temperature=0.2,
    )
    db.add(ChatMessage(video_id=video.id, user_id=user.id, role="user", content=payload.question))
    db.add(ChatMessage(video_id=video.id, user_id=user.id, role="assistant", content=answer, sources=sources))
    db.commit()
    return {"answer": answer, "sources": sources}


@app.get("/api/videos/{video_id}/chat-history")
def chat_history(video_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _get_video(db, video_id, user)
    messages = db.query(ChatMessage).filter(
        ChatMessage.video_id == video_id, ChatMessage.user_id == user.id
    ).order_by(ChatMessage.created_at.asc()).all()
    return [{"role": m.role, "content": m.content, "sources": m.sources, "created_at": m.created_at.isoformat()} for m in messages]


@app.post("/api/videos/{video_id}/study")
def generate_study_material(video_id: str, payload: StudyRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    video = _get_video(db, video_id, user)
    segments = _require_transcript(db, video)
    _require_llm()
    # Retrieve transcript evidence for the requested learning task instead of blindly
    # passing an entire long transcript to the LLM.
    retrieval_queries = {
        "notes": "Create comprehensive study notes covering the key topics, concepts, definitions, examples, and formulas discussed in this video.",
        "mcqs": "Find important concepts, facts, definitions, comparisons, and examples that can be tested in multiple-choice questions.",
        "flashcards": "Find core terms, definitions, concepts, and concise explanations suitable for learning flashcards.",
        "viva": "Find the central concepts, reasoning, applications, and explanations that could be asked in a viva examination.",
    }
    try:
        sources = retrieve(db, video.id, retrieval_queries[payload.kind], top_k=12)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"RAG retrieval is unavailable: {exc}") from exc
    if not sources:
        raise HTTPException(status_code=409, detail="No indexed transcript chunks were found for study generation.")
    transcript = "\n\n".join(
        f"[Source {i + 1}; {item['start']:.1f}s-{item['end']:.1f}s] {item['text']}"
        for i, item in enumerate(sources)
    )
    language = "the original language" if payload.language == "original" else payload.language
    instructions = {
        "notes": "Create structured study notes with headings, definitions, examples, and key takeaways. Return Markdown text.",
        "mcqs": f"Create {payload.count} multiple-choice questions with four options each, correct answer, explanation, difficulty, and source timestamp. Return ONLY a JSON array of objects with question, options, answer, explanation, difficulty, timestamp.",
        "flashcards": f"Create {payload.count} useful flashcards. Return ONLY a JSON array of objects with question, answer, and timestamp.",
        "viva": f"Create {payload.count} viva questions with concise answers, difficulty, and timestamp. Return ONLY a JSON array of objects with question, answer, difficulty, timestamp.",
    }
    result = generate(
        "You are an educational assistant. Base every item only on the supplied transcript. Do not invent topics, facts, or timestamps. If a detail is not in the source, omit it.",
        f"Language: {language}. Difficulty: {payload.difficulty}.\nTask: {instructions[payload.kind]}\nTRANSCRIPT:\n{transcript}",
        temperature=0.2,
    )
    try:
        content: Any = {"markdown": result} if payload.kind == "notes" else _parse_json_response(result)
    except Exception:
        content = {"raw": result}
    db.add(StudyMaterial(video_id=video.id, kind=payload.kind, language=payload.language, content=content))
    db.commit()
    return {"kind": payload.kind, "language": payload.language, "content": content, "sources": sources}


@app.post("/api/videos/{video_id}/chapters")
def generate_chapters(video_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    video = _get_video(db, video_id, user)
    segments = _require_transcript(db, video)
    _require_llm()
    transcript = "\n".join(f"[{item['start']:.1f}-{item['end']:.1f}] {item['text']}" for item in segments)
    if len(transcript) > 25000:
        transcript = transcript[:25000]
    raw = generate(
        "You are a video chaptering assistant. Return only valid JSON: an array of objects containing title, summary, start, end. Use only timestamps present in the transcript and create sequential, non-overlapping chapters.",
        f"Create meaningful chapters for this video transcript. Aim for 4-12 chapters depending on length.\n{transcript}",
        temperature=0.1,
    )
    try:
        items = _parse_json_response(raw)
        if not isinstance(items, list):
            raise ValueError("Expected array")
        db.query(Chapter).filter(Chapter.video_id == video.id).delete()
        saved = []
        for item in items:
            start = max(0.0, float(item["start"]))
            end = max(start, float(item["end"]))
            chapter = Chapter(video_id=video.id, title=str(item["title"])[:500], summary=str(item.get("summary", "")), start=start, end=end)
            db.add(chapter)
            saved.append({"title": chapter.title, "summary": chapter.summary, "start": start, "end": end})
        db.commit()
        return {"chapters": saved}
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail=f"Could not create valid chapters: {exc}") from exc


@app.get("/api/videos/{video_id}/chapters")
def list_chapters(video_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _get_video(db, video_id, user)
    chapters = db.query(Chapter).filter(Chapter.video_id == video_id).order_by(Chapter.start).all()
    return [{"title": c.title, "summary": c.summary, "start": c.start, "end": c.end} for c in chapters]


@app.post("/api/videos/{video_id}/search")
def search_transcript(video_id: str, payload: SearchRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    video = _get_video(db, video_id, user)
    _require_transcript(db, video)
    try:
        results = retrieve(db, video.id, payload.query, payload.top_k)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Semantic search is unavailable: {exc}") from exc
    return {"results": results}


@app.get("/api/videos/{video_id}/subtitles/{language}")
def download_subtitles(video_id: str, language: str, fmt: str = Query(default="srt", pattern="^(srt|vtt)$"), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    video = _get_video(db, video_id, user)
    segments = _get_language_segments(db, video, language)
    content = make_subtitles(segments, fmt)
    filename = f"videomind-{video.id}-{language}.{fmt}"
    media_type = "text/vtt" if fmt == "vtt" else "application/x-subrip"
    return StreamingResponse(iter([content]), media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.get("/api/videos/{video_id}/export")
def export_video(
    video_id: str,
    kind: str = Query(default="transcript", pattern="^(transcript|summary|study|chat)$"),
    fmt: str = Query(default="txt", pattern="^(txt|md|pdf|docx)$"),
    language: str = Query(default="original"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    video = _get_video(db, video_id, user)
    if kind == "transcript":
        segments = _get_language_segments(db, video, language)
        text_content = "\n".join(f"[{s['start']:.2f}s - {s['end']:.2f}s] {s['text']}" for s in segments)
    elif kind == "summary":
        summary = db.query(Summary).filter(Summary.video_id == video_id, Summary.language == language).order_by(Summary.created_at.desc()).first()
        if not summary:
            raise HTTPException(status_code=404, detail="No summary found for this language.")
        text_content = summary.content
    elif kind == "study":
        material = db.query(StudyMaterial).filter(StudyMaterial.video_id == video_id).order_by(StudyMaterial.created_at.desc()).first()
        if not material:
            raise HTTPException(status_code=404, detail="No study material found.")
        text_content = material.content.get("markdown") if isinstance(material.content, dict) and "markdown" in material.content else json.dumps(material.content, ensure_ascii=False, indent=2)
    else:
        messages = db.query(ChatMessage).filter(ChatMessage.video_id == video_id, ChatMessage.user_id == user.id).order_by(ChatMessage.created_at.asc()).all()
        text_content = "\n\n".join(f"{m.role.upper()}: {m.content}" for m in messages)
    filename = f"videomind-{kind}-{video.id}.{fmt}"
    if fmt in {"txt", "md"}:
        return StreamingResponse(iter([text_content]), media_type="text/markdown" if fmt == "md" else "text/plain", headers={"Content-Disposition": f'attachment; filename="{filename}"'})
    output = None
    if fmt == "docx":
        try:
            from docx import Document
            from io import BytesIO
            doc = Document()
            doc.add_heading(video.title, 0)
            for paragraph in text_content.split("\n"):
                doc.add_paragraph(paragraph)
            output = BytesIO()
            doc.save(output)
            output.seek(0)
            media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        except ImportError as exc:
            raise HTTPException(status_code=501, detail="Install python-docx to export DOCX.") from exc
    else:
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas
            from io import BytesIO
            output = BytesIO()
            pdf = canvas.Canvas(output, pagesize=A4)
            width, height = A4
            y = height - 50
            pdf.setFont("Helvetica-Bold", 16)
            pdf.drawString(45, y, video.title[:85])
            y -= 30
            pdf.setFont("Helvetica", 9)
            for raw_line in text_content.splitlines():
                words = raw_line.split()
                line = ""
                for word in words:
                    if len(line) + len(word) > 105:
                        pdf.drawString(45, y, line)
                        y -= 13
                        line = word
                        if y < 45:
                            pdf.showPage(); y = height - 45; pdf.setFont("Helvetica", 9)
                    else:
                        line = f"{line} {word}".strip()
                if line:
                    pdf.drawString(45, y, line); y -= 13
                if y < 45:
                    pdf.showPage(); y = height - 45; pdf.setFont("Helvetica", 9)
            pdf.save(); output.seek(0)
            media = "application/pdf"
        except ImportError as exc:
            raise HTTPException(status_code=501, detail="Install reportlab to export PDF.") from exc
    return StreamingResponse(output, media_type=media, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.get("/api/videos/{video_id}/media")
def stream_media(video_id: str, token: str = Query(...), db: Session = Depends(get_db)):
    # Query token is used only for the HTML video element, which cannot attach a Bearer header.
    import jwt
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        user_id = payload.get("sub")
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid media token") from exc
    video = db.query(Video).filter(Video.id == video_id, Video.user_id == user_id).first()
    if not video or not video.media_filename:
        raise HTTPException(status_code=404, detail="Uploaded media not found")
    path = UPLOADS_DIR / video.media_filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Media file is missing")
    return FileResponse(path, media_type="video/mp4", filename=video.media_filename)


@app.delete("/api/videos/{video_id}")
def delete_video(video_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    video = _get_video(db, video_id, user)
    filename = video.media_filename
    db.delete(video)
    db.commit()
    if filename:
        (UPLOADS_DIR / filename).unlink(missing_ok=True)
    (UPLOADS_DIR / f"{video_id}.audio.mp3").unlink(missing_ok=True)
    return {"message": "Video and associated data deleted."}
