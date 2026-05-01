# Chorus — Product Overview & Architecture

---

## 1. The Problem

Research fatigue. You want to know if something is worth buying, worth learning, or worth using. So you watch one YouTube review. Then another. Then another. They contradict each other. Half an hour later you have more opinions but less clarity.

The signal is there. It lives in thousands of YouTube videos from people who actually used the thing. What's missing is synthesis — a tool that reads all of them and tells you where they agree, where they don't, and exactly where in the video each claim was made so you can verify it yourself.

That's Chorus.

---

## 2. The Core Loop

```
question
    ↓
YouTube Data API v3 search → top 10 candidates
    ↓
filter: Shorts out, no-caption videos out, < 3 min out
    ↓
rank by relevance + view count → top MAX_VIDEOS
    ↓
youtube-transcript-api → parallel fetch (thread pool), timestamped
    ↓
truncate each to MAX_TRANSCRIPT_MINUTES
    ↓
one Gemini API call → structured JSON
    ↓
verdict + key points + timestamp deep links
    ↓
render in browser
```

---

## 3. Technology Decisions

Every choice was evaluated against alternatives. This section records the reasoning so future decisions stay grounded.

---

### Python 3.13 (Runtime)

The two core dependencies — `youtube-transcript-api` and the Google Gen AI SDK — are Python-first, best-maintained in Python, and the Python implementations handle edge cases (auto-caption formats, API response quirks) that other language ports don't cover as well.

Evaluated:
- **Node.js**: `youtube-transcript` npm package is less maintained. More edge cases unhandled. Diverges from the project's toolchain.
- **Go**: No maintained YouTube transcript library. Would require implementing caption format parsing manually.
- **Python**: `youtube-transcript-api` is the reference implementation. First-party `google-api-python-client` for YouTube Data API. `google-genai` (the current Gen AI SDK; the older `google-generativeai` is end-of-life) for Gemini. `pytest`, `ruff`, `bandit` — nothing new to set up.

**Decision: Python 3.13.** Best library support. Matches Sotto's runtime.

---

### FastAPI (HTTP Framework)

Transcript fetching is I/O-bound. Five transcripts fetched sequentially would mean waiting for each to complete before starting the next. With `asyncio.gather` over thread-pool executors, all five run concurrently — total transcript fetch time drops from ~5× per-video to ~1× the slowest video.

Evaluated:
- **Flask**: Synchronous by default. Async support requires `flask[async]` plus careful handling. Not designed for concurrent I/O in the same request handler.
- **Django**: Too heavy for a 3-route app.
- **FastAPI**: Async-first. Parallel transcript fetching is idiomatic. Pydantic v2 for request validation. Mangum bridges it to Lambda with one line.

**Decision: FastAPI.** The async benefit is real and measurable for this exact workload.

---

### AWS Lambda + SAM (Deployment)

Already the deployment model for Sotto. Same AWS account, same toolchain, same CI/CD pattern. No new accounts, no new platforms.

Evaluated:
- **EC2**: Always-on server — overkill and not free for a personal tool.
- **ECS/Fargate**: Container-based, more control, but adds operational overhead and cost.
- **Lambda + SAM**: Serverless. Free tier: 1 million requests/month + 400,000 GB-seconds compute — more than enough for personal use. SAM is already used for Sotto. CI/CD pattern is identical.

**AWS region: `ca-central-1`.** Sotto uses `us-east-1` because of ACM/CloudFront requirements. Chorus has no such constraints — `ca-central-1` is physically closer to Waterloo and keeps data in Canada.

**Lambda timeout: 60 seconds.** Set at the Lambda level. Note: API Gateway HTTP API has a hard 29-second integration timeout — the browser will receive a 504 if the pipeline takes longer. Keep MAX_VIDEOS at 5 and MAX_TRANSCRIPT_MINUTES at 30 to stay well under this limit in practice.

**Decision: AWS Lambda + SAM.** Same as Sotto. No new tools, no new accounts.

---

### Mangum (ASGI ↔ Lambda Adapter)

FastAPI is an ASGI application. Lambda receives JSON events. Mangum translates between them transparently — Lambda calls `handler(event, context)`, Mangum converts the API Gateway event into an ASGI scope, calls the FastAPI app, and converts the response back.

No alternatives worth evaluating. Mangum is the standard and only maintained ASGI adapter for Lambda.

`handler = Mangum(app, lifespan="off")` — `lifespan="off"` because Lambda does not support ASGI lifespan events (startup/shutdown hooks). Using `"on"` causes silent errors on cold starts.

**Decision: Mangum.** The only option.

---

### YouTube Data API v3 (Search)

Scraping YouTube search HTML is fragile — structure changes, rate limits are opaque, metadata like duration and view count require separate requests. The Data API returns structured JSON, is stable, has a clear quota model, and provides all needed fields in one call.

**Quota math:**
- Search: 100 units
- Videos.list (duration + view count for 10 candidates): 10 units
- Total per query: ~110 units
- Free daily quota: 10,000 units
- Effective free searches/day: ~90

90 searches/day is more than enough for a personal tool.

**Decision: YouTube Data API v3.**

---

### youtube-transcript-api (Transcript Fetching)

Handles auto-generated captions and manual captions, returns timestamped segments, no OAuth required.

Evaluated:
- **yt-dlp**: Designed for media download. Overkill. Heavy dependency.
- **YouTube Data API captions endpoint**: Requires OAuth for download. The transcript API does not.
- **youtube-transcript-api**: Lightweight, no auth, handles all caption formats, well-maintained.

**Note:** This library is synchronous. On Lambda + FastAPI (async), it runs in a thread pool executor via `asyncio.get_event_loop().run_in_executor(None, fetch_transcript, video_id)`. This is the correct pattern — it keeps the async event loop unblocked while the synchronous library runs in a thread.

**Decision: youtube-transcript-api.**

---

### Gemini Flash (Synthesis)

The synthesis task is genuinely hard: read five transcripts from five different reviewers, find where they converge and conflict, extract specific quotes, attribute each to a timestamp. This requires a capable model.

- **Gemini 2.5 Flash**: Free tier. Large context window handles 5 full transcripts easily. Strong structured JSON output. This is the right model for this task at zero cost.
- **Gemini 2.0 Flash**: Older free-tier alternative. 2.5 is preferred but the env var `CHORUS_MODEL` can swap it.

Model: `gemini-2.5-flash` (free tier). Configured via env var so it can be swapped.

**Decision: Gemini Flash via Google Gemini API (free tier).** Already in the Google ecosystem for YouTube Data API — same Google Cloud project, same API key flow. Zero cost for personal tool scale.

---

## 4. Architecture

```
Browser
   │
   │ GET / → index.html
   │ POST /search → JSON
   ▼
API Gateway (HTTP API)
   │
   │ proxy all routes
   ▼
Lambda: ChorusFunction
   │
   │ Mangum (ASGI ↔ Lambda)
   ▼
FastAPI app (src/app.py)
   │
   ├── search.py ──────────► YouTube Data API v3
   │                          search + videos.list
   │                          filter + rank
   │                          in-memory cache
   │
   ├── transcripts.py ─────► youtube-transcript-api
   │                          parallel (thread pool)
   │                          [MM:SS] format
   │                          truncate at MAX_TRANSCRIPT_MINUTES
   │
   └── synthesize.py ──────► Google Gemini API
                              one call, all transcripts
                              structured JSON response
                              timestamp citations
```

---

## 5. The Synthesis Prompt (Exact)

The core of the product. Getting this right matters more than any other single decision.

```
You are analyzing {N} YouTube video transcripts to answer the user's question.

USER QUESTION: "{query}"

TRANSCRIPTS:

---
Video 1: {title}
Channel: {channel_name}
URL: https://youtube.com/watch?v={video_id}

[00:00] transcript text here
[00:05] more text
---

(repeated for each video)

INSTRUCTIONS:
1. Read all transcripts carefully.
2. Identify the key claims, opinions, and observations relevant to the user's question.
3. Note where reviewers agree and where they genuinely conflict.
4. For each key point, cite the specific timestamp(s) from the transcript(s) where it was made.
5. Only cite timestamps that actually appear in the transcripts. Do not invent timestamps.
6. Transcripts may contain auto-caption errors (no punctuation, misspelled words). Use context to interpret them.

Return ONLY valid JSON — no markdown, no preamble, no explanation:
{
  "verdict": "One or two sentences directly answering the user's question.",
  "points": [
    {
      "claim": "Specific claim or opinion found in the videos",
      "sentiment": "positive|negative|neutral|mixed",
      "sources": [
        {
          "video_id": "the video ID",
          "title": "the video title",
          "channel": "the channel name",
          "timestamp_seconds": 154,
          "timestamp_label": "2:34",
          "quote": "Brief verbatim or near-verbatim quote from the transcript"
        }
      ]
    }
  ],
  "consensus": "What most reviewers agree on, or null",
  "conflicts": "Where reviewers meaningfully disagree, or null",
  "caveats": "Important conditions or limitations mentioned, or null"
}
```

---

## 6. Video Filtering Logic

**Step 1 — Search (100 units):**
```
GET /youtube/v3/search
  ?q={query}
  &type=video
  &videoCaption=closedCaption
  &relevanceLanguage=en
  &maxResults=10
  &key={YOUTUBE_API_KEY}
```

**Step 2 — Metadata (1 unit/video, ~10 units total):**
```
GET /youtube/v3/videos
  ?id={comma-separated IDs}
  &part=contentDetails,statistics
  &key={YOUTUBE_API_KEY}
```

**Step 3 — Filter:**
- Duration < 3 minutes (180 seconds) → drop
- `contentDetails.caption == false` → drop (belt-and-suspenders on top of search filter)
- No `statistics.viewCount` → drop

**Step 4 — Rank:**
```python
score = (1 / search_position) * math.log10(max(view_count, 1))
```
Take top `MAX_VIDEOS` by score.

---

## 7. Transcript Format

`youtube-transcript-api` returns:
```python
[{'text': 'hello world', 'start': 1.5, 'duration': 2.3}, ...]
```

Formatted for Gemini:
```
[00:01] hello world
[00:05] more text here
```

Truncated at `MAX_TRANSCRIPT_MINUTES * 60` seconds. The `[MM:SS]` timestamp in the text is what Gemini uses for attribution.

---

## 8. Timestamp Deep Links

YouTube timestamp URL format:
```
https://youtube.com/watch?v={video_id}&t={seconds}
```

`[02:34]` = 154 seconds in video `dQw4w9WgXcQ`:
```
https://youtube.com/watch?v=dQw4w9WgXcQ&t=154
```

These are rendered as clickable chips in the UI. They open YouTube at exactly the right moment.

---

## 9. Repository Structure

```
chorus/
├── .github/
│   └── workflows/
│       ├── pr-checks.yml        ← lint + test on PR (mirrors Sotto pr-checks.yml)
│       └── deploy-dev.yml       ← sam build + deploy on push to main (mirrors Sotto deploy-dev.yml)
├── src/
│   ├── app.py                   ← FastAPI + Mangum handler
│   ├── config.py                ← env var validation at import time
│   ├── search.py                ← YouTube search + filter + rank + cache
│   ├── transcripts.py           ← parallel fetch + [MM:SS] format
│   └── synthesize.py            ← Gemini call + JSON parse
├── static/
│   └── index.html               ← single-page UI
├── tests/
│   ├── test_search.py
│   ├── test_transcripts.py
│   └── test_synthesize.py
├── .env.example
├── .gitignore                   ← includes local.env.json
├── local.env.json               ← gitignored, used by sam local start-api
├── samconfig.toml               ← SAM deployment config
├── template.yaml                ← SAM: Lambda function + HTTP API Gateway
├── Makefile
├── requirements.txt
├── requirements-dev.txt
├── CLAUDE.md
├── chorus-00-overview.md        ← this file
└── chorus-01-build.md
```
