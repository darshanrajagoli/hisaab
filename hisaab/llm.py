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
import time
from pathlib import Path
from typing import Any, Optional

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
_LLM_CACHE_PATH = Path(os.getenv("HISAAB_LLM_CACHE_DB", "hisaab_llm_cache.db"))
_llm_cache_conn: Optional[sqlite3.Connection] = None


def _get_llm_cache_conn() -> sqlite3.Connection:
    global _llm_cache_conn
    if _llm_cache_conn is None:
        _llm_cache_conn = sqlite3.connect(str(_LLM_CACHE_PATH))
        _llm_cache_conn.execute("PRAGMA journal_mode=WAL")
        _llm_cache_conn.execute(
            "CREATE TABLE IF NOT EXISTS llm_cache ("
            "cache_key TEXT PRIMARY KEY, response TEXT NOT NULL)"
        )
        _llm_cache_conn.commit()
    return _llm_cache_conn


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

    last_error: Optional[Exception] = None
    for attempt in range(_MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=config,
            )
            _llm_cache_put(cache_key, response.text)
            return response.text
        except genai_errors.ServerError as e:
            # Transient overload (503) — worth a short backoff and retry.
            last_error = e
            if attempt < _MAX_RETRIES - 1:
                time.sleep(2**attempt)
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

    result = call_llm_json(
        prompt,
        system=system,
        model=DEFAULT_MODEL,
        max_tokens=2048,
    )
    return result
