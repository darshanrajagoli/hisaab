"""
Tests for the deterministic scoring engine.

Uses synthetic price series to test every outcome scenario.
These tests prove that the LLM never influences the numbers.
"""

from datetime import date, timedelta

import pandas as pd

from hisaab.models import (
    Direction,
    HorizonBucket,
    InstrumentType,
    ResolvedTip,
    TipOutcome,
    UnscoredReason,
)
from hisaab.pipeline.score import score_tips


def _make_series(base_price: float, daily_returns: list[float], start: date) -> pd.DataFrame:
    """Create a synthetic price series from daily returns."""
    prices = [base_price]
    for r in daily_returns:
        prices.append(prices[-1] * (1 + r))
    dates = [start + timedelta(days=i) for i in range(len(prices))]
    return pd.DataFrame({"date": dates, "close": prices})


def _make_flat_series(price: float, start: date, days: int = 300) -> pd.DataFrame:
    """Create a flat price series (NIFTY benchmark)."""
    dates = [start + timedelta(days=i) for i in range(days)]
    return pd.DataFrame({"date": dates, "close": [price] * days})


def _make_tip(
    publish_date: date,
    direction: Direction = Direction.LONG,
    target: float = None,
    stop_loss: float = None,
    horizon: HorizonBucket = HorizonBucket.POSITIONAL,
    instrument_type: InstrumentType = InstrumentType.EQUITY,
    entry_price: float = None,
) -> ResolvedTip:
    """Create a minimal resolved tip for testing."""
    return ResolvedTip(
        video_id="test_vid",
        start_ms=0,
        end_ms=5000,
        quote_original="test quote",
        quote_english="test quote english",
        company_name_raw="TestCorp",
        direction=direction,
        instrument_type=instrument_type,
        stated_entry_price=entry_price,
        stated_target=target,
        stated_stop_loss=stop_loss,
        horizon_bucket=horizon,
        ticker="TESTCORP",
        ticker_nse="TESTCORP:NSE",
        resolved=True,
        resolution_method="test",
        publish_date=publish_date,
    )


class TestTargetHit:
    """Test that TARGET_HIT is detected when price reaches target before stop."""

    def test_target_hit_long(self):
        pub = date(2024, 1, 1)
        # Price goes from 100 → 120 (target 115 should hit)
        series = _make_series(100, [0.02] * 15 + [0.01] * 50, start=pub)
        nifty = _make_flat_series(20000, pub)

        tip = _make_tip(pub, Direction.LONG, target=115, stop_loss=90)
        scored = score_tips([tip], {"TESTCORP:NSE": series, "NIFTY_50:INDEXNSE": nifty})

        assert len(scored) == 1
        assert scored[0].outcome == TipOutcome.TARGET_HIT
        assert scored[0].is_scored is True

    def test_target_hit_short(self):
        pub = date(2024, 1, 1)
        # Price drops from 100 → 80 (short target 85 should hit)
        series = _make_series(100, [-0.02] * 15 + [-0.01] * 50, start=pub)
        nifty = _make_flat_series(20000, pub)

        tip = _make_tip(pub, Direction.SHORT, target=85, stop_loss=115)
        scored = score_tips([tip], {"TESTCORP:NSE": series, "NIFTY_50:INDEXNSE": nifty})

        assert scored[0].outcome == TipOutcome.TARGET_HIT


class TestStopHit:
    """Test that STOP_HIT is detected when price hits stop before target."""

    def test_stop_hit_long(self):
        pub = date(2024, 1, 1)
        # Price drops from 100 → 80 (stop at 90 should trigger)
        series = _make_series(100, [-0.02] * 15 + [-0.01] * 50, start=pub)
        nifty = _make_flat_series(20000, pub)

        tip = _make_tip(pub, Direction.LONG, target=120, stop_loss=90)
        scored = score_tips([tip], {"TESTCORP:NSE": series, "NIFTY_50:INDEXNSE": nifty})

        assert scored[0].outcome == TipOutcome.STOP_HIT
        assert scored[0].is_scored is True

    def test_stop_hit_short(self):
        pub = date(2024, 1, 1)
        # Price rises from 100 → 120 (short stop at 110 should trigger)
        series = _make_series(100, [0.02] * 15 + [0.01] * 50, start=pub)
        nifty = _make_flat_series(20000, pub)

        tip = _make_tip(pub, Direction.SHORT, target=80, stop_loss=110)
        scored = score_tips([tip], {"TESTCORP:NSE": series, "NIFTY_50:INDEXNSE": nifty})

        assert scored[0].outcome == TipOutcome.STOP_HIT


class TestExpired:
    """Test that EXPIRED is the outcome when neither target nor stop is hit."""

    def test_expired_flat(self):
        pub = date(2024, 1, 1)
        # Price stays flat around 100
        series = _make_flat_series(100, pub)
        nifty = _make_flat_series(20000, pub)

        tip = _make_tip(pub, Direction.LONG, target=150, stop_loss=50)
        scored = score_tips([tip], {"TESTCORP:NSE": series, "NIFTY_50:INDEXNSE": nifty})

        assert scored[0].outcome == TipOutcome.EXPIRED


class TestNotTriggered:
    """Test that NOT_TRIGGERED works when stated entry isn't reached."""

    def test_entry_not_reached(self):
        pub = date(2024, 1, 1)
        # Price starts at 100 but stated entry is 80 (never reached)
        series = _make_series(100, [0.01] * 100, start=pub)
        nifty = _make_flat_series(20000, pub)

        tip = _make_tip(pub, Direction.LONG, target=120, entry_price=80)
        scored = score_tips([tip], {"TESTCORP:NSE": series, "NIFTY_50:INDEXNSE": nifty})

        assert scored[0].outcome == TipOutcome.NOT_TRIGGERED
        assert scored[0].unscored_reason == UnscoredReason.NOT_TRIGGERED


class TestUnscoredCategories:
    """Test that FNO, IPO, etc. are correctly marked as unscored."""

    def test_fno_unscored(self):
        pub = date(2024, 1, 1)
        series = _make_flat_series(100, pub)
        nifty = _make_flat_series(20000, pub)

        tip = _make_tip(pub, instrument_type=InstrumentType.FNO)
        scored = score_tips([tip], {"TESTCORP:NSE": series, "NIFTY_50:INDEXNSE": nifty})

        assert scored[0].is_scored is False
        assert scored[0].unscored_reason == UnscoredReason.FNO

    def test_intraday_unscored(self):
        pub = date(2024, 1, 1)
        series = _make_flat_series(100, pub)
        nifty = _make_flat_series(20000, pub)

        tip = _make_tip(pub, horizon=HorizonBucket.INTRADAY)
        scored = score_tips([tip], {"TESTCORP:NSE": series, "NIFTY_50:INDEXNSE": nifty})

        assert scored[0].is_scored is False
        assert scored[0].unscored_reason == UnscoredReason.INTRADAY

    def test_unresolved_unscored(self):
        pub = date(2024, 1, 1)
        tip = _make_tip(pub)
        tip.resolved = False
        series = _make_flat_series(100, pub)
        nifty = _make_flat_series(20000, pub)

        scored = score_tips([tip], {"TESTCORP:NSE": series, "NIFTY_50:INDEXNSE": nifty})
        assert scored[0].unscored_reason == UnscoredReason.UNRESOLVED_TICKER


class TestExcessReturn:
    """Test excess return calculation."""

    def test_positive_excess(self):
        pub = date(2024, 1, 1)
        # Stock up 20%, NIFTY up 5% → excess = 15%
        stock = _make_series(100, [0.003] * 100, start=pub)
        nifty = _make_series(20000, [0.0007] * 100, start=pub)

        tip = _make_tip(pub, Direction.LONG)
        scored = score_tips([tip], {"TESTCORP:NSE": stock, "NIFTY_50:INDEXNSE": nifty})

        assert scored[0].is_scored is True
        assert scored[0].excess_return is not None
        assert scored[0].excess_return > 0

    def test_short_direction_flips_sign(self):
        pub = date(2024, 1, 1)
        # Stock down 10% → SHORT return should be positive
        stock = _make_series(100, [-0.002] * 100, start=pub)
        nifty = _make_flat_series(20000, pub)

        tip = _make_tip(pub, Direction.SHORT)
        scored = score_tips([tip], {"TESTCORP:NSE": stock, "NIFTY_50:INDEXNSE": nifty})

        assert scored[0].stock_return > 0  # Flipped for SHORT


class TestOpenTip:
    """Test that tips with unelapsed horizon are marked OPEN."""

    def test_open_tip(self):
        # Publish date is very recent → horizon not elapsed
        pub = date.today() - timedelta(days=2)
        series = _make_series(100, [0.01] * 10, start=pub - timedelta(days=5))
        nifty = _make_flat_series(20000, pub - timedelta(days=5))

        tip = _make_tip(pub, Direction.LONG, horizon=HorizonBucket.LONG_TERM)
        scored = score_tips(
            [tip],
            {"TESTCORP:NSE": series, "NIFTY_50:INDEXNSE": nifty},
            today=date.today(),
        )

        assert scored[0].outcome == TipOutcome.OPEN
