from urllib.parse import urlparse, parse_qs

ALLOWED_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "www.youtube-nocookie.com"}


def extract_youtube_id(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or (parsed.hostname or "").lower() not in ALLOWED_HOSTS:
        raise ValueError("For URL processing, this MVP currently accepts YouTube URLs only.")
    host = (parsed.hostname or "").lower()
    if host == "youtu.be":
        video_id = parsed.path.strip("/").split("/")[0]
    elif parsed.path == "/watch":
        video_id = parse_qs(parsed.query).get("v", [""])[0]
    else:
        parts = [part for part in parsed.path.split("/") if part]
        video_id = parts[1] if len(parts) >= 2 and parts[0] in {"embed", "shorts", "live"} else ""
    if not video_id or len(video_id) > 20 or not all(ch.isalnum() or ch in "-_" for ch in video_id):
        raise ValueError("Could not identify a valid YouTube video ID in this URL.")
    return video_id


def fetch_youtube_transcript(video_id: str) -> tuple[list[dict], str | None]:
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError as exc:
        raise RuntimeError("youtube-transcript-api is not installed.") from exc
    transcript = YouTubeTranscriptApi().fetch(video_id, languages=["en", "hi", "mr", "bn", "gu", "ta", "te", "kn", "ml", "pa", "ur"])
    segments = []
    for index, snippet in enumerate(transcript.snippets):
        segments.append({
            "segment_index": index,
            "text": snippet.text.replace("\n", " ").strip(),
            "start": float(snippet.start),
            "end": float(snippet.start + snippet.duration),
            "speaker": None,
        })
    return segments, getattr(transcript, "language_code", None)
