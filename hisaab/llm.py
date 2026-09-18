"""
LLM abstraction layer.

The LLM's ONLY job is to read messy speech and produce structured data.
Every number on the scorecard comes from deterministic Python.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-3.6-flash"

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
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=config,
    )
    return response.text


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
