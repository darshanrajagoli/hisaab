"""
LLM abstraction layer.

The LLM's ONLY job is to read messy speech and produce structured data.
Every number on the scorecard comes from deterministic Python.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Optional

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

logger = logging.getLogger(__name__)

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
