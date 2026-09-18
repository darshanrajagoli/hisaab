"""
Step 13: Deterministic scoring.

Every number on the scorecard comes from this module — not the LLM.
The method is fully documented and reproducible.

Entry rule: close on the first trading day strictly after publish date.
Horizon rule: stated horizon or bucket default.
Outcome: by creator's terms (target/stop) AND by market terms (excess return).
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

import pandas as pd

from hisaab.models import (
    HORIZON_DEFAULTS_TRADING_DAYS,
    Direction,
    HorizonBucket,
    InstrumentType,
    ResolvedTip,
    ScoredTip,
    TipOutcome,
    UnscoredReason,
)
from hisaab.pipeline.prices import get_close_on_date, get_series_between

logger = logging.getLogger(__name__)

NIFTY_TICKER = "NIFTY_50:INDEXNSE"
ENTRY_TRIGGER_WINDOW = 5  # Trading days to reach stated entry price


def score_tips(
    tips: list[ResolvedTip],
    price_data: dict[str, pd.DataFrame],
    today: Optional[date] = None,
) -> list[ScoredTip]:
    """
    Score all tips deterministically against market data.

    Returns ScoredTip objects with outcomes and returns.
    """
    if today is None:
        today = date.today()

    nifty_series = price_data.get(NIFTY_TICKER)
    scored: list[ScoredTip] = []

    for tip in tips:
        stip = ScoredTip(**tip.model_dump())

        # Check if tip can be scored
        unscored_reason = _check_scorable(tip)
        if unscored_reason:
            stip.is_scored = False
            stip.unscored_reason = unscored_reason
            scored.append(stip)
            continue

        series = price_data.get(tip.ticker_nse)
        if series is None or series.empty:
            stip.is_scored = False
            stip.unscored_reason = UnscoredReason.INSUFFICIENT_DATA
            scored.append(stip)
            continue

        # Get publish date
        pub_date = tip.publish_date
        if pub_date is None:
            stip.is_scored = False
            stip.unscored_reason = UnscoredReason.INSUFFICIENT_DATA
            scored.append(stip)
            continue

        stip.publish_date = pub_date

        # Entry: close on first trading day strictly AFTER publish date
        next_day = pub_date + timedelta(days=1)
        entry_result = get_close_on_date(series, next_day, after=True)
        if entry_result is None:
            stip.is_scored = False
            stip.unscored_reason = UnscoredReason.INSUFFICIENT_DATA
            scored.append(stip)
            continue

        entry_date, entry_price = entry_result
        stip.entry_date = entry_date
        stip.entry_price = entry_price

        # Check if stated entry was triggered
        if tip.stated_entry_price is not None:
            triggered = _check_entry_triggered(
                series, entry_date, tip.stated_entry_price, tip.direction
            )
            if not triggered:
                stip.is_scored = False
                stip.outcome = TipOutcome.NOT_TRIGGERED
                stip.unscored_reason = UnscoredReason.NOT_TRIGGERED
                scored.append(stip)
                continue

        # Calculate horizon
        horizon_days = _get_horizon_days(tip)
        stip.horizon_days = horizon_days

        # Check if horizon has elapsed
        horizon_end = _add_trading_days(entry_date, horizon_days, series)
        if horizon_end > today:
            # Tip is still OPEN — mark to market but don't score
            latest = get_close_on_date(series, today, after=False)
            if latest:
                stip.exit_date = latest[0]
                stip.exit_price = latest[1]
                stip.stock_return = _calc_return(entry_price, latest[1], tip.direction)
                if nifty_series is not None:
                    nifty_ret = _calc_nifty_return(nifty_series, entry_date, latest[0])
                    stip.nifty_return = nifty_ret
                    if stip.stock_return is not None and nifty_ret is not None:
                        stip.excess_return = stip.stock_return - nifty_ret

            stip.outcome = TipOutcome.OPEN
            stip.is_scored = False
            stip.unscored_reason = None  # OPEN tips shown but not in aggregates
            scored.append(stip)
            continue

        # Score by creator's terms (target/stop)
        outcome, exit_date, exit_price = _score_creator_terms(
            series, entry_date, entry_price, horizon_end, tip
        )
        stip.outcome = outcome
        stip.exit_date = exit_date
        stip.exit_price = exit_price

        # Calculate returns
        if exit_price is not None:
            stip.stock_return = _calc_return(entry_price, exit_price, tip.direction)

            if nifty_series is not None:
                nifty_ret = _calc_nifty_return(nifty_series, entry_date, exit_date)
                stip.nifty_return = nifty_ret
                if stip.stock_return is not None and nifty_ret is not None:
                    stip.excess_return = stip.stock_return - nifty_ret

        # Handle corporate action flags
        if stip.corporate_action_flag:
            stip.is_scored = False
            stip.unscored_reason = UnscoredReason.CORPORATE_ACTION
        else:
            stip.is_scored = True

        scored.append(stip)

    scored_count = sum(1 for s in scored if s.is_scored)
    logger.info(
        f"Scoring: {scored_count} scored, "
        f"{len(scored) - scored_count} unscored out of {len(scored)} total"
    )
    return scored


def _check_scorable(tip: ResolvedTip) -> Optional[UnscoredReason]:
    """Check if a tip can be scored at all."""
    if tip.instrument_type == InstrumentType.FNO:
        return UnscoredReason.FNO
    if tip.instrument_type == InstrumentType.IPO:
        return UnscoredReason.IPO
    if tip.instrument_type == InstrumentType.MF:
        return UnscoredReason.MF
    if tip.instrument_type == InstrumentType.CRYPTO:
        return UnscoredReason.CRYPTO
    if tip.horizon_bucket == HorizonBucket.INTRADAY:
        return UnscoredReason.INTRADAY
    if not tip.resolved:
        return UnscoredReason.UNRESOLVED_TICKER
    return None


def _get_horizon_days(tip: ResolvedTip) -> int:
    """Get the horizon in trading days from stated or bucket default."""
    return HORIZON_DEFAULTS_TRADING_DAYS.get(tip.horizon_bucket, 60)


def _add_trading_days(start: date, trading_days: int, series: pd.DataFrame) -> date:
    """
    Add N trading days to a start date using the price series as the calendar.
    Falls back to calendar days × 1.5 if series doesn't extend far enough.
    """
    future = series[series["date"] > start].sort_values("date")
    if len(future) >= trading_days:
        return future.iloc[trading_days - 1]["date"]
    # Fallback: approximate with calendar days
    return start + timedelta(days=int(trading_days * 1.5))


def _check_entry_triggered(
    series: pd.DataFrame,
    entry_date: date,
    stated_entry: float,
    direction: Direction,
) -> bool:
    """
    Check if the stated entry price was reached within ENTRY_TRIGGER_WINDOW trading days.

    For LONG: price must have been ≤ stated_entry (buyer could get in)
    For SHORT/AVOID: price must have been ≥ stated_entry
    """
    window = series[series["date"] >= entry_date].head(ENTRY_TRIGGER_WINDOW)
    if window.empty:
        return False

    if direction in (Direction.LONG, Direction.HOLD, Direction.WATCHLIST):
        return float(window["close"].min()) <= stated_entry * 1.02  # 2% tolerance
    else:
        return float(window["close"].max()) >= stated_entry * 0.98


def _score_creator_terms(
    series: pd.DataFrame,
    entry_date: date,
    entry_price: float,
    horizon_end: date,
    tip: ResolvedTip,
) -> tuple[TipOutcome, date, float]:
    """
    Walk the close series from entry to horizon.
    Check if target or stop was hit first.
    """
    window = get_series_between(series, entry_date, horizon_end)
    if window.empty:
        return TipOutcome.EXPIRED, horizon_end, entry_price

    has_target = tip.stated_target is not None
    has_stop = tip.stated_stop_loss is not None

    # If no target or stop, score by excess return at horizon
    if not has_target and not has_stop:
        last_row = window.iloc[-1]
        return TipOutcome.EXPIRED, last_row["date"], float(last_row["close"])

    # Walk the series day by day
    for _, row in window.iterrows():
        close = float(row["close"])
        dt = row["date"]

        if tip.direction in (Direction.LONG, Direction.HOLD, Direction.WATCHLIST):
            if has_target and close >= tip.stated_target:
                return TipOutcome.TARGET_HIT, dt, close
            if has_stop and close <= tip.stated_stop_loss:
                return TipOutcome.STOP_HIT, dt, close
        elif tip.direction in (Direction.SHORT, Direction.AVOID):
            if has_target and close <= tip.stated_target:
                return TipOutcome.TARGET_HIT, dt, close
            if has_stop and close >= tip.stated_stop_loss:
                return TipOutcome.STOP_HIT, dt, close

    # Neither hit — expired
    last_row = window.iloc[-1]
    return TipOutcome.EXPIRED, last_row["date"], float(last_row["close"])


def _calc_return(entry_price: float, exit_price: float, direction: Direction) -> Optional[float]:
    """Calculate return, flipping sign for SHORT/AVOID."""
    if entry_price == 0:
        return None
    raw = (exit_price - entry_price) / entry_price
    if direction in (Direction.SHORT, Direction.AVOID):
        raw = -raw
    return raw


def _calc_nifty_return(
    nifty_series: pd.DataFrame, entry_date: date, exit_date: date
) -> Optional[float]:
    """Calculate NIFTY return over the same period."""
    entry = get_close_on_date(nifty_series, entry_date, after=True)
    exit_ = get_close_on_date(nifty_series, exit_date, after=False)
    if entry is None or exit_ is None or entry[1] == 0:
        return None
    return (exit_[1] - entry[1]) / entry[1]
