# Chorus — YouTube Opinion Aggregator (local)

Ask a question. Get the internet's real opinion — sourced from YouTube, synthesized across multiple videos, with clickable links to the exact timestamp where each point was made.

## What it is

A local Python web app. Type a question, it searches YouTube, fetches transcripts in parallel, sends them to Gemini in one prompt, returns a structured answer with timestamp-deep-linked citations.

## Why local-only

YouTube blocks transcript fetches from cloud provider IP ranges (AWS, GCP, Azure). The original spec assumed AWS Lambda would work; it does not. Running from a residential IP — like your laptop — works.

## Run it

```
cp .env.example .env       # then fill in the two API keys
make install               # one-time: creates .venv, installs deps
make run                   # starts on http://127.0.0.1:8000
```

Open `http://127.0.0.1:8000` in a browser.

## Required env vars

| Var | Where to get it |
|---|---|
| `YOUTUBE_API_KEY` | console.cloud.google.com → APIs & Services → YouTube Data API v3 → API Key |
| `GEMINI_API_KEY` | aistudio.google.com → Get API key |

Both are free-tier sufficient for personal use.

Optional:
- `MAX_VIDEOS` (default 5)
- `MAX_TRANSCRIPT_MINUTES` (default 30)
- `CACHE_TTL_SECONDS` (default 3600) — in-memory cache for YouTube searches
- `CHORUS_MODEL` (default `gemini-2.5-flash`)
- `LOG_LEVEL` (default INFO)

## Architecture

```
Browser  →  uvicorn (FastAPI)  ─┬─→  YouTube Data API v3   (search + metadata)
                                ├─→  youtube-transcript-api (parallel fetch)
                                └─→  Gemini API             (one synthesis call)
```

Files:
- `src/config.py` — env var loading + validation at import time
- `src/search.py` — YouTube search + filter + rank + cache
- `src/transcripts.py` — parallel transcript fetch via thread pool, [MM:SS] format
- `src/synthesize.py` — single Gemini call, structured JSON response
- `src/app.py` — FastAPI app: GET /, GET /health, POST /search
- `static/index.html` — vanilla single-page UI
- `tests/` — pytest suite (29 tests)

## Cost rules

- Cap transcripts at `MAX_TRANSCRIPT_MINUTES` before sending to Gemini.
- Cap videos at `MAX_VIDEOS`.
- One Gemini call per query — pack all transcripts into one prompt.
- Cache YouTube search results by normalized query (10,000-units/day free quota).

## Quotas

- YouTube Data API v3: 10,000 units/day free (~90 queries).
- Gemini API (AI Studio free tier): 1,500 requests/day, 15 req/min.

## Dev

```
make test          # pytest
make lint          # ruff + bandit
```
