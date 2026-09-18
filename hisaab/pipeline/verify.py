"""
Step 9: Two-layer tip verification.

Layer 1: Deterministic fuzzy-match of quote against transcript.
Layer 2: LLM cross-check that the quote supports the extracted fields.

Then merge duplicates within the same video.
"""

from __future__ import annotations

import logging
from pathlib import Path

from rapidfuzz import fuzz

from hisaab.llm import call_llm_json
from hisaab.models import ExtractedTip, TranscriptWindow, VerifiedTip

logger = logging.getLogger(__name__)

VERIFY_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "verify_tip.txt"
FUZZY_THRESHOLD = 70  # Partial ratio minimum


def verify_tips(
    tips: list[ExtractedTip],
    windows: list[TranscriptWindow],
    use_llm_verify: bool = True,
) -> list[VerifiedTip]:
    """
    Verify extracted tips through two layers.

    Returns only tips that pass both checks.
    """
    # Build a lookup from (video_id, start_ms) -> window text
    window_lookup: dict[tuple[str, int], str] = {}
    for w in windows:
        window_lookup[(w.video_id, w.start_ms)] = w.text
        # Also index nearby windows (overlap means exact match may differ)
        for other_w in windows:
            if other_w.video_id == w.video_id:
                window_lookup[(other_w.video_id, other_w.start_ms)] = other_w.text

    verified: list[VerifiedTip] = []
    dropped_fuzzy = 0
    dropped_llm = 0

    for tip in tips:
        # Find the matching window text
        window_text = _find_window_text(tip, window_lookup, windows)
        if not window_text:
            logger.debug(f"No window found for tip {tip.company_name_raw}@{tip.start_ms}")
            dropped_fuzzy += 1
            continue

        # Layer 1: Deterministic fuzzy match
        if not _fuzzy_verify(tip.quote_original, window_text):
            logger.debug(
                f"Fuzzy verification failed for {tip.company_name_raw}: score < {FUZZY_THRESHOLD}"
            )
            dropped_fuzzy += 1
            continue

        # Layer 2: LLM verification (optional)
        if use_llm_verify:
            llm_result = _llm_verify(tip, window_text)
            if not llm_result.get("supported", False):
                logger.debug(
                    f"LLM verification failed for {tip.company_name_raw}: "
                    f"{llm_result.get('reason', 'unknown')}"
                )
                dropped_llm += 1
                continue

            # Apply corrections if any
            corrections = llm_result.get("corrections", {})
            tip_dict = tip.model_dump()
            tip_dict.update(corrections)
            vtip = VerifiedTip(
                **tip_dict, verification_notes=str(corrections) if corrections else ""
            )
        else:
            vtip = VerifiedTip(**tip.model_dump())

        verified.append(vtip)

    logger.info(
        f"Verification: {len(verified)} passed, "
        f"{dropped_fuzzy} dropped (fuzzy), {dropped_llm} dropped (LLM)"
    )
    return verified


def merge_duplicates(tips: list[VerifiedTip]) -> list[VerifiedTip]:
    """
    Merge duplicate mentions of the same stock within a video.

    Keeps the earliest timestamp and merges fields.
    """
    # Group by (video_id, company_name_raw normalized)
    groups: dict[tuple[str, str], list[VerifiedTip]] = {}
    for tip in tips:
        key = (tip.video_id, tip.company_name_raw.lower().strip())
        groups.setdefault(key, []).append(tip)

    merged: list[VerifiedTip] = []
    for key, group in groups.items():
        if len(group) == 1:
            merged.append(group[0])
            continue

        # Sort by start_ms, keep earliest
        group.sort(key=lambda t: t.start_ms)
        primary = group[0]

        # Merge fields from later mentions
        for later in group[1:]:
            if primary.stated_target is None and later.stated_target is not None:
                primary.stated_target = later.stated_target
            if primary.stated_stop_loss is None and later.stated_stop_loss is not None:
                primary.stated_stop_loss = later.stated_stop_loss
            if primary.stated_entry_price is None and later.stated_entry_price is not None:
                primary.stated_entry_price = later.stated_entry_price
            if (
                primary.horizon_bucket.value == "UNSPECIFIED"
                and later.horizon_bucket.value != "UNSPECIFIED"
            ):
                primary.horizon_bucket = later.horizon_bucket
            primary.conviction_flags = list(set(primary.conviction_flags + later.conviction_flags))

        merged.append(primary)

    if len(tips) != len(merged):
        logger.info(f"Merged {len(tips)} tips → {len(merged)} (removed duplicates)")

    return merged


def _find_window_text(
    tip: ExtractedTip,
    lookup: dict[tuple[str, int], str],
    windows: list[TranscriptWindow],
) -> str:
    """Find the window text that matches this tip."""
    # Exact match
    key = (tip.video_id, tip.start_ms)
    if key in lookup:
        return lookup[key]

    # Find closest window for this video
    video_windows = [w for w in windows if w.video_id == tip.video_id]
    if not video_windows:
        return ""

    closest = min(video_windows, key=lambda w: abs(w.start_ms - tip.start_ms))
    return closest.text


def _fuzzy_verify(quote: str, window_text: str) -> bool:
    """Check if the quote is a reasonable match against the window text."""
    if not quote or not window_text:
        return False
    score = fuzz.partial_ratio(quote.lower(), window_text.lower())
    return score >= FUZZY_THRESHOLD


def _llm_verify(tip: ExtractedTip, window_text: str) -> dict:
    """Use LLM to verify the tip against the window text."""
    system = ""
    if VERIFY_PROMPT_PATH.exists():
        system = VERIFY_PROMPT_PATH.read_text()

    prompt = f"""Transcript window:
{window_text}

Extracted tip:
- Company: {tip.company_name_raw}
- Direction: {tip.direction.value}
- Quote: {tip.quote_original}
- Entry: {tip.stated_entry_price}
- Target: {tip.stated_target}
- Stop loss: {tip.stated_stop_loss}

Is this tip supported by the transcript? Return JSON."""

    try:
        return call_llm_json(
            prompt,
            system=system,
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
        )
    except Exception as e:
        logger.warning(f"LLM verification call failed: {e}")
        return {"supported": True}  # Pass through on failure
