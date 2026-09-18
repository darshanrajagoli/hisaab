"""
Step 11: Price data retrieval.

Fetches historical prices from Google Finance for each unique ticker.
Uses the smallest window that covers all tips for that stock.
One call per ticker+window, plus one for NIFTY 50.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

import pandas as pd

from hisaab.models import ResolvedTip
from hisaab.serp.client import SerpClient

logger = logging.getLogger(__name__)

NIFTY_TICKER = "NIFTY_50:INDEXNSE"


def fetch_prices(
    client: SerpClient,
    tips: list[ResolvedTip],
) -> dict[str, pd.DataFrame]:
    """
    Fetch price series for all unique tickers and NIFTY 50.

    Returns: {ticker_nse: DataFrame with columns [date, close]}
    """
    # Collect unique resolved tickers
    tickers: set[str] = set()
    for tip in tips:
        if tip.resolved and tip.ticker_nse:
            tickers.add(tip.ticker_nse)

    # Always include NIFTY
    tickers.add(NIFTY_TICKER)

    price_data: dict[str, pd.DataFrame] = {}
    for ticker in tickers:
        # Choose window based on how far back tips go
        window = _choose_window(tips, ticker)
        try:
            result = client.search_google_finance(ticker, window=window)
            series = _parse_price_series(result)
            if series is not None and len(series) > 0:
                price_data[ticker] = series
                logger.info(f"Prices: {ticker} → {len(series)} data points ({window})")
            else:
                logger.warning(f"No price data for {ticker}")
        except Exception as e:
            logger.warning(f"Failed to fetch prices for {ticker}: {e}")

    return price_data


def _choose_window(tips: list[ResolvedTip], ticker: str) -> str:
    """Choose the smallest Google Finance window that covers all tips for this ticker."""
    if ticker == NIFTY_TICKER:
        # Cover the full range of all tips
        dates = [t.publish_date for t in tips if t.publish_date]
        if not dates:
            return "1Y"
        oldest = min(dates)
        days_ago = (date.today() - oldest).days
    else:
        relevant = [t for t in tips if t.ticker_nse == ticker and t.publish_date]
        if not relevant:
            return "1Y"
        oldest_date = min(t.publish_date for t in relevant)
        days_ago = (date.today() - oldest_date).days

    if days_ago <= 30:
        return "1M"
    elif days_ago <= 180:
        return "6M"
    elif days_ago <= 365:
        return "1Y"
    else:
        return "5Y"


def _parse_price_series(result: dict) -> Optional[pd.DataFrame]:
    """
    Parse Google Finance response into a date-indexed price DataFrame.

    Handles the graph data structure from the API.
    """
    # Try different response structures
    graph = result.get("graph", [])
    if not graph:
        # Try finance_results or summary
        finance = result.get("finance_results", {})
        graph = finance.get("graph", [])
    if not graph:
        graph = result.get("time_series", [])

    if not graph:
        return None

    records = []
    for point in graph:
        price = point.get("price", point.get("close", point.get("value")))
        date_str = point.get("date", point.get("datetime", ""))

        if price is None or not date_str:
            continue

        try:
            price = float(price)
        except (ValueError, TypeError):
            continue

        try:
            dt = pd.Timestamp(date_str)
            records.append({"date": dt.date(), "close": price})
        except Exception:
            continue

    if not records:
        return None

    df = pd.DataFrame(records)
    df = df.drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)
    return df


MAX_SNAP_DAYS = 10  # weekly bars can legitimately be ~7 days apart


def get_close_on_date(
    series: pd.DataFrame, target_date: date, after: bool = True
) -> Optional[tuple[date, float]]:
    """
    Get the closing price on or after/before a target date.

    Returns: (actual_date, close_price) or None. Snapping is bounded to
    MAX_SNAP_DAYS — an unbounded snap-forward would silently use a much
    later entry price for a ticker whose series starts after target_date
    (a too-narrow fetch window, a new listing, or a demerged/renamed
    entity), scoring the tip as if it entered on a date the stock wasn't
    actually bought at.
    """
    if series is None or series.empty:
        return None

    if after:
        mask = series["date"] >= target_date
    else:
        mask = series["date"] <= target_date

    filtered = series[mask]
    if filtered.empty:
        return None

    if after:
        row = filtered.iloc[0]
    else:
        row = filtered.iloc[-1]

    actual_date = row["date"]
    gap = abs((actual_date - target_date).days)
    if gap > MAX_SNAP_DAYS:
        return None

    return (actual_date, float(row["close"]))


def get_series_between(series: pd.DataFrame, start_date: date, end_date: date) -> pd.DataFrame:
    """Get price series between two dates (inclusive)."""
    if series is None or series.empty:
        return pd.DataFrame(columns=["date", "close"])

    mask = (series["date"] >= start_date) & (series["date"] <= end_date)
    return series[mask].reset_index(drop=True)
