import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.config import config
from src.search import get_top_videos
from src.synthesize import synthesize
from src.transcripts import fetch_all_transcripts

logging.basicConfig(level=config.log_level)
logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent.parent / "static"

app = FastAPI(title="Chorus")


class SearchRequest(BaseModel):
    query: str
    max_videos: int = 5


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health():
    return {"status": "ok", "environment": config.environment}


@app.post("/search")
async def search(req: SearchRequest):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    n = min(req.max_videos, config.max_videos)
    logger.info("Search: %r, max_videos=%d", req.query, n)

    videos = get_top_videos(req.query, n)
    if not videos:
        raise HTTPException(status_code=404, detail="No suitable videos found for this query")

    transcripts = await fetch_all_transcripts([v["video_id"] for v in videos])
    for video in videos:
        video["transcript"] = transcripts.get(video["video_id"])

    usable = [v for v in videos if v.get("transcript")]
    if not usable:
        raise HTTPException(status_code=422, detail="No transcripts available for any found videos")

    result = synthesize(req.query, usable)
    result["videos_analyzed"] = len(usable)
    result["sources"] = [
        {
            "video_id": v["video_id"],
            "title": v["title"],
            "channel": v["channel"],
            "view_count": v.get("view_count", 0),
            "url": f"https://youtube.com/watch?v={v['video_id']}",
        }
        for v in usable
    ]

    for point in result.get("points", []):
        for source in point.get("sources", []):
            source["url"] = (
                f"https://youtube.com/watch?v={source.get('video_id', '')}&t={source.get('timestamp_seconds', 0)}"
            )

    return result
