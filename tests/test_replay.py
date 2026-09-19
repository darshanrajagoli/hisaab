"""
Tests for replay mode — the "judges can run this with zero API keys" claim.

These assert against the actual shipped fixtures/demo/ bundle, not mocks,
so a broken or incomplete bundle fails CI instead of shipping silently.
"""

from __future__ import annotations

import pytest

from hisaab.llm import ReplayFixtureMissing, call_llm
from hisaab.serp.fixtures import DEFAULT_FIXTURES_DIR, FixtureStore


def test_fixture_bundle_is_not_empty():
    store = FixtureStore()
    assert store._index, (
        "fixtures/demo/ has no entries — replay mode has nothing to serve. "
        "Run scripts/export_fixtures.py after a live audit to populate it."
    )


def test_fixture_bundle_files_exist_on_disk():
    store = FixtureStore()
    missing = [key for key, path in store._index.items() if not path.exists()]
    assert not missing, f"index.json references {len(missing)} missing fixture file(s)"


def test_fixture_bundle_covers_multiple_engines():
    """A bundle that's all one engine (e.g. only youtube_video) can't drive a full audit."""
    import json

    engines_seen = set()
    for path in DEFAULT_FIXTURES_DIR.glob("*.json"):
        if path.name == "index.json":
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        engine = data.get("search_metadata", {}).get("engine") or data.get(
            "search_parameters", {}
        ).get("engine")
        if engine:
            engines_seen.add(engine)

    assert len(engines_seen) >= 2, f"Only found engine(s): {engines_seen}"


def test_replay_mode_llm_call_fails_loud_not_silent(monkeypatch):
    """
    A prompt with no cached LLM response in replay mode must raise
    ReplayFixtureMissing, not fall through to a live call or return empty.
    """
    monkeypatch.setenv("HISAAB_MODE", "replay")
    import uuid

    unique_prompt = f"this prompt was never cached: {uuid.uuid4()}"
    with pytest.raises(ReplayFixtureMissing):
        call_llm(unique_prompt, max_tokens=8)


def test_llm_cache_bundle_is_not_empty():
    """fixtures/demo/llm_cache.db must exist and have rows, or replay-mode
    extraction/verification/resolution has nothing to serve."""
    import sqlite3

    db_path = DEFAULT_FIXTURES_DIR / "llm_cache.db"
    assert db_path.exists(), (
        f"{db_path} is missing — replay mode has no cached Gemini responses. "
        "Run a live audit then scripts/export_fixtures.py to populate it."
    )
    conn = sqlite3.connect(str(db_path))
    try:
        count = conn.execute("SELECT COUNT(*) FROM llm_cache").fetchone()[0]
    finally:
        conn.close()
    assert count > 0, f"{db_path} exists but has zero cached rows."


def test_full_audit_replay_produces_tips(monkeypatch, tmp_path, caplog):
    """The real end-to-end guarantee: a full audit against the shipped demo
    bundle, with zero API keys and zero live network calls, must actually
    extract and verify tips — not just fail to crash. A broken or
    incomplete LLM cache previously produced a clean-looking but empty
    scorecard instead of a loud error; assert real pipeline output instead.

    Deliberately does NOT override HISAAB_LLM_CACHE_DB — that would bypass
    fixtures/demo/llm_cache.db entirely (see hisaab.llm._llm_cache_path)
    and defeat the point of this test, which is to prove the *shipped*
    bundle is what a judge running with zero keys actually gets served.
    """
    import logging

    caplog.set_level(logging.INFO)

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("SERPAPI_API_KEY", raising=False)
    monkeypatch.delenv("HISAAB_LLM_CACHE_DB", raising=False)
    monkeypatch.setenv("HISAAB_MODE", "replay")

    from hisaab.pipeline.orchestrator import run_audit
    from hisaab.serp.cache import SerpCache
    from hisaab.serp.client import SerpClient

    # Isolate the SerpApi budget-tracking DB from the developer's real
    # local hisaab_cache.db — replay mode itself reads fixtures, not this,
    # but BudgetGovernor restores its monthly count from it on init.
    client = SerpClient(mode="replay", cache=SerpCache(tmp_path / "cache.db"))
    # max_videos intentionally omitted (default=10) — this must match the
    # exact `hisaab audit @RakeshBansal --replay demo` command in the
    # README's quickstart, since that's the claim under test.
    run = run_audit(
        user_input="@RakeshBansal",
        client=client,
        store=None,
    )

    assert run.funnel.tips_extracted > 0, "Replay produced zero extracted tips"
    assert run.funnel.tips_verified > 0, "Replay produced zero verified tips"
    assert run.funnel.tips_scored > 0, "Replay produced zero scored tips"
    assert client.budget.run_used == 0, (
        f"Replay mode made {client.budget.run_used} live SerpApi call(s) — "
        "it should serve everything from the fixture bundle."
    )
