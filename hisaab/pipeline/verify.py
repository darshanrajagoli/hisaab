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

from hisaab.llm import ReplayFixtureMissing, call_llm_json
from hisaab.models import ExtractedTip, TranscriptWindow, VerifiedTip
from hisaab.pipeline.extract import (
    _DIRECTION_SYNONYMS,
    _HORIZON_SYNONYMS,
    _INSTRUMENT_SYNONYMS,
    _normalize_enum,
)

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

    verified: list[VerifiedTip] = []
    dropped_fuzzy = 0
    dropped_llm = 0
    llm_skipped = 0

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
            if llm_result.get("llm_verify_skipped"):
                llm_skipped += 1
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
            _renormalize_enums(tip_dict)
            notes = str(corrections) if corrections else ""
            if llm_result.get("llm_verify_skipped"):
                skip_note = (
                    "LLM verification layer was skipped (API error) — "
                    "only fuzzy-match verified"
                )
                notes = f"{notes}; {skip_note}" if notes else skip_note
            try:
                vtip = VerifiedTip(**tip_dict, verification_notes=notes)
            except Exception as e:
                # An LLM correction can still produce an invalid combination
                # (e.g. a bad enum) — don't let one bad tip kill the whole run.
                logger.warning(f"Dropping tip after invalid correction: {e}")
                dropped_llm += 1
                continue
        else:
            vtip = VerifiedTip(**tip.model_dump())

        verified.append(vtip)

    logger.info(
        f"Verification: {len(verified)} passed, "
        f"{dropped_fuzzy} dropped (fuzzy), {dropped_llm} dropped (LLM)"
        + (f", {llm_skipped} LLM checks skipped due to errors" if llm_skipped else "")
    )
    return verified


def _renormalize_enums(tip_dict: dict) -> None:
    """Re-apply enum synonym coercion after LLM corrections are merged in."""
    tip_dict["direction"] = _normalize_enum(
        tip_dict.get("direction"), _DIRECTION_SYNONYMS, "LONG"
    )
    tip_dict["instrument_type"] = _normalize_enum(
        tip_dict.get("instrument_type"), _INSTRUMENT_SYNONYMS, "EQUITY"
    )
    tip_dict["horizon_bucket"] = _normalize_enum(
        tip_dict.get("horizon_bucket"), _HORIZON_SYNONYMS, "UNSPECIFIED"
    )


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

        # Sort by start_ms, keep earliest — this is the timestamp the Tip
        # Detail screen deep-links to, so any field backfilled from a later
        # mention below was NOT necessarily said at that exact moment.
        group.sort(key=lambda t: t.start_ms)
        primary = group[0]
        backfilled_from_later: list[str] = []

        # Merge fields from later mentions
        for later in group[1:]:
            if primary.stated_target is None and later.stated_target is not None:
                primary.stated_target = later.stated_target
                backfilled_from_later.append("target")
            if primary.stated_stop_loss is None and later.stated_stop_loss is not None:
                primary.stated_stop_loss = later.stated_stop_loss
                backfilled_from_later.append("stop_loss")
            if primary.stated_entry_price is None and later.stated_entry_price is not None:
                primary.stated_entry_price = later.stated_entry_price
                backfilled_from_later.append("entry_price")
            if (
                primary.horizon_bucket.value == "UNSPECIFIED"
                and later.horizon_bucket.value != "UNSPECIFIED"
            ):
                primary.horizon_bucket = later.horizon_bucket
            primary.conviction_flags = list(set(primary.conviction_flags + later.conviction_flags))

        if backfilled_from_later:
            fields = ", ".join(sorted(set(backfilled_from_later)))
            note = f"Filled in from a later mention in the same video: {fields}"
            primary.verification_notes = (
                f"{primary.verification_notes}; {note}" if primary.verification_notes else note
            )

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


def _load_system_prompt() -> str:
    """Load the verification system prompt from file.

    See extract.py's _load_system_prompt for why encoding is explicit —
    same bug class, same fix.
    """
    if VERIFY_PROMPT_PATH.exists():
        return VERIFY_PROMPT_PATH.read_text(encoding="utf-8")
    return ""


def _llm_verify(tip: ExtractedTip, window_text: str) -> dict:
    """Use LLM to verify the tip against the window text."""
    system = _load_system_prompt()

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
            model="gemini-3.1-flash-lite",
            max_tokens=512,
        )
    except ReplayFixtureMissing:
        raise
    except Exception as e:
        # Don't silently mark the tip verified — an LLM outage or quota
        # exhaustion here previously produced "0 dropped (LLM)" in the
        # funnel, which reads as a clean bill of health rather than "layer
        # 2 never ran". Surface it as an explicit skip instead.
        logger.warning(f"LLM verification call failed: {e}")
        return {"supported": True, "llm_verify_skipped": True, "reason": str(e)}
