"""
Tests for the replay clock and gradeable-first video selection.
"""

from __future__ import annotations

from datetime import date, timedelta

from hisaab import clock
from hisaab.models import VideoInfo
from hisaab.pipeline.select import MIN_GRADEABLE_AGE_DAYS, select_videos


def test_live_mode_uses_real_date(monkeypatch):
    monkeypatch.setenv("HISAAB_MODE", "live")
    assert clock.today() == date.today()


def test_replay_mode_pins_to_bundle_date(monkeypatch):
    """Without this, the Google Finance window chosen for a tip drifts as real
    time passes and replay starts missing fixtures it used to hit."""
    monkeypatch.setenv("HISAAB_MODE", "replay")
    monkeypatch.setenv("HISAAB_REPLAY_BUNDLE", "demo")
    as_of = clock.bundle_as_of("demo")
    assert as_of is not None, "fixtures/demo/bundle.json must declare as_of"
    assert clock.today() == as_of


def test_replay_mode_without_bundle_metadata_falls_back(monkeypatch):
    monkeypatch.setenv("HISAAB_MODE", "replay")
    monkeypatch.setenv("HISAAB_REPLAY_BUNDLE", "no-such-bundle")
    assert clock.today() == date.today()


def _video(vid: str, age_days: int | None, classification: str = "likely-tip") -> VideoInfo:
    return VideoInfo(
        video_id=vid,
        title=vid,
        channel_id="UC",
        channel_title="c",
        publish_date=None if age_days is None else date.today() - timedelta(days=age_days),
        classification=classification,
    )


def test_selection_prefers_videos_old_enough_to_grade(monkeypatch):
    monkeypatch.setenv("HISAAB_MODE", "live")
    videos = [
        _video("new1", 10),
        _video("old1", MIN_GRADEABLE_AGE_DAYS + 30),
        _video("undated", None),
        _video("new2", 20),
        _video("old2", 400),
    ]
    selected = select_videos(videos, max_videos=3, use_llm=False)
    assert [v.video_id for v in selected][:2] == ["old1", "old2"]


def test_selection_still_fills_budget_with_recent_videos(monkeypatch):
    monkeypatch.setenv("HISAAB_MODE", "live")
    videos = [_video("new1", 5), _video("old1", 200), _video("new2", 6)]
    selected = select_videos(videos, max_videos=3, use_llm=False)
    assert [v.video_id for v in selected] == ["old1", "new1", "new2"]
