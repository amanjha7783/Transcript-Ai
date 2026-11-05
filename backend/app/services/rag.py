from typing import Any
from sqlalchemy.orm import Session
from app.models import TranscriptChunk, TranscriptSegment, Video
from app.services.embeddings import embed_texts, cosine_similarity


def build_chunks(segments: list[dict[str, Any]], max_words: int = 180, overlap_words: int = 35) -> list[dict[str, Any]]:
    """Create timestamp-aware chunks without splitting the source segment metadata."""
    chunks: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    word_count = 0
    for segment in segments:
        text = (segment.get("text") or "").strip()
        if not text:
            continue
        words = len(text.split())
        if current and word_count + words > max_words:
            chunks.append(_pack_chunk(current, len(chunks)))
            # Carry recent segments into the next chunk for contextual overlap.
            overlap: list[dict[str, Any]] = []
            overlap_count = 0
            for old in reversed(current):
                old_words = len(old["text"].split())
                if overlap_count + old_words > overlap_words:
                    break
                overlap.insert(0, old)
                overlap_count += old_words
            current = overlap
            word_count = overlap_count
        current.append({**segment, "text": text})
        word_count += words
    if current:
        chunks.append(_pack_chunk(current, len(chunks)))
    return chunks


def _pack_chunk(segments: list[dict[str, Any]], index: int) -> dict[str, Any]:
    return {
        "chunk_index": index,
        "text": " ".join(item["text"] for item in segments),
        "start": float(segments[0].get("start", 0)),
        "end": float(segments[-1].get("end", 0)),
    }


def index_video(db: Session, video: Video, segments: list[dict[str, Any]]) -> int:
    db.query(TranscriptChunk).filter(TranscriptChunk.video_id == video.id).delete()
    chunks = build_chunks(segments)
    vectors = embed_texts([chunk["text"] for chunk in chunks])
    for chunk, vector in zip(chunks, vectors):
        db.add(TranscriptChunk(
            video_id=video.id,
            chunk_index=chunk["chunk_index"],
            text=chunk["text"],
            start=chunk["start"],
            end=chunk["end"],
            language=video.language,
            embedding=vector,
        ))
    db.flush()
    return len(chunks)


def retrieve(db: Session, video_id: str, query: str, top_k: int = 5) -> list[dict[str, Any]]:
    query_vector = embed_texts([query])[0]
    chunks = db.query(TranscriptChunk).filter(TranscriptChunk.video_id == video_id).all()
    scored = [(cosine_similarity(chunk.embedding, query_vector), chunk) for chunk in chunks]
    scored.sort(key=lambda item: item[0], reverse=True)
    return [
        {
            "chunk_id": chunk.id,
            "text": chunk.text,
            "start": chunk.start,
            "end": chunk.end,
            "score": float(score),
        }
        for score, chunk in scored[:top_k]
    ]


def transcript_segments(db: Session, video_id: str) -> list[dict[str, Any]]:
    rows = db.query(TranscriptSegment).filter(TranscriptSegment.video_id == video_id).order_by(TranscriptSegment.segment_index).all()
    return [{"text": row.text, "start": row.start, "end": row.end, "speaker": row.speaker} for row in rows]
