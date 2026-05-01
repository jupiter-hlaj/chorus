# Chorus — Build Steps

---

## Step 0: Repo Setup + CI/CD Skeleton

### 0.1 Create the Repository

```bash
cd ~/Desktop/chorus
git init
gh repo create jupiter-hlaj/chorus --public --description "YouTube opinion aggregator — search, synthesize, cite"
git remote add origin https://github.com/jupiter-hlaj/chorus.git
```

### 0.2 `.gitignore`

```
__pycache__/
*.pyc
*.pyo
.env
.venv/
venv/
*.egg-info/
dist/
build/
.pytest_cache/
.ruff_cache/
htmlcov/
.coverage
local.env.json
.aws-sam/
```

### 0.3 `.env.example`

Values needed for `local.env.json` — never commit the actual keys.

```
YOUTUBE_API_KEY=
GEMINI_API_KEY=
MAX_VIDEOS=5
MAX_TRANSCRIPT_MINUTES=30
CACHE_TTL_SECONDS=3600
LOG_LEVEL=DEBUG
ENVIRONMENT=dev
```

### 0.4 `local.env.json`

Used by `sam local start-api`. Gitignored. Create this manually — never commit it.

```json
{
  "ChorusFunction": {
    "YOUTUBE_API_KEY": "your_youtube_api_key_here",
    "GEMINI_API_KEY": "your_gemini_api_key_here",
    "MAX_VIDEOS": "5",
    "MAX_TRANSCRIPT_MINUTES": "30",
    "CACHE_TTL_SECONDS": "3600",
    "LOG_LEVEL": "DEBUG",
    "ENVIRONMENT": "dev"
  }
}
```

### 0.5 `requirements.txt`

```
fastapi>=0.115
mangum>=0.17
uvicorn[standard]>=0.30
google-genai>=1.0
google-api-python-client>=2.150
youtube-transcript-api>=0.6
pydantic>=2.0
python-dotenv>=1.0
```

### 0.6 `requirements-dev.txt`

```
pytest>=8.0
pytest-asyncio>=0.24
pytest-cov
ruff
bandit
httpx
respx
moto[core]
```

### 0.7 `Makefile` (mirrors Sotto)

```makefile
.PHONY: build test lint local-dev local-lambda deploy-dev

build:
	sam build --template template.yaml --use-container

test:
	pytest tests/ -v --tb=short

lint:
	ruff check src/ && ruff format --check src/ && bandit -r src/ -ll

local-dev:
	uvicorn src.app:app --reload --port 8000

local-lambda:
	sam local start-api --template template.yaml --env-vars local.env.json

deploy-dev:
	sam deploy --config-env dev
```

`local-dev` uses uvicorn directly — fast reload, best for active development.
`local-lambda` uses SAM local — tests the Lambda integration, slower but accurate.

### 0.8 GitHub Actions: `pr-checks.yml` (mirrors Sotto)

File: `.github/workflows/pr-checks.yml`

```yaml
name: PR Checks

on:
  pull_request:
    branches: [main]

env:
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: 'true'

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.13' }
      - run: pip install ruff bandit
      - run: ruff check src/
      - run: ruff format --check src/
      - run: bandit -r src/ -ll

  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.13' }
      - run: pip install -r requirements.txt -r requirements-dev.txt
      - run: pytest tests/ -v --tb=short --cov=src --cov-report=xml
      - uses: codecov/codecov-action@v4
```

### 0.9 GitHub Actions: `deploy-dev.yml` (mirrors Sotto)

File: `.github/workflows/deploy-dev.yml`

```yaml
name: Deploy to Dev

on:
  push:
    branches: [main]

permissions:
  id-token: write
  contents: read

concurrency:
  group: deploy-dev
  cancel-in-progress: false

env:
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: 'true'

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: dev
    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials (OIDC)
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.DEV_OIDC_ROLE_ARN }}
          aws-region: ca-central-1

      - uses: aws-actions/setup-sam@v2
      - uses: actions/setup-python@v5
        with: { python-version: '3.13' }

      - name: SAM Build
        run: sam build --no-cached --template template.yaml

      - name: SAM Deploy (dev)
        run: |
          sam deploy \
            --config-env dev \
            --parameter-overrides \
              YoutubeApiKey=${{ secrets.YOUTUBE_API_KEY }} \
              GeminiApiKey=${{ secrets.GEMINI_API_KEY }} \
            --no-confirm-changeset \
            --no-fail-on-empty-changeset

      - name: Smoke test
        run: |
          API_URL=$(aws cloudformation describe-stacks \
            --stack-name chorus-dev \
            --query "Stacks[0].Outputs[?OutputKey=='ChorusApiUrl'].OutputValue" \
            --output text \
            --region ca-central-1)
          curl -f "$API_URL/health" || exit 1
```

**GitHub Secrets required:**
- `DEV_OIDC_ROLE_ARN` — OIDC role scoped to Chorus (create new, do not reuse other projects)
- `YOUTUBE_API_KEY` — YouTube Data API v3 key
- `GEMINI_API_KEY` — Google Gemini API key

### 0.10 `samconfig.toml` (mirrors Sotto)

Replace `{ACCOUNT_ID}` with your AWS account ID.

```toml
# Chorus SAM deployment configuration
# Bootstrap (first deploy only):
#   1. aws s3 mb s3://chorus-sam-{ACCOUNT_ID}-dev --region ca-central-1
#   2. Replace {ACCOUNT_ID} in s3_bucket below.
#   3. sam deploy --config-env dev --guided (first time only)

version = 0.1

[default.global.parameters]
region = "ca-central-1"

[default.build.parameters]
cached = true
parallel = true

[default.validate.parameters]
lint = true

[dev.global.parameters]
stack_name = "chorus-dev"
region = "ca-central-1"

[dev.build.parameters]
cached = true
parallel = true

[dev.deploy.parameters]
stack_name              = "chorus-dev"
region                  = "ca-central-1"
s3_bucket               = "chorus-sam-{ACCOUNT_ID}-dev"
s3_prefix               = "chorus-dev"
capabilities            = "CAPABILITY_IAM CAPABILITY_NAMED_IAM CAPABILITY_AUTO_EXPAND"
confirm_changeset       = false
fail_on_empty_changeset = false
parameter_overrides     = [
  "Environment=dev",
  "LogLevel=DEBUG"
]
```

**Note:** `YoutubeApiKey` and `GeminiApiKey` are not in `samconfig.toml` because they are secrets — they come from GitHub Secrets in CI and are passed on the command line locally. Never put secret values in `samconfig.toml`.

### 0.11 Initial commit

```bash
git add .
git commit -m "chore: project scaffold and spec docs"
git push -u origin main
```

---

## Step 1: Config + YouTube Search + Transcript Engine

### 1.1 `src/config.py`

Validates all environment variables at import time. Fails before the app accepts any requests.

```python
import os
from dataclasses import dataclass

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
```

### 1.2 `src/search.py`

YouTube Data API v3 search + filter + rank + in-memory cache.

```python
import math
import re
import time
import logging
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
    m = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', iso)
    if not m:
        return 0
    return int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + int(m.group(3) or 0)

def _rank_score(position: int, view_count: int) -> float:
    return (1 / (position + 1)) * math.log10(max(view_count, 1))

def get_top_videos(query: str, n: int) -> list[dict]:
    cached = _get_cached(query)
    if cached is not None:
        return cached[:n]

    # Search — 100 units
    search_resp = _yt.search().list(
        q=query,
        type="video",
        videoCaption="closedCaption",
        relevanceLanguage="en",
        maxResults=10,
        part="id,snippet",
    ).execute()

    items = search_resp.get("items", [])
    if not items:
        return []

    video_ids = [item["id"]["videoId"] for item in items]

    # Metadata — ~10 units
    meta_resp = _yt.videos().list(
        id=",".join(video_ids),
        part="contentDetails,statistics",
    ).execute()

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

        results.append({
            "video_id": vid_id,
            "title": item["snippet"]["title"],
            "channel": item["snippet"]["channelTitle"],
            "duration_seconds": duration,
            "view_count": view_count,
            "score": _rank_score(position, view_count),
        })

    results.sort(key=lambda r: r["score"], reverse=True)
    _set_cached(query, results)
    logger.info("Search for %r returned %d usable videos", query, len(results))
    return results[:n]
```

### 1.3 `src/transcripts.py`

Parallel transcript fetch + `[MM:SS]` timestamp formatting.

```python
import asyncio
import logging
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
from src.config import config

logger = logging.getLogger(__name__)

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
        segments = YouTubeTranscriptApi.get_transcript(
            video_id, languages=["en", "en-US", "en-GB"]
        )
        return format_transcript(segments, config.max_transcript_minutes)
    except (TranscriptsDisabled, NoTranscriptFound):
        logger.info("No transcript for video %s — skipping", video_id)
        return None
    except Exception as e:
        logger.warning("Transcript fetch failed for %s: %s", video_id, e)
        return None

async def fetch_all_transcripts(video_ids: list[str]) -> dict[str, str | None]:
    loop = asyncio.get_event_loop()
    tasks = [loop.run_in_executor(None, fetch_transcript, vid) for vid in video_ids]
    results = await asyncio.gather(*tasks)
    return dict(zip(video_ids, results))
```

`YouTubeTranscriptApi` is synchronous. `run_in_executor` runs it in a thread pool so the async event loop is never blocked.

### 1.4 Tests: `tests/test_search.py`

Mock `_yt` (the googleapiclient build). Test:
- Short video (< 180s) is filtered out
- Video with `caption="false"` is filtered out
- Video with no view count is filtered out
- Ranking produces correct order (higher view count at same search position wins)
- Cache hit returns cached results without calling YouTube API
- Cache miss calls the API and stores results

### 1.5 Tests: `tests/test_transcripts.py`

Mock `YouTubeTranscriptApi.get_transcript`. Test:
- `format_transcript` produces correct `[MM:SS]` format
- Truncation stops at `max_minutes` boundary
- `TranscriptsDisabled` handled gracefully → returns None
- `NoTranscriptFound` handled gracefully → returns None
- `fetch_all_transcripts` returns dict keyed by video ID
- One failed transcript does not prevent others from returning

---

## Step 2: Gemini Synthesis Engine

### 2.1 `src/synthesize.py`

```python
import json
import logging
from google import genai
from src.config import config

logger = logging.getLogger(__name__)
_client = genai.Client(api_key=config.gemini_api_key)

REQUIRED_KEYS = {"verdict", "points", "consensus", "conflicts", "caveats"}
_GENERATION_CONFIG = {"response_mime_type": "application/json"}

def build_prompt(query: str, videos: list[dict]) -> str:
    sections = []
    for i, video in enumerate(videos, 1):
        transcript = video.get("transcript") or "(no transcript available)"
        sections.append(
            f"---\n"
            f"Video {i}: {video['title']}\n"
            f"Channel: {video['channel']}\n"
            f"URL: https://youtube.com/watch?v={video['video_id']}\n\n"
            f"{transcript}\n"
            f"---"
        )

    return f"""You are analyzing {len(videos)} YouTube video transcripts to answer the user's question.

USER QUESTION: "{query}"

TRANSCRIPTS:

{chr(10).join(sections)}

INSTRUCTIONS:
1. Read all transcripts carefully.
2. Identify the key claims, opinions, and observations relevant to the user's question.
3. Note where reviewers agree and where they genuinely conflict.
4. For each key point, cite the specific timestamp(s) from the transcript(s) where it was made.
5. Only cite timestamps that actually appear in the transcripts. Do not invent timestamps.
6. Transcripts may contain auto-caption errors (no punctuation, misspelled words). Use context to interpret them.

Return ONLY valid JSON — no markdown, no preamble, no explanation:
{{
  "verdict": "One or two sentences directly answering the user's question based on what the videos collectively say.",
  "points": [
    {{
      "claim": "Specific claim or opinion found in the videos",
      "sentiment": "positive|negative|neutral|mixed",
      "sources": [
        {{
          "video_id": "the video ID",
          "title": "the video title",
          "channel": "the channel name",
          "timestamp_seconds": 154,
          "timestamp_label": "2:34",
          "quote": "Brief verbatim or near-verbatim quote from the transcript"
        }}
      ]
    }}
  ],
  "consensus": "What most reviewers agree on, or null if no clear consensus",
  "conflicts": "Where reviewers meaningfully disagree, or null if no significant conflicts",
  "caveats": "Important conditions or limitations mentioned, or null"
}}"""

def _parse_response(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        end = next((i for i in range(len(lines) - 1, 0, -1) if lines[i].strip() == "```"), len(lines))
        text = "\n".join(lines[1:end])
    data = json.loads(text)
    missing = REQUIRED_KEYS - set(data.keys())
    if missing:
        raise ValueError(f"Gemini response missing keys: {missing}")
    return data

def synthesize(query: str, videos: list[dict]) -> dict:
    prompt = build_prompt(query, videos)
    try:
        response = _client.models.generate_content(
            model=config.model,
            contents=prompt,
            config=_GENERATION_CONFIG,
        )
        return _parse_response(response.text)
    except json.JSONDecodeError as e:
        logger.warning("Gemini returned unparseable JSON: %s", e)
        return {
            "verdict": "Could not parse response. Try again or rephrase your question.",
            "points": [],
            "consensus": None,
            "conflicts": None,
            "caveats": None,
        }
    except Exception:
        logger.exception("Synthesis call failed")
        raise
```

### 2.2 Tests: `tests/test_synthesize.py`

Mock `google.genai.Client`. Test:
- `build_prompt` includes all video titles and transcripts
- `build_prompt` includes the user's query verbatim
- `_parse_response` handles clean JSON
- `_parse_response` strips markdown code fences (` ```json ... ``` `)
- `_parse_response` raises `ValueError` on missing required keys
- `synthesize` returns degraded dict on `JSONDecodeError` — not a 500
- Degraded response includes all required keys with null/empty values

---

## Step 3: FastAPI App + Mangum + Frontend UI

### 3.1 `src/app.py`

```python
import logging
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from mangum import Mangum
from pydantic import BaseModel
from src.config import config
from src.search import get_top_videos
from src.transcripts import fetch_all_transcripts
from src.synthesize import synthesize

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
                f"https://youtube.com/watch?v={source.get('video_id', '')}"
                f"&t={source.get('timestamp_seconds', 0)}"
            )

    return result

# Lambda handler — entry point is src.app.handler in template.yaml
handler = Mangum(app, lifespan="off")
```

`STATIC_DIR` is resolved relative to `__file__` so it works on Lambda (`/var/task/`) and locally.

### 3.2 `static/index.html`

Single-page app. Vanilla HTML, CSS, JS. No frameworks, no build step.

**Structure:**
- Header: app name + tagline
- Search bar + submit button
- Status div: "Analyzing N videos…" during loading
- Error div: shown on API errors
- Results section (hidden until populated):
  - Verdict: highlighted box, `<p>` text
  - Points: `<ul>` with sentiment badge + source chips (each chip = `<a>` timestamp link)
  - Consensus / conflicts: `<p>` text, hidden if null
  - Sources: list of video links at the bottom

**Source chip format:**
```html
<a href="https://youtube.com/watch?v=XXX&t=154"
   target="_blank"
   rel="noopener noreferrer"
   class="chip">
  ChannelName @ 2:34
</a>
```

**JavaScript — key behavior:**
```javascript
document.getElementById('search-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const query = document.getElementById('query').value.trim();
  if (!query) return;

  setStatus(`Searching YouTube and analyzing videos…`);
  clearResults();

  try {
    const res = await fetch('/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, max_videos: 5 }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
      setError(err.detail || 'Something went wrong. Try again.');
      return;
    }
    const data = await res.json();
    setStatus(`Analyzed ${data.videos_analyzed} videos`);
    renderResults(data);
  } catch (err) {
    setError('Request failed. Check your connection.');
  }
});
```

---

## Step 4: SAM Template + Deploy

### 4.1 `template.yaml`

```yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31
Description: Chorus — YouTube Opinion Aggregator

Parameters:
  Environment:
    Type: String
    AllowedValues: [dev, prod]
    Default: dev
  LogLevel:
    Type: String
    Default: INFO
    AllowedValues: [DEBUG, INFO, WARNING, ERROR]
  YoutubeApiKey:
    Type: String
    NoEcho: true
    Description: YouTube Data API v3 key
  GeminiApiKey:
    Type: String
    NoEcho: true
    Description: Google Gemini API key

Globals:
  Function:
    Runtime: python3.13
    Architectures: [arm64]
    MemorySize: 512
    Timeout: 60
    Environment:
      Variables:
        ENVIRONMENT: !Ref Environment
        LOG_LEVEL: !Ref LogLevel
        YOUTUBE_API_KEY: !Ref YoutubeApiKey
        GEMINI_API_KEY: !Ref GeminiApiKey
        MAX_VIDEOS: "5"
        MAX_TRANSCRIPT_MINUTES: "30"
        CACHE_TTL_SECONDS: "3600"

Resources:
  ChorusApi:
    Type: AWS::Serverless::HttpApi
    Properties:
      StageName: !Ref Environment
      CorsConfiguration:
        AllowOrigins:
          - '*'
        AllowMethods:
          - GET
          - POST
          - OPTIONS
        AllowHeaders:
          - Content-Type

  ChorusFunction:
    Type: AWS::Serverless::Function
    Properties:
      Handler: src.app.handler
      CodeUri: .
      Description: Chorus main app — search, transcribe, synthesize
      Events:
        Root:
          Type: HttpApi
          Properties:
            ApiId: !Ref ChorusApi
            Path: /
            Method: GET
        Health:
          Type: HttpApi
          Properties:
            ApiId: !Ref ChorusApi
            Path: /health
            Method: GET
        Search:
          Type: HttpApi
          Properties:
            ApiId: !Ref ChorusApi
            Path: /search
            Method: POST

Outputs:
  ChorusApiUrl:
    Description: Chorus API URL
    Value: !Sub "https://${ChorusApi}.execute-api.${AWS::Region}.amazonaws.com/${Environment}"
```

**Notes:**
- `MemorySize: 512` — more memory = faster CPU on Lambda. Transcript fetching and JSON parsing benefit.
- `Timeout: 60` — Lambda timeout. API Gateway HTTP API cuts at 29 seconds regardless. Lambda timeout set higher to allow for direct invocations and future async patterns.
- `arm64` — Graviton2. Same as Sotto. Better price/performance.
- `YoutubeApiKey` and `GeminiApiKey` are `NoEcho: true` — they won't appear in CloudFormation console output.

### 4.2 Bootstrap (first deploy only)

```bash
# 1. Create the SAM artifact bucket (replace {ACCOUNT_ID})
aws s3 mb s3://chorus-sam-{ACCOUNT_ID}-dev --region ca-central-1

# 2. Update samconfig.toml: replace {ACCOUNT_ID} with your account ID

# 3. First guided deploy
sam build --template template.yaml
sam deploy \
  --config-env dev \
  --guided \
  --parameter-overrides \
    YoutubeApiKey=your_key \
    GeminiApiKey=your_key

# 4. Subsequent local deploys
make build && make deploy-dev
```

### 4.3 Add GitHub Secrets

In GitHub repo → Settings → Secrets → Actions:

| Secret | Value |
|---|---|
| `DEV_OIDC_ROLE_ARN` | New OIDC role scoped to chorus-* (create fresh, separate from other projects) |
| `YOUTUBE_API_KEY` | Your YouTube Data API v3 key |
| `GEMINI_API_KEY` | Your Google Gemini API key |

After this: every push to `main` auto-deploys via GitHub Actions.

### 4.4 OIDC Role Permissions

Create a new OIDC role scoped to `chorus-*` resources only. Do not reuse roles from other projects.

The role needs: `cloudformation:*`, `lambda:*`, `apigateway:*`, `iam:PassRole`, `s3:*` on the SAM bucket, scoped to `chorus-*` resource ARNs.

---

## What To Get Before Starting

| Item | Where | Free? |
|---|---|---|
| YouTube Data API v3 key | console.cloud.google.com → New project → Enable API → Credentials → API Key | Yes |
| Gemini API key | aistudio.google.com → Get API key (same Google account) | Yes (free tier) |
| SAM S3 bucket | `aws s3 mb s3://chorus-sam-{ACCOUNT_ID}-dev --region ca-central-1` | Free (< 5GB) |
| OIDC role | Create new scoped to chorus-* | Free |
