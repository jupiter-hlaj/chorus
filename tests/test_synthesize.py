import json
from unittest.mock import MagicMock, patch

import pytest

from src import synthesize


def _video(video_id="v1", title="T", channel="C", transcript="[00:00] foo"):
    return {
        "video_id": video_id,
        "title": title,
        "channel": channel,
        "transcript": transcript,
    }


def _full_payload(**overrides):
    base = {
        "verdict": "yes",
        "points": [],
        "consensus": None,
        "conflicts": None,
        "caveats": None,
    }
    base.update(overrides)
    return base


def test_build_prompt_includes_query():
    prompt = synthesize.build_prompt("is X good", [_video()])
    assert 'USER QUESTION: "is X good"' in prompt


def test_build_prompt_includes_all_videos():
    videos = [
        _video("v1", title="T1", channel="C1", transcript="[00:00] foo"),
        _video("v2", title="T2", channel="C2", transcript="[00:01] bar"),
    ]
    prompt = synthesize.build_prompt("query", videos)
    for token in ["T1", "T2", "C1", "C2", "[00:00] foo", "[00:01] bar"]:
        assert token in prompt


def test_build_prompt_handles_missing_transcript():
    videos = [_video(transcript=None)]
    prompt = synthesize.build_prompt("query", videos)
    assert "(no transcript available)" in prompt


def test_parse_response_clean_json():
    out = synthesize._parse_response(json.dumps(_full_payload(verdict="good")))
    assert out["verdict"] == "good"


def test_parse_response_strips_json_fences():
    raw = "```json\n" + json.dumps(_full_payload(verdict="good")) + "\n```"
    assert synthesize._parse_response(raw)["verdict"] == "good"


def test_parse_response_strips_plain_fences():
    raw = "```\n" + json.dumps(_full_payload(verdict="good")) + "\n```"
    assert synthesize._parse_response(raw)["verdict"] == "good"


def test_parse_response_raises_on_missing_keys():
    with pytest.raises(ValueError, match="missing keys"):
        synthesize._parse_response(json.dumps({"verdict": "ok"}))


def test_synthesize_returns_degraded_on_invalid_json():
    fake_response = MagicMock()
    fake_response.text = "not valid json"
    with patch.object(synthesize._client.models, "generate_content", return_value=fake_response):
        out = synthesize.synthesize("q", [_video()])
    assert out["points"] == []
    assert out["consensus"] is None
    assert "Could not parse" in out["verdict"]
    assert set(out.keys()) >= synthesize.REQUIRED_KEYS


def test_synthesize_returns_parsed_response():
    payload = _full_payload(verdict="yes", consensus="all agree")
    fake_response = MagicMock()
    fake_response.text = json.dumps(payload)
    with patch.object(synthesize._client.models, "generate_content", return_value=fake_response):
        out = synthesize.synthesize("q", [_video()])
    assert out["verdict"] == "yes"
    assert out["consensus"] == "all agree"


def test_synthesize_reraises_unexpected_errors():
    with patch.object(synthesize._client.models, "generate_content", side_effect=RuntimeError("api down")):
        with pytest.raises(RuntimeError, match="api down"):
            synthesize.synthesize("q", [_video()])
