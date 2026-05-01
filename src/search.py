import logging
import math
import re
import time

from googleapiclient.discovery import build

from src.config import config

logger = logging.getLogger(__name__)

_yt = build("youtube", "v3", developerKey=config.youtube_api_key)
_cache: dict[str, tuple[list, float]] = {}


def _cache_key(query: str) -> str:
    return query.strip().lower()


def _get_cached(query: str) -> list | None:
    key = _cache_key(query)
    if key in _cache:
        results, ts = _cache[key]
        if time.time() - ts < config.cache_ttl_seconds:
            logger.debug("Cache hit for query %r", query)
            return results
    return None


def _set_cached(query: str, results: list) -> None:
    _cache[_cache_key(query)] = (results, time.time())


def _parse_duration_seconds(iso: str) -> int:
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso)
    if not m:
        return 0
    return int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + int(m.group(3) or 0)


def _rank_score(position: int, view_count: int) -> float:
    return (1 / (position + 1)) * math.log10(max(view_count, 1))


def get_top_videos(query: str, n: int) -> list[dict]:
    cached = _get_cached(query)
    if cached is not None:
        return cached[:n]

    search_resp = (
        _yt.search()
        .list(
            q=query,
            type="video",
            videoCaption="closedCaption",
            relevanceLanguage="en",
            maxResults=10,
            part="id,snippet",
        )
        .execute()
    )

    items = search_resp.get("items", [])
    if not items:
        return []

    video_ids = [item["id"]["videoId"] for item in items]

    meta_resp = (
        _yt.videos()
        .list(
            id=",".join(video_ids),
            part="contentDetails,statistics",
        )
        .execute()
    )

    meta = {v["id"]: v for v in meta_resp.get("items", [])}

    results = []
    for position, item in enumerate(items):
        vid_id = item["id"]["videoId"]
        m = meta.get(vid_id, {})
        content = m.get("contentDetails", {})
        stats = m.get("statistics", {})

        if content.get("caption") == "false":
            continue

        duration = _parse_duration_seconds(content.get("duration", "PT0S"))
        if duration < 180:
            continue

        view_count = int(stats.get("viewCount", 0))
        if not view_count:
            continue

        results.append(
            {
                "video_id": vid_id,
                "title": item["snippet"]["title"],
                "channel": item["snippet"]["channelTitle"],
                "duration_seconds": duration,
                "view_count": view_count,
                "score": _rank_score(position, view_count),
            }
        )

    results.sort(key=lambda r: r["score"], reverse=True)
    _set_cached(query, results)
    logger.info("Search for %r returned %d usable videos", query, len(results))
    return results[:n]
