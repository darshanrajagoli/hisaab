"""
Step 14: Aggregate statistics.

Wilson 95% confidence intervals for hit rates.
Bootstrap 95% CI for mean excess return.
Two-sided binomial test against a 50% coin flip.
₹10,000-per-tip simulation.
Conviction analysis.

All computation is deterministic. The LLM never touches these numbers.
"""

from __future__ import annotations

import logging
import math
from typing import Optional

import numpy as np
from scipy import stats as sp_stats

from hisaab.models import ChannelStats, ScoredTip, TipOutcome

logger = logging.getLogger(__name__)

MIN_SCORED_TIPS = 10
BOOTSTRAP_N = 10_000
BOOTSTRAP_SEED = 42
SIM_AMOUNT = 10_000  # ₹10,000 per tip


def compute_stats(
    tips: list[ScoredTip],
    channel_id: str,
    channel_title: str = "",
) -> ChannelStats:
    """Compute all aggregate statistics for a channel."""
    cs = ChannelStats(
        channel_id=channel_id,
        channel_title=channel_title,
    )

    scored = [t for t in tips if t.is_scored]
    unscored = [t for t in tips if not t.is_scored]

    cs.total_scored = len(scored)
    cs.total_unscored = len(unscored)

    # Unscored breakdown. OPEN tips are counted under their own bucket
    # below — counting them again here under a generic "UNKNOWN" would
    # double-count them and make the breakdown not sum to total_unscored.
    for t in unscored:
        if t.outcome == TipOutcome.OPEN:
            continue
        reason = t.unscored_reason.value if t.unscored_reason else "UNKNOWN"
        cs.unscored_breakdown[reason] = cs.unscored_breakdown.get(reason, 0) + 1

    open_tips = [t for t in tips if t.outcome == TipOutcome.OPEN]
    if open_tips:
        cs.unscored_breakdown["OPEN"] = len(open_tips)

    if cs.total_scored < MIN_SCORED_TIPS:
        cs.insufficient_evidence = True
        logger.warning(f"Only {cs.total_scored} scored tips — insufficient evidence")
        # Still compute what we can
        if cs.total_scored == 0:
            return cs

    # ── Hit rate on market terms (excess return > 0) ──

    excess_returns = [t.excess_return for t in scored if t.excess_return is not None]

    if excess_returns:
        wins = sum(1 for r in excess_returns if r > 0)
        n = len(excess_returns)
        cs.hit_rate_market = wins / n
        ci_low, ci_high = wilson_ci(wins, n)
        cs.hit_rate_market_ci_low = ci_low
        cs.hit_rate_market_ci_high = ci_high

        # Mean and median excess return
        cs.mean_excess_return = float(np.mean(excess_returns))
        cs.median_excess_return = float(np.median(excess_returns))

        # Bootstrap CI for mean
        ci_low, ci_high = bootstrap_ci(excess_returns)
        cs.mean_excess_ci_low = ci_low
        cs.mean_excess_ci_high = ci_high

        # Binomial test against 50%
        p_value = binomial_test(wins, n)
        cs.binomial_p_value = p_value
        cs.binomial_verdict = _interpret_p_value(p_value, wins / n)

    # ── Hit rate on creator's terms ──

    with_targets = [
        t
        for t in scored
        if t.outcome in (TipOutcome.TARGET_HIT, TipOutcome.STOP_HIT, TipOutcome.EXPIRED)
        and t.stated_target is not None
    ]
    if with_targets:
        target_hits = sum(1 for t in with_targets if t.outcome == TipOutcome.TARGET_HIT)
        n_targets = len(with_targets)
        cs.hit_rate_creator = target_hits / n_targets
        ci_low, ci_high = wilson_ci(target_hits, n_targets)
        cs.hit_rate_creator_ci_low = ci_low
        cs.hit_rate_creator_ci_high = ci_high

    # ── Conviction analysis ──

    conviction_tips = [t for t in scored if t.conviction_flags and t.excess_return is not None]
    non_conviction_tips = [
        t for t in scored if not t.conviction_flags and t.excess_return is not None
    ]
    cs.conviction_count = len(conviction_tips)

    if conviction_tips:
        conv_wins = sum(1 for t in conviction_tips if t.excess_return > 0)
        cs.conviction_hit_rate = conv_wins / len(conviction_tips)

    if non_conviction_tips:
        non_conv_wins = sum(1 for t in non_conviction_tips if t.excess_return > 0)
        cs.non_conviction_hit_rate = non_conv_wins / len(non_conviction_tips)

    # ── ₹10,000 per tip simulation ──

    sim_result = simulate_portfolio(scored)
    if sim_result:
        cs.simulation_pnl = sim_result["portfolio_pnl"]
        cs.simulation_nifty_pnl = sim_result["nifty_pnl"]

    return cs


def wilson_ci(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """
    Wilson score interval for a proportion.

    More reliable than normal approximation, especially for small n.
    """
    if n == 0:
        return (0.0, 1.0)

    p_hat = successes / n
    z2 = z * z

    denom = 1 + z2 / n
    center = (p_hat + z2 / (2 * n)) / denom
    spread = (z / denom) * math.sqrt(p_hat * (1 - p_hat) / n + z2 / (4 * n * n))

    lower = max(0.0, center - spread)
    upper = min(1.0, center + spread)

    return (lower, upper)


def bootstrap_ci(
    values: list[float],
    n_bootstrap: int = BOOTSTRAP_N,
    seed: int = BOOTSTRAP_SEED,
    alpha: float = 0.05,
) -> tuple[float, float]:
    """Bootstrap 95% confidence interval for the mean."""
    if not values:
        return (0.0, 0.0)

    rng = np.random.RandomState(seed)
    arr = np.array(values)
    means = []

    for _ in range(n_bootstrap):
        sample = rng.choice(arr, size=len(arr), replace=True)
        means.append(float(np.mean(sample)))

    means.sort()
    lower = means[int(n_bootstrap * alpha / 2)]
    upper = means[int(n_bootstrap * (1 - alpha / 2))]

    return (lower, upper)


def binomial_test(successes: int, n: int, p0: float = 0.5) -> float:
    """
    Two-sided binomial test: is the hit rate significantly different from p0
    in either direction (better OR worse than a coin flip)?

    Returns p-value.
    """
    if n == 0:
        return 1.0

    result = sp_stats.binomtest(successes, n, p0, alternative="two-sided")
    return float(result.pvalue)


def _interpret_p_value(p_value: float, hit_rate: float) -> str:
    """Convert p-value to plain English."""
    if p_value < 0.01:
        direction = "better" if hit_rate > 0.5 else "worse"
        return f"Significantly {direction} than a coin flip (p < 0.01)"
    elif p_value < 0.05:
        direction = "better" if hit_rate > 0.5 else "worse"
        return f"Likely {direction} than a coin flip (p < 0.05)"
    else:
        return "Indistinguishable from a coin flip"


def simulate_portfolio(
    tips: list[ScoredTip],
) -> Optional[dict]:
    """
    ₹10,000-per-tip equal-weight simulation.

    Returns cumulative P&L for the portfolio and for NIFTY over the same dates.
    """
    scored = [
        t for t in tips if t.is_scored and t.stock_return is not None and t.nifty_return is not None
    ]
    if not scored:
        return None

    portfolio_pnl = 0.0
    nifty_pnl = 0.0
    timeline = []

    # Sort by exit date, since that's the date plotted per point below —
    # sorting by entry_date instead (as this used to) can produce a
    # non-monotonic x-axis once tips have different horizons, because a
    # later-entered short-horizon tip can exit before an earlier-entered
    # long-horizon one.
    scored_sorted = sorted(scored, key=lambda t: t.exit_date or "")

    for tip in scored_sorted:
        tip_pnl = SIM_AMOUNT * tip.stock_return
        tip_nifty = SIM_AMOUNT * tip.nifty_return
        portfolio_pnl += tip_pnl
        nifty_pnl += tip_nifty
        timeline.append(
            {
                "date": str(tip.exit_date),
                "ticker": tip.ticker,
                "return": tip.stock_return,
                "excess": tip.excess_return,
                "cumulative_pnl": portfolio_pnl,
                "cumulative_nifty": nifty_pnl,
            }
        )

    return {
        "portfolio_pnl": portfolio_pnl,
        "nifty_pnl": nifty_pnl,
        "timeline": timeline,
        "n_tips": len(scored),
        "amount_per_tip": SIM_AMOUNT,
    }
