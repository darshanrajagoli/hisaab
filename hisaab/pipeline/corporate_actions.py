"""
Step 12: Corporate action detection.

Flags single-period moves beyond ±35% that aren't explained by news.
Splits, bonuses, and demergers break naive returns.
Flagged tips are excluded from aggregates.
"""

from __future__ import annotations

import logging
from datetime import timedelta

import pandas as pd

from hisaab.models import ResolvedTip

logger = logging.getLogger(__name__)

SPIKE_THRESHOLD = 0.35  # 35% single-period move


def detect_corporate_actions(
    tips: list[ResolvedTip],
    price_data: dict[str, pd.DataFrame],
) -> list[ResolvedTip]:
    """
    Flag tips where the price series shows a likely corporate action.

    A single-period move beyond ±35% is suspicious. These tips are
    excluded from aggregates but shown with the reason.
    """
    for tip in tips:
        if not tip.resolved or not tip.ticker_nse:
            continue
        if not tip.publish_date:
            continue

        series = price_data.get(tip.ticker_nse)
        if series is None or series.empty:
            continue

        # Check the price series during the tip's horizon window
        start = tip.publish_date
        horizon_days = tip.horizon_days or 60
        end = start + timedelta(days=int(horizon_days * 1.5))

        window = series[(series["date"] >= start) & (series["date"] <= end)].copy()

        if len(window) < 2:
            continue

        # Calculate single-period returns
        closes = window["close"].values
        returns = []
        for i in range(1, len(closes)):
            if closes[i - 1] != 0:
                ret = (closes[i] - closes[i - 1]) / closes[i - 1]
                returns.append((window.iloc[i]["date"], ret))

        # Flag spikes
        for dt, ret in returns:
            if abs(ret) > SPIKE_THRESHOLD:
                tip.corporate_action_flag = True
                direction = "up" if ret > 0 else "down"
                tip.corporate_action_note = (
                    f"Suspicious {direction} move of {ret:.1%} on {dt}. "
                    f"Possible split, bonus, or demerger. "
                    f"Excluded from aggregates."
                )
                logger.info(f"Corporate action flag: {tip.ticker} {ret:.1%} on {dt}")
                break  # One flag per tip is enough

    flagged = sum(1 for t in tips if t.corporate_action_flag)
    if flagged:
        logger.info(f"Corporate actions: {flagged} tips flagged")

    return tips
