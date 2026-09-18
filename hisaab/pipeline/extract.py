"""
Step 8: Tip extraction.

Uses an LLM to extract structured stock tips from transcript windows.
The prompt includes Hinglish few-shot examples and strict rules.
"""

from __future__ import annotations

import logging
from pathlib import Path

from hisaab.llm import ReplayFixtureMissing, call_llm_json
from hisaab.models import ExtractedTip, TranscriptWindow

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "extract_tips.txt"

# The LLM mostly follows the prompt's exact enum values, but occasionally
# drifts to a plausible synonym (e.g. "SELL" instead of "SHORT"). Coerce
# known synonyms instead of dropping an otherwise-valid tip.
_DIRECTION_SYNONYMS = {
    "SELL": "SHORT",
    "SHORT_SELL": "SHORT",
    "BUY": "LONG",
    "EXIT": "AVOID",
    "STAY_AWAY": "AVOID",
}
_INSTRUMENT_SYNONYMS = {
    "COMMODITY": "OTHER",
    "OPTIONS": "FNO",
    "FUTURES": "FNO",
    "STOCK": "EQUITY",
    "SHARE": "EQUITY",
    "ETF": "OTHER",
    "CASH": "EQUITY",
}
_HORIZON_SYNONYMS = {
    "SHORT_TERM": "SWING",
    "MEDIUM_TERM": "POSITIONAL",
    "LONG": "LONG_TERM",
    "UNKNOWN": "UNSPECIFIED",
    "NONE": "UNSPECIFIED",
}


_CONFIDENCE_WORDS = {"HIGH": 0.9, "MEDIUM": 0.6, "MED": 0.6, "LOW": 0.3}


def _normalize_confidence(value) -> float:
    """The LLM occasionally returns a word ("HIGH") instead of a 0-1 float."""
    if isinstance(value, str):
        word = value.strip().upper()
        if word in _CONFIDENCE_WORDS:
            return _CONFIDENCE_WORDS[word]
        try:
            return float(value)
        except ValueError:
            return 0.5
    if isinstance(value, (int, float)):
        return float(value)
    return 0.5


def _normalize_enum(value, synonyms: dict[str, str], default: str) -> str:
    """Map an LLM-produced string onto a known enum value, or fall back to default."""
    if not value:
        return default
    value = str(value).strip().upper().replace(" ", "_")
    # The LLM occasionally echoes a Python-style enum repr, e.g. "Direction.LONG".
    if "." in value:
        value = value.rsplit(".", 1)[-1]
    return synonyms.get(value, value)


def _load_system_prompt() -> str:
    """Load the extraction system prompt from file."""
    if PROMPT_PATH.exists():
        return PROMPT_PATH.read_text()
    return "Extract stock tips from the transcript. Return a JSON array."


def extract_tips_from_window(window: TranscriptWindow) -> list[ExtractedTip]:
    """
    Extract stock tips from a single transcript window.

    Returns a list of ExtractedTip objects (may be empty).
    """
    system = _load_system_prompt()

    prompt = f"""Video ID: {window.video_id}
Window start_ms: {window.start_ms}
Window end_ms: {window.end_ms}

Transcript:
{window.text}

Extract all actionable stock tips. Return a JSON array."""

    try:
        raw = call_llm_json(prompt, system=system, max_tokens=2048)
    except ReplayFixtureMissing:
        raise
    except Exception as e:
        logger.warning(f"Extraction failed for {window.video_id}@{window.start_ms}: {e}")
        return []

    if not isinstance(raw, list):
        raw = [raw] if isinstance(raw, dict) else []

    tips: list[ExtractedTip] = []
    for item in raw:
        try:
            # Ensure required fields have defaults
            item.setdefault("video_id", window.video_id)
            item.setdefault("start_ms", window.start_ms)
            item.setdefault("end_ms", window.end_ms)
            item.setdefault("conviction_flags", [])
            item.setdefault("extractor_confidence", 0.5)

            # The prompt asks the LLM to restate start_ms/end_ms, and it
            # occasionally hallucinates a value outside the window it was
            # actually shown (e.g. 0 or a small offset) — that timestamp
            # drives the YouTube deep-link on the Tip Detail screen, so an
            # out-of-range value would silently point at the wrong moment.
            # Clamp to the window we actually sent, don't trust the echo.
            try:
                start_ms = int(item["start_ms"])
            except (TypeError, ValueError):
                start_ms = window.start_ms
            if not (window.start_ms <= start_ms <= window.end_ms):
                start_ms = window.start_ms
            item["start_ms"] = start_ms

            try:
                end_ms = int(item["end_ms"])
            except (TypeError, ValueError):
                end_ms = window.end_ms
            if not (start_ms <= end_ms <= window.end_ms):
                end_ms = window.end_ms
            item["end_ms"] = end_ms

            item["direction"] = _normalize_enum(item.get("direction"), _DIRECTION_SYNONYMS, "LONG")
            item["instrument_type"] = _normalize_enum(
                item.get("instrument_type"), _INSTRUMENT_SYNONYMS, "EQUITY"
            )
            item["horizon_bucket"] = _normalize_enum(
                item.get("horizon_bucket"), _HORIZON_SYNONYMS, "UNSPECIFIED"
            )
            item["extractor_confidence"] = _normalize_confidence(item.get("extractor_confidence"))

            tip = ExtractedTip(**item)
            tips.append(tip)
        except Exception as e:
            logger.debug(f"Failed to parse extracted tip: {e}")
            continue

    return tips


def extract_tips_from_windows(
    windows: list[TranscriptWindow],
) -> list[ExtractedTip]:
    """Extract tips from all keyword-matching windows."""
    all_tips: list[ExtractedTip] = []

    for window in windows:
        if not window.has_tip_keywords:
            continue
        tips = extract_tips_from_window(window)
        all_tips.extend(tips)
        if tips:
            logger.info(
                f"  Extracted {len(tips)} tips from {window.video_id}@{window.start_ms // 1000}s"
            )

    logger.info(f"Total extracted: {len(all_tips)} tips from {len(windows)} windows")
    return all_tips
