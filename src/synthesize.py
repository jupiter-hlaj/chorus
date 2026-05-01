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

Return ONLY valid JSON - no markdown, no preamble, no explanation:
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
        end = next(
            (i for i in range(len(lines) - 1, 0, -1) if lines[i].strip() == "```"),
            len(lines),
        )
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
