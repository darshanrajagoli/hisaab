"""Tests for cache key canonicalization, window building, and ticker resolution."""

import pytest

from hisaab.models import TranscriptSnippet
from hisaab.pipeline.windows import _has_tip_keywords, build_windows
from hisaab.serp.cache import SerpCache, _make_cache_key


class TestCacheKey:
    """Cache key must be deterministic regardless of parameter order."""

    def test_order_independent(self):
        params1 = {"engine": "google_finance", "q": "RELIANCE:NSE", "window": "1Y"}
        params2 = {"window": "1Y", "engine": "google_finance", "q": "RELIANCE:NSE"}
        assert _make_cache_key(params1) == _make_cache_key(params2)

    def test_api_key_excluded(self):
        params1 = {"engine": "test", "q": "hello", "api_key": "secret123"}
        params2 = {"engine": "test", "q": "hello"}
        assert _make_cache_key(params1) == _make_cache_key(params2)

    def test_different_params_different_keys(self):
        params1 = {"engine": "test", "q": "hello"}
        params2 = {"engine": "test", "q": "world"}
        assert _make_cache_key(params1) != _make_cache_key(params2)


class TestSerpCache:
    def test_put_and_get(self, tmp_path):
        cache = SerpCache(db_path=tmp_path / "test_cache.db")
        params = {"engine": "youtube_video", "v": "abc123"}
        response = {"video_results": {"title": "Test"}}

        cache.put(params, response)
        result = cache.get(params)

        assert result is not None
        assert result["video_results"]["title"] == "Test"
        cache.close()

    def test_miss(self, tmp_path):
        cache = SerpCache(db_path=tmp_path / "test_cache.db")
        result = cache.get({"engine": "test", "q": "nonexistent"})
        assert result is None
        cache.close()

    def test_immutable_never_expires(self, tmp_path):
        cache = SerpCache(db_path=tmp_path / "test_cache.db")
        params = {"engine": "youtube_video_transcript", "video_id": "abc"}
        cache.put(params, {"transcript": "test"})

        # Should still be there (TTL = -1)
        result = cache.get(params)
        assert result is not None
        cache.close()


class TestWindowBuilding:
    def test_basic_windows(self):
        snippets = [
            TranscriptSnippet(text=f"word {i}", start_ms=i * 5000, end_ms=(i + 1) * 5000)
            for i in range(30)
        ]
        windows = build_windows("vid1", snippets)
        assert len(windows) > 0
        assert all(w.video_id == "vid1" for w in windows)

    def test_empty_snippets(self):
        windows = build_windows("vid1", [])
        assert windows == []

    def test_windows_have_text(self):
        snippets = [
            TranscriptSnippet(text="reliance target 2800", start_ms=0, end_ms=5000),
            TranscriptSnippet(text="stop loss 2500", start_ms=5000, end_ms=10000),
        ]
        windows = build_windows("vid1", snippets)
        assert len(windows) > 0
        assert "reliance" in windows[0].text.lower()


class TestKeywordDetection:
    def test_english_keywords(self):
        assert _has_tip_keywords("buy reliance target 2800") is True
        assert _has_tip_keywords("stop loss at 500") is True
        assert _has_tip_keywords("this is a multibagger stock") is True

    def test_hindi_keywords(self):
        assert _has_tip_keywords("reliance kharid lo") is True
        assert _has_tip_keywords("खरीदो ये शेयर") is True

    def test_no_keywords(self):
        assert _has_tip_keywords("hello everyone welcome to my channel") is False
        assert _has_tip_keywords("let me tell you about my vacation") is False

    def test_price_patterns(self):
        assert _has_tip_keywords("₹2800 tak target hai") is True
        assert _has_tip_keywords("rs 500 stop loss") is True

    def test_company_names(self):
        assert _has_tip_keywords("tata motors ka analysis") is True
        assert _has_tip_keywords("zomato strong buy") is True


class TestTickerResolver:
    def test_alias_match(self):
        from hisaab.pipeline.resolve import TickerResolver

        resolver = TickerResolver()
        # Only run if data files exist
        if not resolver.aliases:
            pytest.skip("No alias data available")

        result = resolver.resolve("reliance")
        assert result is not None
        assert result["symbol"] == "RELIANCE"

    def test_fuzzy_match(self):
        from hisaab.pipeline.resolve import TickerResolver

        resolver = TickerResolver()
        if not resolver.nse_data:
            pytest.skip("No NSE data available")

        result = resolver.resolve("Tata Consultancy Services")
        assert result is not None
        assert result["symbol"] == "TCS"

    def test_no_match(self):
        from hisaab.pipeline.resolve import TickerResolver

        resolver = TickerResolver()
        result = resolver.resolve("xyznonexistentcorp12345")
        assert result is None
