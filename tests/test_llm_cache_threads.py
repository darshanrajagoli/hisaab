"""
Regression tests for failures that made audits silently report 0 tips.
"""

from __future__ import annotations

import threading

import pytest

from hisaab import llm
from hisaab.models import TranscriptWindow
from hisaab.pipeline import extract


def test_llm_cache_readable_from_another_thread(tmp_path, monkeypatch):
    """Streamlit runs each session on its own thread. A cache connection
    opened by the first session must not break lookups in the next one."""
    monkeypatch.setenv("HISAAB_LLM_CACHE_DB", str(tmp_path / "cache.db"))
    llm._llm_cache_put("k", "cached response")

    seen: list[object] = []

    def lookup():
        try:
            seen.append(llm._llm_cache_get("k"))
        except Exception as e:  # surfaced via the assert below
            seen.append(e)

    t = threading.Thread(target=lookup)
    t.start()
    t.join()
    assert seen == ["cached response"]


def _window(i: int) -> TranscriptWindow:
    return TranscriptWindow(
        video_id="v", window_index=i, start_ms=i * 1000, end_ms=i * 1000 + 900,
        text="target stop loss buy", has_tip_keywords=True,
    )


def test_every_extraction_call_failing_is_loud_not_zero_tips(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("429 RESOURCE_EXHAUSTED")

    monkeypatch.setattr(extract, "call_llm_json", boom)
    with pytest.raises(RuntimeError, match="All 2 tip-extraction LLM calls failed"):
        extract.extract_tips_from_windows([_window(0), _window(1)])


def test_one_failed_window_does_not_sink_the_run(monkeypatch):
    calls = {"n": 0}

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("Server disconnected")
        return []

    monkeypatch.setattr(extract, "call_llm_json", flaky)
    assert extract.extract_tips_from_windows([_window(0), _window(1)]) == []
