import asyncio
import logging

from youtube_transcript_api import (
    NoTranscriptFound,
    TranscriptsDisabled,
    YouTubeTranscriptApi,
)

from src.config import config

logger = logging.getLogger(__name__)
_api = YouTubeTranscriptApi()


def format_transcript(segments: list[dict], max_minutes: int) -> str:
    max_seconds = max_minutes * 60
    lines = []
    for seg in segments:
        if seg["start"] > max_seconds:
            break
        total = int(seg["start"])
        m, s = divmod(total, 60)
        lines.append(f"[{m:02d}:{s:02d}] {seg['text'].strip()}")
    return "\n".join(lines)


def fetch_transcript(video_id: str) -> str | None:
    try:
        fetched = _api.fetch(video_id, languages=["en", "en-US", "en-GB"])
        segments = [{"start": s.start, "duration": s.duration, "text": s.text} for s in fetched.snippets]
        return format_transcript(segments, config.max_transcript_minutes)
    except (TranscriptsDisabled, NoTranscriptFound):
        logger.info("No transcript for video %s - skipping", video_id)
        return None
    except Exception as e:
        logger.warning("Transcript fetch failed for %s: %s", video_id, e)
        return None


async def fetch_all_transcripts(video_ids: list[str]) -> dict[str, str | None]:
    loop = asyncio.get_running_loop()
    tasks = [loop.run_in_executor(None, fetch_transcript, vid) for vid in video_ids]
    results = await asyncio.gather(*tasks)
    return dict(zip(video_ids, results, strict=False))
