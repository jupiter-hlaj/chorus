import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    youtube_api_key: str
    gemini_api_key: str
    max_videos: int
    max_transcript_minutes: int
    cache_ttl_seconds: int
    log_level: str
    environment: str
    model: str


def _require(key: str) -> str:
    value = os.environ.get(key)
    if not value:
        raise ValueError(f"Required environment variable {key!r} is not set")
    return value


config = Config(
    youtube_api_key=_require("YOUTUBE_API_KEY"),
    gemini_api_key=_require("GEMINI_API_KEY"),
    max_videos=int(os.environ.get("MAX_VIDEOS", "5")),
    max_transcript_minutes=int(os.environ.get("MAX_TRANSCRIPT_MINUTES", "30")),
    cache_ttl_seconds=int(os.environ.get("CACHE_TTL_SECONDS", "3600")),
    log_level=os.environ.get("LOG_LEVEL", "INFO"),
    environment=os.environ.get("ENVIRONMENT", "dev"),
    model=os.environ.get("CHORUS_MODEL", "gemini-2.5-flash"),
)
