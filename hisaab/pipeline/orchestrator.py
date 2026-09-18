"""
Pipeline orchestrator.

Runs the full audit flow: discover → select → metadata → transcripts →
windows → extract → verify → resolve → prices → corporate actions →
score → stats → explain.

Reports progress at each stage for the UI and CLI.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Callable, Optional

from hisaab.models import (
    AuditRun,
    CostEstimate,
    PipelineFunnel,
)
from hisaab.pipeline.corporate_actions import detect_corporate_actions
from hisaab.pipeline.discover import (
    discover_single_video,
    discover_videos,
    parse_channel_input,
)
from hisaab.pipeline.explain import explain_top_tips
from hisaab.pipeline.extract import extract_tips_from_windows
from hisaab.pipeline.metadata import fetch_metadata
from hisaab.pipeline.prices import fetch_prices
from hisaab.pipeline.resolve import TickerResolver, resolve_tips
from hisaab.pipeline.score import score_tips
from hisaab.pipeline.select import select_videos
from hisaab.pipeline.stats import compute_stats
from hisaab.pipeline.transcripts import fetch_all_transcripts
from hisaab.pipeline.verify import merge_duplicates, verify_tips
from hisaab.pipeline.windows import build_windows, filter_windows
from hisaab.serp.client import SerpClient
from hisaab.store import HisaabStore

logger = logging.getLogger(__name__)

# Type for progress callbacks
ProgressCallback = Callable[[str, str, dict[str, Any]], None]


def _noop_progress(stage: str, message: str, data: dict[str, Any]) -> None:
    """Default no-op progress callback."""
    pass


def run_audit(
    user_input: str,
    client: SerpClient,
    store: Optional[HisaabStore] = None,
    max_videos: int = 10,
    use_llm_classify: bool = True,
    use_llm_verify: bool = True,
    explain_news: bool = True,
    progress: ProgressCallback = _noop_progress,
) -> AuditRun:
    """
    Run a complete channel or video audit.

    Args:
        user_input: Channel URL/handle/ID or video URL
        client: Configured SerpClient (live or replay)
        store: Optional persistence store
        max_videos: Max videos to audit per run
        use_llm_classify: Whether to use LLM for title classification
        use_llm_verify: Whether to use LLM for tip verification
        explain_news: Whether to fetch news explanations
        progress: Callback for stage progress updates

    Returns:
        Complete AuditRun with all scored tips and statistics
    """
    run_id = str(uuid.uuid4())[:8]
    started_at = datetime.now()
    funnel = PipelineFunnel()

    progress("init", "Starting audit", {"run_id": run_id})

    # ── Step 1–2: Parse input ──
    parsed = parse_channel_input(user_input)
    progress("parse", f"Input type: {parsed['type']}", parsed)

    # ── Step 3: Discovery ──
    progress("discover", "Discovering videos...", {"engine": "youtube_channel"})

    if parsed["type"] == "video":
        channel, videos = discover_single_video(client, parsed["video_id"])
    else:
        channel, videos = discover_videos(client, parsed)

    funnel.videos_discovered = len(videos)
    progress(
        "discover",
        f"Found {len(videos)} videos from {channel.channel_title}",
        {"count": len(videos)},
    )

    # ── Step 4: Selection ──
    progress("select", "Classifying and selecting videos...", {})
    selected = select_videos(videos, max_videos=max_videos, use_llm=use_llm_classify)
    funnel.videos_selected = len(selected)
    funnel.videos_classified_as_tips = sum(1 for v in videos if v.classification == "likely-tip")
    progress("select", f"Selected {len(selected)} videos", {"count": len(selected)})

    # ── Step 5: Metadata ──
    progress("metadata", "Fetching video metadata...", {"engine": "youtube_video"})
    enriched = fetch_metadata(client, selected)
    progress("metadata", f"Got metadata for {len(enriched)} videos", {})

    # ── Step 6: Transcripts ──
    progress("transcripts", "Fetching transcripts...", {"engine": "youtube_video_transcript"})
    transcripts = fetch_all_transcripts(client, enriched)
    funnel.videos_with_transcripts = len(transcripts)
    progress(
        "transcripts",
        f"Got transcripts for {len(transcripts)}/{len(enriched)} videos",
        {"count": len(transcripts)},
    )

    # ── Step 7: Windowing ──
    progress("windows", "Building transcript windows...", {})
    all_windows = []
    for video_id, snippets in transcripts.items():
        windows = build_windows(video_id, snippets)
        all_windows.extend(windows)

    funnel.windows_total = len(all_windows)
    keyword_windows = filter_windows(all_windows)
    funnel.windows_with_keywords = len(keyword_windows)
    progress(
        "windows",
        f"{len(keyword_windows)} windows with tip keywords (of {len(all_windows)} total)",
        {"total": len(all_windows), "filtered": len(keyword_windows)},
    )

    # ── Step 8: Extraction ──
    progress("extract", "Extracting tips from transcripts...", {"engine": "llm"})
    extracted = extract_tips_from_windows(keyword_windows)
    funnel.tips_extracted = len(extracted)

    # Attach publish dates from video metadata
    video_dates = {v.video_id: v.publish_date for v in enriched if v.publish_date}
    for tip in extracted:
        if tip.video_id in video_dates:
            tip.publish_date = video_dates[tip.video_id]
    progress("extract", f"Extracted {len(extracted)} tips", {"count": len(extracted)})

    # ── Step 9: Verification ──
    progress("verify", "Verifying extracted tips...", {})
    verified = verify_tips(extracted, all_windows, use_llm_verify=use_llm_verify)
    verified = merge_duplicates(verified)
    funnel.tips_verified = len(verified)
    funnel.tips_dropped_verification = funnel.tips_extracted - len(verified)
    progress(
        "verify",
        f"{len(verified)} tips verified ({funnel.tips_dropped_verification} dropped)",
        {"verified": len(verified), "dropped": funnel.tips_dropped_verification},
    )

    # ── Step 10: Resolution ──
    progress("resolve", "Resolving ticker symbols...", {})
    resolver = TickerResolver()
    resolved = resolve_tips(verified, resolver)
    funnel.tips_resolved = sum(1 for t in resolved if t.resolved)
    funnel.tips_dropped_resolution = len(resolved) - funnel.tips_resolved
    progress(
        "resolve",
        f"{funnel.tips_resolved} tickers resolved, {funnel.tips_dropped_resolution} unresolved",
        {},
    )

    # ── Step 11: Prices ──
    progress("prices", "Fetching price data...", {"engine": "google_finance"})
    price_data = fetch_prices(client, resolved)
    progress(
        "prices",
        f"Got prices for {len(price_data)} tickers",
        {"count": len(price_data)},
    )

    # ── Step 12: Corporate actions ──
    progress("corporate_actions", "Checking for corporate actions...", {})
    resolved = detect_corporate_actions(resolved, price_data)

    # ── Step 13: Scoring ──
    progress("score", "Scoring tips against market data...", {})
    scored = score_tips(resolved, price_data)
    funnel.tips_scored = sum(1 for t in scored if t.is_scored)
    funnel.tips_unscored = sum(1 for t in scored if not t.is_scored)
    progress(
        "score",
        f"{funnel.tips_scored} scored, {funnel.tips_unscored} unscored",
        {},
    )

    # ── Step 14: Statistics ──
    progress("stats", "Computing statistics...", {})
    stats = compute_stats(scored, channel.channel_id, channel.channel_title)

    # ── Step 15: Explanations ──
    if explain_news:
        progress("explain", "Fetching news explanations...", {"engine": "google_news"})
        scored = explain_top_tips(client, scored)

    # ── Assemble result ──
    completed_at = datetime.now()
    cost = CostEstimate(
        estimated_calls=client.budget.run_used,
        cached_calls=sum(s.cache_hits for s in client.budget.engine_stats.values()),
        net_new_calls=client.budget.run_used,
        monthly_remaining=client.budget.remaining_monthly(),
        breakdown={name: s.calls for name, s in client.budget.engine_stats.items()},
    )

    run = AuditRun(
        run_id=run_id,
        channel=channel,
        videos=enriched,
        tips=scored,
        stats=stats,
        funnel=funnel,
        cost=cost,
        started_at=started_at,
        completed_at=completed_at,
    )

    # Persist
    if store:
        store.save_run(run)
        progress("store", "Results saved", {})

    progress(
        "complete",
        f"Audit complete: {funnel.tips_scored} scored tips",
        {"run_id": run_id, "duration": (completed_at - started_at).total_seconds()},
    )

    return run
