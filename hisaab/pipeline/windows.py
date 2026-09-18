"""
Step 7: Transcript windowing.

Merge snippets into ~90-second windows with ~15s overlap.
Pre-filter with deterministic keyword scan before LLM extraction.
"""

from __future__ import annotations

import re

from hisaab.models import TranscriptSnippet, TranscriptWindow

# ── Tip keywords for pre-filtering ──────────────────────────────────────────

KEYWORDS_EN = {
    "target",
    "stop loss",
    "stoploss",
    "sl",
    "buy",
    "sell",
    "entry",
    "accumulate",
    "breakout",
    "multibagger",
    "rupees",
    "₹",
    "nse",
    "bse",
    "stock",
    "share",
    "invest",
    "portfolio",
    "bullish",
    "bearish",
    "long",
    "short",
    "cmp",
    "current market price",
}

KEYWORDS_HI = {
    "kharid",
    "khareed",
    "khareedna",
    "kharido",
    "lakshya",
    "stoploss",
    "target",
    "becho",
    "bech",
    "niklo",
    "खरीद",
    "खरीदो",
    "लक्ष्य",
    "बेचो",
    "स्टॉप",
    "लॉस",
    "टारगेट",
    "निवेश",
    "शेयर",
    "स्टॉक",
}

ALL_KEYWORDS = KEYWORDS_EN | KEYWORDS_HI

# Common Indian company names that appear in tips
COMPANY_KEYWORDS = {
    "reliance",
    "tata",
    "infosys",
    "hdfc",
    "icici",
    "sbi",
    "wipro",
    "adani",
    "bajaj",
    "kotak",
    "hul",
    "itc",
    "airtel",
    "maruti",
    "titan",
    "zomato",
    "paytm",
    "jio",
    "vedanta",
    "hindalco",
    "tcs",
    "hcl",
    "tech mahindra",
    "axis",
    "indusind",
    "power grid",
    "ntpc",
    "ongc",
    "coal india",
    "bpcl",
    "ioc",
    "gail",
    "bhel",
    "sail",
    "irctc",
    "rvnl",
    "suzlon",
    "nhpc",
}

WINDOW_DURATION_MS = 90_000  # 90 seconds
OVERLAP_MS = 15_000  # 15 seconds


def build_windows(
    video_id: str,
    snippets: list[TranscriptSnippet],
    window_duration_ms: int = WINDOW_DURATION_MS,
    overlap_ms: int = OVERLAP_MS,
) -> list[TranscriptWindow]:
    """
    Merge transcript snippets into overlapping windows.

    Each window is ~90 seconds of text with ~15 seconds of overlap
    with the previous window.
    """
    if not snippets:
        return []

    # Sort by start time
    snippets = sorted(snippets, key=lambda s: s.start_ms)

    windows: list[TranscriptWindow] = []
    window_idx = 0
    i = 0

    while i < len(snippets):
        # Start a new window
        window_start = snippets[i].start_ms
        window_end = window_start + window_duration_ms
        texts: list[str] = []
        actual_end = window_start

        # Collect snippets within the window
        j = i
        while j < len(snippets) and snippets[j].start_ms < window_end:
            texts.append(snippets[j].text)
            actual_end = max(actual_end, snippets[j].end_ms)
            j += 1

        window_text = " ".join(texts)

        # Check for tip keywords
        has_keywords = _has_tip_keywords(window_text)

        windows.append(
            TranscriptWindow(
                video_id=video_id,
                window_index=window_idx,
                text=window_text,
                start_ms=window_start,
                end_ms=actual_end,
                has_tip_keywords=has_keywords,
            )
        )

        window_idx += 1

        # Advance to next window start, accounting for overlap
        step_ms = window_duration_ms - overlap_ms
        # Find the first snippet that starts after our step
        next_start = window_start + step_ms
        while i < len(snippets) and snippets[i].start_ms < next_start:
            i += 1

        # If we didn't advance, force advance by 1
        if i == 0 or (i < len(snippets) and snippets[i].start_ms <= window_start):
            i = j  # Jump past this window's snippets

    return windows


def filter_windows(windows: list[TranscriptWindow]) -> list[TranscriptWindow]:
    """Return only windows that contain tip keywords."""
    return [w for w in windows if w.has_tip_keywords]


def _has_tip_keywords(text: str) -> bool:
    """Check if text contains any tip-related keywords."""
    text_lower = text.lower()

    # Check general keywords
    for kw in ALL_KEYWORDS:
        if kw in text_lower:
            return True

    # Check company names
    for company in COMPANY_KEYWORDS:
        if company in text_lower:
            return True

    # Check for price patterns (₹ followed by numbers)
    if re.search(r"(?:₹|rs\.?|rupee)\s*\d", text_lower):
        return True

    # Check for number patterns that look like targets/stops
    if re.search(r"\d{3,5}\s*(?:tak|तक|target|stop|sl)", text_lower):
        return True

    return False
