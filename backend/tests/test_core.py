from app.services.rag import build_chunks
from app.services.subtitles import make_subtitles
from app.services.youtube import extract_youtube_id


def test_chunking_preserves_text_and_time_ranges():
    segments = [
        {"text": "one two three", "start": 0.0, "end": 1.0},
        {"text": "four five six", "start": 1.0, "end": 2.0},
        {"text": "seven eight nine", "start": 2.0, "end": 3.0},
    ]
    chunks = build_chunks(segments, max_words=5, overlap_words=0)
    assert chunks[0]["start"] == 0.0
    assert chunks[-1]["end"] == 3.0
    assert "one two three" in " ".join(chunk["text"] for chunk in chunks)
    assert len(chunks) >= 2


def test_srt_and_vtt_timestamps():
    segments = [{"text": "Hello world", "start": 1.25, "end": 2.5}]
    srt = make_subtitles(segments, "srt")
    vtt = make_subtitles(segments, "vtt")
    assert "00:00:01,250 --> 00:00:02,500" in srt
    assert "WEBVTT" in vtt
    assert "00:00:01.250 --> 00:00:02.500" in vtt


def test_youtube_url_validation_and_id_extraction():
    assert extract_youtube_id("https://youtu.be/abcdefghijk") == "abcdefghijk"
    assert extract_youtube_id("https://www.youtube.com/watch?v=abcdefghijk") == "abcdefghijk"
    try:
        extract_youtube_id("http://127.0.0.1/admin")
    except ValueError:
        pass
    else:
        raise AssertionError("non-YouTube URL should be rejected")
