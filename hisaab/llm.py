"""
LLM abstraction layer.

The LLM's ONLY job is to read messy speech and produce structured data.
Every number on the scorecard comes from deterministic Python.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Optional

import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

logger = logging.getLogger(__name__)


class ReplayFixtureMissing(RuntimeError):
    """Raised in replay mode when no cached LLM response covers a prompt.

    Deliberately NOT a subclass of a broadly-caught error type on its own —
    pipeline steps must catch this specifically and re-raise it rather than
    letting a generic `except Exception` swallow it into a silent empty
    result (that's what made a broken replay bundle look like "0 tips
    extracted" instead of a loud, obvious failure).
    """


# Gemini's free tier caps at 500 requests/DAY total (all endpoints share the
# quota). Re-running an audit re-extracts every window from scratch unless
# responses are cached, which burns through the daily cap on repeat runs of
# the same channel/videos. This cache makes identical (prompt, model, temp)
# calls free on replay.
#
# In replay mode there's no live API to fall back on, so lookups go against
# the read-only bundle shipped in fixtures/<bundle>/llm_cache.db instead of
# the local (gitignored) working cache — that's what lets `--replay demo`
# reproduce a full audit with zero API keys on a machine that's never made a
# live call.
_FIXTURES_ROOT = Path(__file__).parent.parent / "fixtures"


def _llm_cache_path() -> Path:
    """Resolved lazily (not at import time) since HISAAB_MODE is set by the
    CLI/app after this module is already imported."""
    override = os.getenv("HISAAB_LLM_CACHE_DB")
    if override:
        return Path(override)
    if os.getenv("HISAAB_MODE") == "replay":
        bundle = os.getenv("HISAAB_REPLAY_BUNDLE", "demo")
        return _FIXTURES_ROOT / bundle / "llm_cache.db"
    return Path("hisaab_llm_cache.db")


# One connection per thread: sqlite3 connections can't cross threads, and
# Streamlit runs every session (and rerun) on its own script thread. A single
# module-level connection worked for the first audit on a server and made
# every later one fail each cache lookup — silently, as "0 tips".
_llm_cache_local = threading.local()


def _get_llm_cache_conn() -> sqlite3.Connection:
    path = _llm_cache_path()
    conn = getattr(_llm_cache_local, "conn", None)
    if conn is None or getattr(_llm_cache_local, "path", None) != path:
        conn = sqlite3.connect(str(path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS llm_cache ("
            "cache_key TEXT PRIMARY KEY, response TEXT NOT NULL)"
        )
        conn.commit()
        _llm_cache_local.conn = conn
        _llm_cache_local.path = path
    return conn


def _llm_cache_key(model: str, system: str, prompt: str, temperature: float) -> str:
    canonical = json.dumps(
        {"model": model, "system": system, "prompt": prompt, "temperature": temperature},
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def _llm_cache_get(key: str) -> Optional[str]:
    row = _get_llm_cache_conn().execute(
        "SELECT response FROM llm_cache WHERE cache_key = ?", (key,)
    ).fetchone()
    return row[0] if row else None


def _llm_cache_put(key: str, response: str) -> None:
    conn = _get_llm_cache_conn()
    conn.execute(
        "INSERT OR REPLACE INTO llm_cache (cache_key, response) VALUES (?, ?)", (key, response)
    )
    conn.commit()

# gemini-3.6-flash's free tier caps at 20 requests/DAY — far too low for a
# pipeline that makes many calls per audit (classification, extraction per
# window, verification, disambiguation). gemini-3.1-flash-lite draws from a
# separate, much larger free quota and is plenty capable for structured
# extraction tasks like this one.
DEFAULT_MODEL = "gemini-3.1-flash-lite"

_MAX_RETRIES = 3

# The free tier also caps requests per MINUTE (15 for flash-lite). An audit
# fires dozens of extraction/verification calls back to back, so without
# pacing it bursts past that cap and windows start failing with 429s.
_MIN_CALL_INTERVAL_S = 60 / 14
_RATE_LIMIT_BACKOFF_S = 30
_last_call_at = 0.0

_client: Optional[genai.Client] = None


def get_client() -> genai.Client:
    """Get or create the Gemini client."""
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.getenv("GEMINI_API_KEY", ""))
    return _client


def extract_json(text: str) -> Any:
    """Extract JSON from a response that may have markdown fences."""
    text = text.strip()
    if text.startswith("```"):
        # Remove markdown code fences
        lines = text.split("\n")
        lines = [line for line in lines if not line.strip().startswith("```")]
        text = "\n".join(lines)
    return json.loads(text)


def call_llm(
    prompt: str,
    system: str = "",
    model: str = DEFAULT_MODEL,
    max_tokens: int = 4096,
    temperature: float = 0.0,
) -> str:
    """Make a single LLM call and return the text response."""
    cache_key = _llm_cache_key(model, system, prompt, temperature)
    cached = _llm_cache_get(cache_key)
    if cached is not None:
        return cached

    if os.getenv("HISAAB_MODE") == "replay":
        raise ReplayFixtureMissing(
            "Replay mode: no cached LLM response for this prompt and no live "
            "calls are allowed. The demo fixture bundle is incomplete for this input."
        )

    client = get_client()
    config = types.GenerateContentConfig(
        max_output_tokens=max_tokens,
        temperature=temperature,
        system_instruction=system or None,
    )

    global _last_call_at
    last_error: Optional[Exception] = None
    for attempt in range(_MAX_RETRIES):
        wait = _MIN_CALL_INTERVAL_S - (time.monotonic() - _last_call_at)
        if wait > 0:
            time.sleep(wait)
        _last_call_at = time.monotonic()
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=config,
            )
            _llm_cache_put(cache_key, response.text)
            return response.text
        except (genai_errors.ServerError, httpx.TransportError) as e:
            # Transient overload (503) or a dropped connection ("Server
            # disconnected without sending a response") — back off and retry.
            last_error = e
            if attempt < _MAX_RETRIES - 1:
                time.sleep(2**attempt)
        except genai_errors.ClientError as e:
            # 429 is usually the per-minute cap and clears within a minute;
            # if it's the daily cap, the retries fail too and it surfaces.
            if e.code != 429:
                raise
            last_error = e
            if attempt < _MAX_RETRIES - 1:
                logger.warning(f"Gemini rate limit hit, retrying in {_RATE_LIMIT_BACKOFF_S}s")
                time.sleep(_RATE_LIMIT_BACKOFF_S)
    raise last_error


def call_llm_json(
    prompt: str,
    system: str = "",
    model: str = DEFAULT_MODEL,
    max_tokens: int = 4096,
) -> Any:
    """Make an LLM call expecting JSON output."""
    text = call_llm(prompt, system=system, model=model, max_tokens=max_tokens)
    return extract_json(text)


def classify_video_titles(titles: list[dict[str, str]]) -> list[dict[str, str]]:
    """
    Classify video titles into tip categories.

    Uses Gemini Flash for cost efficiency (free tier).
    Returns list of {video_id, title, classification}.
    """
    system = (
        "You classify Indian stock market YouTube video titles into categories. "
        "Respond ONLY with a JSON array. No other text."
    )
    prompt = f"""Classify each video title into one of these categories:
- "likely-tip": Contains specific stock buy/sell calls, targets, recommendations
- "commentary": General market analysis, news discussion, sector overview
- "fno": Focused on futures, options, F&O strategies
- "other": Educational, motivational, unrelated

Videos:
{json.dumps(titles, indent=2)}

Return a JSON array of objects with "video_id", "title", and "classification" fields.
Return ONLY the JSON array, no other text."""

    # A fixed 2048-token cap silently truncated the JSON array mid-object on
    # channels with enough videos (~40+ titles), producing invalid JSON that
    # fell through to the heuristic classifier instead of raising — nobody
    # noticed because the fallback still "worked", just non-deterministically.
    # Scale with the number of titles instead of guessing a fixed ceiling.
    max_tokens = max(2048, 120 * len(titles) + 512)

    result = call_llm_json(
        prompt,
        system=system,
        model=DEFAULT_MODEL,
        max_tokens=max_tokens,
    )
    return result
