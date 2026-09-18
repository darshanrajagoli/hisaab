"""
Tests for replay mode — the "judges can run this with zero API keys" claim.

These assert against the actual shipped fixtures/demo/ bundle, not mocks,
so a broken or incomplete bundle fails CI instead of shipping silently.
"""

from __future__ import annotations

import os

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


@pytest.mark.skipif(
    not os.getenv("HISAAB_RUN_LLM_REPLAY_TEST"),
    reason=(
        "Full end-to-end replay (LLM extraction included) needs a bundled "
        "LLM response cache, which is not yet shipped. Set "
        "HISAAB_RUN_LLM_REPLAY_TEST=1 once fixtures/demo includes one."
    ),
)
def test_full_audit_replay_produces_scored_tips():
    """Placeholder for the real end-to-end assertion the audit called for.

    Once an LLM-response fixture is shipped alongside the SerpApi fixtures,
    this should run `hisaab audit <demo channel> --replay demo` and assert
    at least one scored tip comes back — catching a broken/incomplete
    bundle before it reaches judges, instead of a formatted-but-empty
    scorecard.
    """
    pytest.skip("Not yet implemented — see docstring.")
