import time
from unittest.mock import MagicMock

import pytest

from src import search


@pytest.fixture(autouse=True)
def reset_state():
    search._cache.clear()
    yield
    search._cache.clear()


def _search_item(video_id, title="A video", channel="A channel"):
    return {
        "id": {"videoId": video_id},
        "snippet": {"title": title, "channelTitle": channel},
    }


def _meta_item(video_id, duration="PT5M", caption="true", view_count="1000"):
    return {
        "id": video_id,
        "contentDetails": {"duration": duration, "caption": caption},
        "statistics": {"viewCount": view_count},
    }


def _mock_yt(search_items, meta_items):
    yt = MagicMock()
    yt.search.return_value.list.return_value.execute.return_value = {"items": search_items}
    yt.videos.return_value.list.return_value.execute.return_value = {"items": meta_items}
    return yt


def test_short_video_filtered_out(monkeypatch):
    yt = _mock_yt(
        [_search_item("v1")],
        [_meta_item("v1", duration="PT2M")],
    )
    monkeypatch.setattr(search, "_yt", yt)
    assert search.get_top_videos("test", 5) == []


def test_caption_false_filtered_out(monkeypatch):
    yt = _mock_yt(
        [_search_item("v1")],
        [_meta_item("v1", caption="false")],
    )
    monkeypatch.setattr(search, "_yt", yt)
    assert search.get_top_videos("test", 5) == []


def test_no_view_count_filtered_out(monkeypatch):
    yt = _mock_yt(
        [_search_item("v1")],
        [_meta_item("v1", view_count="0")],
    )
    monkeypatch.setattr(search, "_yt", yt)
    assert search.get_top_videos("test", 5) == []


def test_ranking_higher_view_count_wins(monkeypatch):
    yt = _mock_yt(
        [_search_item("v1"), _search_item("v2")],
        [
            _meta_item("v1", view_count="100"),
            _meta_item("v2", view_count="100000"),
        ],
    )
    monkeypatch.setattr(search, "_yt", yt)
    results = search.get_top_videos("test", 5)
    assert len(results) == 2
    assert results[0]["video_id"] == "v2"


def test_cache_hit_returns_cached(monkeypatch):
    yt = _mock_yt([_search_item("v1")], [_meta_item("v1")])
    monkeypatch.setattr(search, "_yt", yt)

    results1 = search.get_top_videos("test query", 5)
    assert yt.search.call_count == 1

    results2 = search.get_top_videos("test query", 5)
    assert yt.search.call_count == 1
    assert results1 == results2


def test_cache_normalizes_query(monkeypatch):
    yt = _mock_yt([_search_item("v1")], [_meta_item("v1")])
    monkeypatch.setattr(search, "_yt", yt)

    search.get_top_videos("Test Query  ", 5)
    search.get_top_videos("test query", 5)
    assert yt.search.call_count == 1


def test_cache_expires_after_ttl(monkeypatch):
    yt = _mock_yt([_search_item("v1")], [_meta_item("v1")])
    monkeypatch.setattr(search, "_yt", yt)

    search.get_top_videos("test", 5)
    cached_results, _ = search._cache["test"]
    search._cache["test"] = (cached_results, time.time() - 99999)
    search.get_top_videos("test", 5)
    assert yt.search.call_count == 2


def test_empty_search_results(monkeypatch):
    yt = _mock_yt([], [])
    monkeypatch.setattr(search, "_yt", yt)
    assert search.get_top_videos("test", 5) == []


def test_parse_duration_seconds():
    assert search._parse_duration_seconds("PT3M30S") == 210
    assert search._parse_duration_seconds("PT1H") == 3600
    assert search._parse_duration_seconds("PT45S") == 45
    assert search._parse_duration_seconds("PT1H30M15S") == 5415
    assert search._parse_duration_seconds("garbage") == 0
