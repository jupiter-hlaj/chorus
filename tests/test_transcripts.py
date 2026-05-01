from unittest.mock import patch

import pytest
from youtube_transcript_api import NoTranscriptFound, TranscriptsDisabled

from src import transcripts


def test_format_transcript_basic():
    segments = [
        {"text": "hello world", "start": 1.5, "duration": 2.0},
        {"text": "more text", "start": 5.0, "duration": 2.0},
    ]
    out = transcripts.format_transcript(segments, max_minutes=30)
    assert out == "[00:01] hello world\n[00:05] more text"


def test_format_transcript_truncates():
    segments = [
        {"text": "first", "start": 0.0, "duration": 1.0},
        {"text": "in window", "start": 1700.0, "duration": 1.0},
        {"text": "out of window", "start": 1900.0, "duration": 1.0},
    ]
    out = transcripts.format_transcript(segments, max_minutes=30)
    assert "first" in out
    assert "in window" in out
    assert "out of window" not in out


def test_format_transcript_strips_text():
    segments = [{"text": "  spaced text  ", "start": 0, "duration": 1}]
    out = transcripts.format_transcript(segments, max_minutes=30)
    assert out == "[00:00] spaced text"


def test_format_transcript_minutes_seconds_format():
    segments = [{"text": "x", "start": 125, "duration": 1}]
    out = transcripts.format_transcript(segments, max_minutes=30)
    assert out == "[02:05] x"


def _raise(exc):
    def _side(*args, **kwargs):
        raise exc

    return _side


def test_fetch_transcript_handles_disabled():
    with patch.object(
        transcripts.YouTubeTranscriptApi,
        "get_transcript",
        side_effect=_raise(TranscriptsDisabled("v1")),
    ):
        assert transcripts.fetch_transcript("v1") is None


def test_fetch_transcript_handles_not_found():
    with patch.object(
        transcripts.YouTubeTranscriptApi,
        "get_transcript",
        side_effect=_raise(NoTranscriptFound("v1", ["en"], None)),
    ):
        assert transcripts.fetch_transcript("v1") is None


def test_fetch_transcript_handles_generic_error():
    with patch.object(
        transcripts.YouTubeTranscriptApi,
        "get_transcript",
        side_effect=_raise(RuntimeError("boom")),
    ):
        assert transcripts.fetch_transcript("v1") is None


def test_fetch_transcript_returns_formatted():
    fake_segments = [{"text": "hello", "start": 0, "duration": 1}]
    with patch.object(
        transcripts.YouTubeTranscriptApi,
        "get_transcript",
        return_value=fake_segments,
    ):
        result = transcripts.fetch_transcript("v1")
        assert "[00:00] hello" in result


@pytest.mark.asyncio
async def test_fetch_all_transcripts_returns_dict():
    fake_segments = [{"text": "hi", "start": 0, "duration": 1}]
    with patch.object(
        transcripts.YouTubeTranscriptApi,
        "get_transcript",
        return_value=fake_segments,
    ):
        result = await transcripts.fetch_all_transcripts(["v1", "v2"])
        assert set(result.keys()) == {"v1", "v2"}
        assert all(v is not None for v in result.values())


@pytest.mark.asyncio
async def test_fetch_all_handles_partial_failure():
    def side_effect(video_id, **kwargs):
        if video_id == "fail":
            raise TranscriptsDisabled("fail")
        return [{"text": "hi", "start": 0, "duration": 1}]

    with patch.object(
        transcripts.YouTubeTranscriptApi,
        "get_transcript",
        side_effect=side_effect,
    ):
        result = await transcripts.fetch_all_transcripts(["ok", "fail"])
        assert result["ok"] is not None
        assert result["fail"] is None
