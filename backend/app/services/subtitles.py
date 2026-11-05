from typing import Iterable


def timestamp_srt(seconds: float) -> str:
    millis = max(0, int(round(seconds * 1000)))
    hours, remainder = divmod(millis, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, ms = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def timestamp_vtt(seconds: float) -> str:
    return timestamp_srt(seconds).replace(",", ".")


def make_subtitles(segments: Iterable[dict], fmt: str = "srt") -> str:
    fmt = fmt.lower()
    if fmt not in {"srt", "vtt"}:
        raise ValueError("Subtitle format must be srt or vtt.")
    lines = ["WEBVTT", ""] if fmt == "vtt" else []
    for index, segment in enumerate(segments, 1):
        start = timestamp_vtt(float(segment["start"])) if fmt == "vtt" else timestamp_srt(float(segment["start"]))
        end = timestamp_vtt(float(segment["end"])) if fmt == "vtt" else timestamp_srt(float(segment["end"]))
        if fmt == "srt":
            lines.append(str(index))
        lines.extend([f"{start} --> {end}", str(segment["text"]).strip(), ""])
    return "\n".join(lines).rstrip() + "\n"
