"""
Hisaab domain models.

Every data structure that flows through the pipeline is defined here.
The LLM reads transcripts; Python judges outcomes. These models enforce that boundary.
"""

from __future__ import annotations

import enum
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field

# ── Enums ────────────────────────────────────────────────────────────────────


class Direction(str, enum.Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    AVOID = "AVOID"
    HOLD = "HOLD"
    WATCHLIST = "WATCHLIST"


class InstrumentType(str, enum.Enum):
    EQUITY = "EQUITY"
    FNO = "FNO"
    IPO = "IPO"
    MF = "MF"
    CRYPTO = "CRYPTO"
    OTHER = "OTHER"


class HorizonBucket(str, enum.Enum):
    INTRADAY = "INTRADAY"
    SWING = "SWING"
    POSITIONAL = "POSITIONAL"
    LONG_TERM = "LONG_TERM"
    UNSPECIFIED = "UNSPECIFIED"


HORIZON_DEFAULTS_TRADING_DAYS: dict[HorizonBucket, int] = {
    HorizonBucket.INTRADAY: 1,
    HorizonBucket.SWING: 10,
    HorizonBucket.POSITIONAL: 60,
    HorizonBucket.LONG_TERM: 250,
    HorizonBucket.UNSPECIFIED: 60,
}


class TipOutcome(str, enum.Enum):
    TARGET_HIT = "TARGET_HIT"
    STOP_HIT = "STOP_HIT"
    EXPIRED = "EXPIRED"
    NOT_TRIGGERED = "NOT_TRIGGERED"
    OPEN = "OPEN"


class UnscoredReason(str, enum.Enum):
    INTRADAY = "INTRADAY"
    FNO = "FNO"
    IPO = "IPO"
    MF = "MF"
    CRYPTO = "CRYPTO"
    UNRESOLVED_TICKER = "UNRESOLVED_TICKER"
    CORPORATE_ACTION = "CORPORATE_ACTION"
    NOT_TRIGGERED = "NOT_TRIGGERED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


CONVICTION_FLAGS = [
    "guaranteed",
    "100 percent",
    "100%",
    "jackpot",
    "multibagger",
    "sure shot",
    "sureshot",
    "double",
    "triple",
    "paisa vasool",
    "rocket",
    "blockbuster",
]


# ── Video & Channel ─────────────────────────────────────────────────────────


class VideoInfo(BaseModel):
    video_id: str
    title: str
    channel_id: str
    channel_title: str = ""
    publish_date: Optional[date] = None
    description: str = ""
    view_count: Optional[int] = None
    classification: str = "unknown"  # likely-tip, commentary, fno, other


class ChannelInfo(BaseModel):
    channel_id: str
    channel_title: str = ""
    handle: str = ""
    subscriber_count: Optional[int] = None


# ── Transcript ───────────────────────────────────────────────────────────────


class TranscriptSnippet(BaseModel):
    text: str
    start_ms: int
    end_ms: int


class TranscriptWindow(BaseModel):
    video_id: str
    window_index: int
    text: str
    start_ms: int
    end_ms: int
    has_tip_keywords: bool = False


# ── Extracted Tip ────────────────────────────────────────────────────────────


class ExtractedTip(BaseModel):
    """A tip as extracted by the LLM from a transcript window."""

    video_id: str
    start_ms: int
    end_ms: int
    publish_date: Optional[date] = None
    quote_original: str = Field(description="Verbatim substring from the transcript window")
    quote_english: str = Field(description="Short English gloss of the quote")
    company_name_raw: str = Field(description="Company name as spoken by the creator")
    direction: Direction
    instrument_type: InstrumentType = InstrumentType.EQUITY
    stated_entry_price: Optional[float] = None
    stated_target: Optional[float] = None
    stated_stop_loss: Optional[float] = None
    stated_horizon_text: Optional[str] = None
    horizon_bucket: HorizonBucket = HorizonBucket.UNSPECIFIED
    conviction_flags: list[str] = Field(default_factory=list)
    extractor_confidence: float = Field(ge=0.0, le=1.0, default=0.5)


# ── Verified & Resolved Tip ─────────────────────────────────────────────────


class VerifiedTip(ExtractedTip):
    """A tip that passed both deterministic and LLM verification."""

    verification_passed: bool = True
    verification_notes: str = ""


class ResolvedTip(VerifiedTip):
    """A verified tip with a resolved NSE ticker symbol."""

    ticker: Optional[str] = None  # e.g. "RELIANCE"
    ticker_nse: Optional[str] = None  # e.g. "RELIANCE:NSE"
    isin: Optional[str] = None
    company_name: str = ""  # official NSE name, e.g. "Reliance Industries Limited"
    resolved: bool = False
    resolution_method: str = ""  # alias, fuzzy, llm, google_finance
    # Set by detect_corporate_actions(), which runs before scoring.
    corporate_action_flag: bool = False
    corporate_action_note: str = ""


# ── Scored Tip ───────────────────────────────────────────────────────────────


class ScoredTip(ResolvedTip):
    """A tip with deterministic scoring against market data."""

    publish_date: Optional[date] = None
    entry_date: Optional[date] = None
    entry_price: Optional[float] = None
    exit_date: Optional[date] = None
    exit_price: Optional[float] = None
    horizon_days: Optional[int] = None
    outcome: Optional[TipOutcome] = None
    stock_return: Optional[float] = None
    nifty_return: Optional[float] = None
    excess_return: Optional[float] = None
    is_scored: bool = False
    unscored_reason: Optional[UnscoredReason] = None
    news_explanation: str = ""
    news_source_url: str = ""


# ── Aggregate Statistics ─────────────────────────────────────────────────────


class ChannelStats(BaseModel):
    """Aggregate statistics for a channel audit."""

    channel_id: str
    channel_title: str = ""
    total_videos_scanned: int = 0
    total_windows_scanned: int = 0
    total_candidates: int = 0
    total_extracted: int = 0
    total_verified: int = 0
    total_resolved: int = 0
    total_scored: int = 0
    total_unscored: int = 0
    unscored_breakdown: dict[str, int] = Field(default_factory=dict)

    # Hit rates
    hit_rate_market: Optional[float] = None  # excess return > 0
    hit_rate_market_ci_low: Optional[float] = None
    hit_rate_market_ci_high: Optional[float] = None
    hit_rate_creator: Optional[float] = None  # TARGET_HIT / (TARGET_HIT + STOP_HIT + EXPIRED)
    hit_rate_creator_ci_low: Optional[float] = None
    hit_rate_creator_ci_high: Optional[float] = None

    # Returns
    mean_excess_return: Optional[float] = None
    median_excess_return: Optional[float] = None
    mean_excess_ci_low: Optional[float] = None
    mean_excess_ci_high: Optional[float] = None

    # Significance
    binomial_p_value: Optional[float] = None
    binomial_verdict: str = ""

    # Conviction analysis
    conviction_hit_rate: Optional[float] = None
    non_conviction_hit_rate: Optional[float] = None
    conviction_count: int = 0

    # Simulation
    simulation_pnl: Optional[float] = None
    simulation_nifty_pnl: Optional[float] = None

    insufficient_evidence: bool = False


# ── Pipeline Funnel ──────────────────────────────────────────────────────────


class PipelineFunnel(BaseModel):
    """Tracks counts at each stage for transparency."""

    videos_discovered: int = 0
    videos_classified_as_tips: int = 0
    videos_selected: int = 0
    videos_with_transcripts: int = 0
    windows_total: int = 0
    windows_with_keywords: int = 0
    tips_extracted: int = 0
    tips_verified: int = 0
    tips_resolved: int = 0
    tips_scored: int = 0
    tips_unscored: int = 0
    tips_dropped_verification: int = 0
    tips_dropped_resolution: int = 0


# ── Cost Estimate ────────────────────────────────────────────────────────────


class CostEstimate(BaseModel):
    """Pre-run cost estimate shown to user."""

    estimated_calls: int = 0
    cached_calls: int = 0
    net_new_calls: int = 0
    monthly_remaining: int = 250
    breakdown: dict[str, int] = Field(default_factory=dict)  # engine -> count


# ── Run Result ───────────────────────────────────────────────────────────────


class AuditRun(BaseModel):
    """Complete result of an audit run."""

    run_id: str
    channel: ChannelInfo
    videos: list[VideoInfo] = Field(default_factory=list)
    tips: list[ScoredTip] = Field(default_factory=list)
    stats: Optional[ChannelStats] = None
    funnel: PipelineFunnel = Field(default_factory=PipelineFunnel)
    cost: CostEstimate = Field(default_factory=CostEstimate)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
