"""
Step 4: Video selection.

Classify titles to find likely-tip videos, then take the top N (in
discovery order) within the run budget.
"""

from __future__ import annotations

import logging

from hisaab.llm import classify_video_titles
from hisaab.models import VideoInfo

logger = logging.getLogger(__name__)


def select_videos(
    videos: list[VideoInfo],
    max_videos: int = 10,
    use_llm: bool = True,
) -> list[VideoInfo]:
    """
    Select videos to audit.

    1. Classify titles (LLM or heuristic)
    2. Filter to likely-tip videos
    3. Return the first N, in the order they were discovered
    """
    if not videos:
        return []

    # Classify
    if use_llm and len(videos) > 0:
        try:
            titles = [{"video_id": v.video_id, "title": v.title} for v in videos]
            classifications = classify_video_titles(titles)
            class_map = {c["video_id"]: c["classification"] for c in classifications}
            for v in videos:
                v.classification = class_map.get(v.video_id, "unknown")
        except Exception as e:
            logger.warning(f"LLM classification failed, using heuristics: {e}")
            for v in videos:
                v.classification = _heuristic_classify(v.title)
    else:
        for v in videos:
            v.classification = _heuristic_classify(v.title)

    # Filter to likely tips
    tip_videos = [v for v in videos if v.classification == "likely-tip"]

    # If too few, include unknowns
    if len(tip_videos) < max_videos:
        unknowns = [v for v in videos if v.classification in ("unknown", "commentary")]
        tip_videos.extend(unknowns)

    # Deduplicate
    seen = set()
    unique = []
    for v in tip_videos:
        if v.video_id not in seen:
            seen.add(v.video_id)
            unique.append(v)

    selected = unique[:max_videos]
    logger.info(
        f"Selected {len(selected)} videos from {len(videos)} "
        f"({sum(1 for v in videos if v.classification == 'likely-tip')} classified as likely-tip)"
    )
    return selected


def _heuristic_classify(title: str) -> str:
    """Fallback heuristic classification based on keywords."""
    title_lower = title.lower()

    # FNO indicators
    fno_words = ["option", "future", "f&o", "fno", "nifty", "banknifty", "expiry", "call put"]
    if any(w in title_lower for w in fno_words):
        return "fno"

    # Tip indicators
    tip_words = [
        "target",
        "stop loss",
        "buy",
        "sell",
        "multibagger",
        "breakout",
        "stock pick",
        "portfolio",
        "invest",
        "khareed",
        "kharid",
        "entry",
        "exit",
    ]
    if any(w in title_lower for w in tip_words):
        return "likely-tip"

    return "unknown"
