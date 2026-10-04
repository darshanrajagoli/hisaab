"""
Step 4: Video selection.

Classify titles to find likely-tip videos, then take the top N within the
run budget — preferring videos old enough for their calls to be graded.
"""

from __future__ import annotations

import logging
import re

from hisaab import clock
from hisaab.llm import ReplayFixtureMissing, classify_video_titles
from hisaab.models import VideoInfo

logger = logging.getLogger(__name__)

# A positional call (the default horizon) needs 60 trading days, about 90
# calendar days, before it can be graded. Auditing a two-week-old video
# mostly yields OPEN tips, so with a fixed video budget, older videos first.
MIN_GRADEABLE_AGE_DAYS = 90

# "Top 5 Solar Stocks", "4 PSU Stocks", "2 Stocks to BUY NOW" — a list video
# costs the same two SerpApi calls as a one-stock Short but carries several
# calls to grade. Not "₹10 Penny Stock" (a price) or "Target 2500".
_MULTI_PICK_RE = re.compile(
    r"(?<![₹$\d.,])\b([2-9]|1[0-9])\s+(?:[\w&-]+\s+){0,4}?(?:stocks|shares|picks|companies)\b",
    re.IGNORECASE,
)


def select_videos(
    videos: list[VideoInfo],
    max_videos: int = 10,
    use_llm: bool = True,
) -> list[VideoInfo]:
    """
    Select videos to audit.

    1. Classify titles (LLM or heuristic)
    2. Filter to likely-tip videos
    3. Prefer videos at least MIN_GRADEABLE_AGE_DAYS old, then multi-stock
       list videos (otherwise keeping discovery order), and return the first N
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
        except ReplayFixtureMissing:
            raise
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

    today = clock.today()

    def too_recent(v: VideoInfo) -> bool:
        return v.publish_date is None or (today - v.publish_date).days < MIN_GRADEABLE_AGE_DAYS

    # Stable sort: likely-tip still ranks ahead of unknowns, gradeable videos
    # ahead of too-recent ones within each group, then list videos first.
    unique.sort(
        key=lambda v: (
            v.classification != "likely-tip",
            too_recent(v),
            not _MULTI_PICK_RE.search(v.title),
        )
    )

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
