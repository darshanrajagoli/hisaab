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

from anthropic import Anthropic

logger = logging.getLogger(__name__)

_client: Optional[Anthropic] = None


def get_client() -> Anthropic:
    """Get or create the Anthropic client."""
    global _client
    if _client is None:
        _client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
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
    model: str = "claude-sonnet-4-5-20250514",
    max_tokens: int = 4096,
    temperature: float = 0.0,
) -> str:
    """Make a single LLM call and return the text response."""
    client = get_client()
    messages = [{"role": "user", "content": prompt}]
    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": messages,
        "temperature": temperature,
    }
    if system:
        kwargs["system"] = system

    response = client.messages.create(**kwargs)
    return response.content[0].text


def call_llm_json(
    prompt: str,
    system: str = "",
    model: str = "claude-sonnet-4-5-20250514",
    max_tokens: int = 4096,
) -> Any:
    """Make an LLM call expecting JSON output."""
    text = call_llm(prompt, system=system, model=model, max_tokens=max_tokens)
    return extract_json(text)


def classify_video_titles(titles: list[dict[str, str]]) -> list[dict[str, str]]:
    """
    Classify video titles into tip categories.

    Uses Haiku for cost efficiency.
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
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
    )
    return result
