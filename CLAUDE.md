# Chorus — YouTube Opinion Aggregator

Ask a question. Get the internet's real opinion — sourced from YouTube, synthesized across multiple videos, with clickable links to the exact timestamp where each point was made.

Working name. Rename when ready.

---

## 0. How To Use This File

Load this file at the start of every session. It is the single source of truth for building Chorus. Detailed specs live in the numbered files — load them when working on a specific step.

**Spec files:**
```
chorus-00-overview.md    ← product vision, architecture, tech decisions
chorus-01-build.md       ← full build: search → transcripts → synthesis → UI → deploy
```

**Run a build step:**
```
/project:step-00   ← repo setup + CI/CD skeleton
/project:step-01   ← config + YouTube search + transcript engine
/project:step-02   ← Gemini synthesis engine
/project:step-03   ← FastAPI app + Mangum + frontend UI
/project:step-04   ← SAM template + deploy
```

**Rules for every session:**
- Build exactly what the step specifies. No extra features.
- Cost awareness at every step — every transcript call costs tokens.
- Follow the Immutable Rules in Section 8. Non-negotiable.
- Never introduce a tool, platform, or service not already in the user's stack without explaining why and offering alternatives first.
- If anything is unclear, ask before building. Do not guess at architecture.

---

## 1. What Chorus Is

Chorus is a lightweight web app deployed as an AWS Lambda function. You type a question or topic — "is the Sony WH-1000XM5 worth buying?" or "what do developers actually think about Remix?" — and Chorus:

1. Searches YouTube for the most relevant videos on that topic
2. Fetches timestamped transcripts from the top results in parallel
3. Sends all transcripts to Gemini with your question in one API call
4. Returns a structured answer: the range of opinions, where they agree, where they conflict
5. Surfaces clickable timestamp links to the exact moments in each video where each point was made

It is not a chatbot. It is not a single-video summarizer. It is an opinion aggregator that uses YouTube as its source and Gemini as its synthesizer.

---

## 2. How It Works

```
User types question
        ↓
YouTube Data API v3 search → top 10 candidates
        ↓
Filter: remove Shorts, non-English, < 3 min, no captions
        ↓
Rank by relevance + view count → take top MAX_VIDEOS (default 5)
        ↓
youtube-transcript-api → parallel fetch, timestamped (thread pool via run_in_executor)
        ↓
Truncate each to MAX_TRANSCRIPT_MINUTES (default 30)
        ↓
One Gemini API call → synthesize across all transcripts
        ↓
Structured JSON: verdict + key points + timestamp deep links
        ↓
Render in browser with clickable youtube.com/watch?v=XXX&t=seconds links
```

**One Gemini call per user query.** All transcripts packed into one prompt. Never call Gemini per video.

---

## 3. User Interface

Single-page web app served from Lambda. No login. No database. No accounts.

- Search bar at top, submit button
- Loading state: "Analyzing N videos…"
- Results:
  - Verdict (highlighted box)
  - Key points (bulleted, each with source chips linking to exact timestamps)
  - Consensus / conflicts section
  - Source list (title, channel, deep links)
- Mobile-friendly, minimal CSS

---

## 4. API (Internal)

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Serve the single-page UI |
| POST | `/search` | Run a query: search → transcripts → synthesize → return JSON |
| GET | `/health` | Health check |

**`POST /search` request:**
```json
{ "query": "is X good", "max_videos": 5 }
```

**`POST /search` response:**
```json
{
  "verdict": "string",
  "points": [
    {
      "claim": "string",
      "sentiment": "positive|negative|neutral|mixed",
      "sources": [
        {
          "video_id": "string",
          "title": "string",
          "channel": "string",
          "timestamp_seconds": 154,
          "timestamp_label": "2:34",
          "quote": "string",
          "url": "https://youtube.com/watch?v=XXX&t=154"
        }
      ]
    }
  ],
  "consensus": "string or null",
  "conflicts": "string or null",
  "caveats": "string or null",
  "videos_analyzed": 5,
  "sources": [{ "video_id", "title", "channel", "view_count", "url" }]
}
```

---

## 5. Data Model

No database. Stateless per Lambda invocation.

In-memory cache: YouTube search results cached by normalized query string for `CACHE_TTL_SECONDS`. **Lambda-specific behavior:** the cache lives in the Lambda container — it persists across warm invocations of the same container but is lost on cold starts and does not share across concurrent containers. Good enough for a personal tool; acceptable behavior documented here.

---

## 6. Environment Variables

API keys are passed as SAM Parameters (`NoEcho: true`) during deployment and injected as Lambda environment variables. They are never committed to the repo.

| Variable | Required | Default | Description |
|---|---|---|---|
| `YOUTUBE_API_KEY` | Yes | — | YouTube Data API v3 key. Set via SAM parameter or `local.env.json`. |
| `GEMINI_API_KEY` | Yes | — | Google Gemini API key. Set via SAM parameter or `local.env.json`. |
| `MAX_VIDEOS` | No | `5` | Max videos to analyze per query |
| `MAX_TRANSCRIPT_MINUTES` | No | `30` | Max minutes of transcript per video |
| `CACHE_TTL_SECONDS` | No | `3600` | In-memory search cache TTL |
| `LOG_LEVEL` | No | `INFO` | Python logging level |
| `ENVIRONMENT` | No | `dev` | Set automatically by SAM |

`PORT` is not used on Lambda. It is only relevant when running `uvicorn` directly for local development outside SAM.

---

## 7. Project Structure

```
chorus/
├── .github/
│   └── workflows/
│       ├── pr-checks.yml        ← ruff + bandit + pytest on every PR (mirrors Sotto)
│       └── deploy-dev.yml       ← sam build + sam deploy on push to main (mirrors Sotto)
├── src/
│   ├── app.py                   ← FastAPI app + Mangum handler for Lambda
│   ├── config.py                ← env var validation at import time
│   ├── search.py                ← YouTube Data API: search + filter + rank + cache
│   ├── transcripts.py           ← parallel transcript fetch + timestamp formatting
│   └── synthesize.py            ← Gemini API: one call, structured JSON output
├── static/
│   └── index.html               ← single-page UI (vanilla HTML/CSS/JS)
├── tests/
│   ├── test_search.py
│   ├── test_transcripts.py
│   └── test_synthesize.py
├── .env.example                 ← template for local.env.json values
├── .gitignore
├── local.env.json               ← gitignored, used by sam local start-api
├── samconfig.toml               ← SAM deployment config (mirrors Sotto)
├── template.yaml                ← SAM template: Lambda + HTTP API Gateway
├── Makefile                     ← build, test, lint, local, deploy-dev (mirrors Sotto)
├── requirements.txt
├── requirements-dev.txt
├── CLAUDE.md                    ← this file
├── chorus-00-overview.md
└── chorus-01-build.md
```

No Dockerfile. No container registry. SAM packages and deploys the function directly.

---

## 8. Immutable Rules

### Cost Rules — Non-Negotiable

1. **Cap transcripts at `MAX_TRANSCRIPT_MINUTES`.** Every transcript is truncated to the cap before synthesis. Never send an unbounded transcript to Gemini.

2. **Cap videos at `MAX_VIDEOS`.** Default 5. Never analyze more than the configured max per query.

3. **One Gemini call per user query.** Pack all transcripts into one prompt. Never call Gemini once per video.

4. **Cache YouTube search results.** YouTube Data API quota: 10,000 units/day free. Search = 100 units. Cache by normalized query string.

### Lambda Rules

5. **API Gateway HTTP API timeout is 29 seconds.** The Lambda function timeout is set to 60 seconds for direct invocation, but API Gateway cuts the connection at 29 seconds. Keep the pipeline fast: parallel transcript fetches, one Gemini call. If the pipeline exceeds 29 seconds consistently, reduce MAX_VIDEOS or MAX_TRANSCRIPT_MINUTES.

6. **Mangum handles the ASGI ↔ Lambda bridge.** `handler = Mangum(app, lifespan="off")`. The Lambda handler entry point is `src.app.handler`. Never use `lifespan="on"` — Lambda does not support ASGI lifespan events.

7. **Static files served from the Lambda package.** `static/index.html` is included in the SAM build. Read it relative to `__file__` so the path resolves correctly on Lambda (`/var/task/`) and locally.

### Code Rules

8. **Config validated at import time.** Missing `YOUTUBE_API_KEY` or `GEMINI_API_KEY` raises `ValueError` before the app accepts any requests.

9. **Timestamps preserved through the pipeline.** Transcripts formatted as `[MM:SS] text` before Gemini. Attribution is only possible if timestamps are in the text.

10. **Gemini returns structured JSON.** Parse and validate. If parse fails, return a degraded response — never a 500.

11. **Transcript fetch failures are non-fatal.** If one video has no transcript, skip it and continue. Never crash the query because of one missing transcript.

12. **Fetch transcripts in parallel.** `asyncio.gather` over `loop.run_in_executor` calls. Never sequential.

13. **`ruff` and `bandit` must pass clean.** Same standard as Sotto.

14. **`pytest` for all tests.** No other test framework.

15. **Python 3.13, arm64 (Graviton2).** Match Sotto's runtime.

16. **Never introduce a tool, platform, or service not in the user's existing stack** (AWS, GitHub Actions, Python, SAM) without explaining why and offering alternatives first.

---

## 9. Resolved Design Decisions

**Why YouTube and not Reddit/blogs:**
YouTube reviews are longer, more hands-on, harder to fake. For "is X good" queries, YouTube is the highest-signal source available without scraping paywalled sites.

**Why multiple videos and not one:**
One review is one opinion. Five reveal where consensus holds and where it breaks. The disagreements are often the most useful signal.

**Why timestamps:**
Trust. Anyone can summarize. Showing the exact moment where a claim was made lets the user verify rather than just trust.

**Why Python 3.13:**
`youtube-transcript-api` is the best transcript library in any language. First-party YouTube Data API Python client. Matches Sotto's runtime — same toolchain throughout.

**Why FastAPI:**
Async-first. `asyncio.gather` for parallel transcript fetches is idiomatic and clean. Mangum bridges FastAPI (ASGI) to Lambda events cleanly.

**Why AWS Lambda + SAM:**
User already uses AWS SAM for Sotto. Same toolchain, same account, same CI/CD pattern. Free tier covers a personal tool: 1 million requests/month, 400,000 GB-seconds compute free. No new accounts, no new tools.

**Why no database:**
Nothing to persist. Users have no accounts. Queries don't need to be stored. In-memory cache is sufficient for quota protection.

**Why API keys via SAM Parameters → Lambda env vars:**
Simplest secure option for a personal tool. Keys come from GitHub Secrets, get passed as SAM `NoEcho` parameters during deploy, land as Lambda environment variables. Never committed to the repo. For a multi-tenant production service, move to Secrets Manager (like Sotto does).

---

## 10. Common Pitfalls

1. **YouTube quota.** 10,000 units/day free. Search = 100 units, videos.list ≈ 10 units per query. Cache search results. Don't re-search the same query within the cache TTL.

2. **29-second API Gateway timeout.** The hard limit. Gemini synthesis on large inputs can approach this. Keep MAX_VIDEOS at 5 and MAX_TRANSCRIPT_MINUTES at 30.

3. **No transcript available.** Some videos disable captions. Handle gracefully — skip and log, never crash.

4. **Auto-captions are noisy.** No punctuation, occasional errors. Instruct Gemini to use context to interpret.

5. **Lambda in-memory cache is per-container.** Multiple warm containers do not share cache. Cold starts lose the cache. This is acceptable for a personal tool.

6. **SAM build packages dependencies.** Run `sam build` before `sam deploy` every time. CI does this. Locally, run `make build` before `make deploy-dev`.

7. **Gemini JSON parse failures.** Gemini occasionally wraps JSON in markdown code fences. Strip them before parsing. Retry once. Fall back to degraded response.

8. **Transcript timestamps must survive pipeline.** Verify the `[MM:SS]` format is in the text before the Gemini call. If Gemini can't see timestamps, it can't cite them.

---

## 11. Build Progress

- [ ] **Step 0** — Repo setup + CI/CD skeleton (`/project:step-00`)
- [ ] **Step 1** — Config + YouTube search + transcript engine (`/project:step-01`)
- [ ] **Step 2** — Gemini synthesis engine (`/project:step-02`)
- [ ] **Step 3** — FastAPI app + Mangum + frontend UI (`/project:step-03`)
- [ ] **Step 4** — SAM template + deploy (`/project:step-04`)
