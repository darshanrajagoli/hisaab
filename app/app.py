"""
Hisaab — Streamlit UI

Five screens (the sidebar radio below is the source of truth):
1. Home: input + budget panel + live run progress
2. Scorecard: headline numbers + charts
3. Tip detail: embedded video + price chart
4. Compare: side-by-side channels
5. Methodology: scoring rules
"""

import os
import sys
from pathlib import Path

import streamlit as st

# Ensure the project root is in path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

# On Streamlit Community Cloud, API keys are configured as "Secrets" in the
# app dashboard (st.secrets), not as a .env file — they don't land in
# os.environ automatically, but everything downstream (SerpClient, llm.py)
# reads via os.getenv. Bridge the two. Wrapped in try/except: st.secrets
# raises if no secrets.toml exists at all, which is the normal case for a
# local run using .env instead.
try:
    for _key, _val in st.secrets.items():
        os.environ.setdefault(_key, str(_val))
except Exception:
    pass

st.set_page_config(
    page_title="Hisaab — Finfluencer Scorecard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.sidebar.title("📊 Hisaab")
st.sidebar.caption("_hisaab keeps the receipts_")
st.sidebar.info(
    "⚠️ Educational only — not investment advice. Grades what a creator "
    "said against what happened; doesn't imply intent or track record "
    "beyond the videos this tool actually sampled.",
    icon="⚠️",
)

page = st.sidebar.radio(
    "Navigate",
    ["🏠 Home", "📊 Scorecard", "🔍 Tip Detail", "⚖️ Compare", "📐 Methodology"],
    index=0,
)

if page == "🏠 Home":
    st.title("Hisaab — Grade Finfluencer Stock Tips")
    st.markdown(
        """
        Every stock tip on YouTube is a timestamped prediction.
        **Hisaab** finds each tip, records the exact second it was said,
        and grades it against what the stock actually did afterwards.

        > _Indian finfluencers make thousands of stock calls. Nobody grades them. Until now._
        """
    )

    st.divider()

    col1, col2 = st.columns([2, 1])

    with col1:
        user_input = st.text_input(
            "YouTube Channel or Video URL",
            placeholder="@channel_handle or https://youtube.com/watch?v=...",
            help="Paste a channel URL, handle, channel ID, or video URL",
        )

        col_a, col_b = st.columns(2)
        with col_a:
            max_videos = st.slider("Max videos to audit", 3, 20, 10)
        with col_b:
            mode = st.radio("Mode", ["Live", "Replay (demo)"], horizontal=True)

    with col2:
        st.markdown("### 💰 API Budget")
        from hisaab.serp.client import SerpClient

        # SerpClient restores actual usage-to-date from the cache DB on
        # construction — a bare BudgetGovernor() always shows the full cap
        # regardless of real usage, which is a dashboard that lies.
        try:
            _budget_client = SerpClient(mode="replay")
            budget = _budget_client.budget
            st.metric("Monthly Remaining", f"{budget.remaining_monthly()}")
            st.metric("Run Cap", f"{budget.run_cap}")
        except Exception:
            st.caption("Budget unavailable (no cache DB yet)")
        st.caption("Cached searches are free")

    st.divider()

    if st.button("🚀 Run Audit", type="primary", disabled=not user_input):
        run_mode = "replay" if "Replay" in mode else "live"
        # llm.py reads this env var globally, and a Streamlit process stays
        # alive across reruns — leaving it set to "replay" after a replay
        # run would permanently break a later Live run in the same session
        # until the process restarts. Always set it explicitly either way.
        os.environ["HISAAB_MODE"] = run_mode

        try:
            client = SerpClient(mode=run_mode)
        except ValueError as e:
            st.error(f"Configuration error: {e}")
            st.stop()

        from hisaab.pipeline.orchestrator import run_audit
        from hisaab.store import HisaabStore

        store = HisaabStore()

        # Progress display
        progress_container = st.container()
        status = st.status("Running audit...", expanded=True)

        def streamlit_progress(stage, message, data):
            engine = data.get("engine", "")
            badge = f" `{engine}`" if engine else ""
            status.update(label=message)
            status.write(f"**{stage}**: {message}{badge}")

        try:
            run = run_audit(
                user_input=user_input,
                client=client,
                store=store,
                max_videos=max_videos,
                progress=streamlit_progress,
            )
            status.update(label="✅ Audit complete!", state="complete")
            st.session_state["latest_run"] = run
            st.session_state["latest_channel_id"] = run.channel.channel_id
            st.success(
                f"Audit complete! {run.funnel.tips_scored} tips scored. "
                f"Go to 📊 Scorecard to see results."
            )

            # Budget summary
            summary = client.budget.summary()
            st.info(
                f"API calls: {summary['run_used']} this run | "
                f"{summary['monthly_remaining']} remaining this month"
            )
        except Exception as e:
            status.update(label="❌ Error", state="error")
            from hisaab.llm import ReplayFixtureMissing

            if isinstance(e, ReplayFixtureMissing):
                st.error(
                    "Replay mode stopped: no cached LLM response for this input. "
                    "The bundled fixtures only cover the SerpApi side (YouTube/"
                    "Finance/News) — an LLM (Gemini) response cache isn't shipped "
                    "yet. Switch Mode to Live and provide GEMINI_API_KEY/"
                    "SERPAPI_API_KEY in .env to run this for real."
                )
            else:
                st.error(f"Audit failed: {e}")
                with st.expander("Full error details"):
                    st.exception(e)

elif page == "📊 Scorecard":
    st.title("📊 Scorecard")

    run = st.session_state.get("latest_run")
    if not run:
        # Try loading from store
        from hisaab.store import HisaabStore
        store = HisaabStore()
        channels = store.list_channels()
        if channels:
            selected = st.selectbox(
                "Select channel",
                [c["channel_title"] for c in channels],
            )
            ch = next(c for c in channels if c["channel_title"] == selected)
            run = store.get_latest_run(ch["channel_id"])
            if run:
                st.session_state["latest_run"] = run

    if not run:
        st.info("No audit data. Run an audit from the Home page first.")
        st.stop()

    stats = run.stats
    if not stats:
        st.warning("No statistics available.")
        st.stop()

    # Channel header
    st.header(run.channel.channel_title)

    # Insufficient evidence warning
    if stats.insufficient_evidence:
        st.warning(
            f"⚠️ Only {stats.total_scored} scored tips. "
            f"Need ≥10 for reliable statistical analysis."
        )

    # Headline metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Scored Tips", stats.total_scored)
    with col2:
        if stats.hit_rate_market is not None:
            ci_help = (
                f"95% CI: [{stats.hit_rate_market_ci_low:.1%}, "
                f"{stats.hit_rate_market_ci_high:.1%}]"
            )
            st.metric("Hit Rate (vs NIFTY)", f"{stats.hit_rate_market:.1%}", help=ci_help)
    with col3:
        if stats.mean_excess_return is not None:
            st.metric(
                "Mean Excess Return",
                f"{stats.mean_excess_return:+.2%}",
                help=f"95% CI: [{stats.mean_excess_ci_low:+.2%}, {stats.mean_excess_ci_high:+.2%}]",
            )
    with col4:
        if stats.binomial_verdict:
            short = (
                stats.binomial_verdict
                if len(stats.binomial_verdict) <= 30
                else stats.binomial_verdict[:27] + "..."
            )
            st.metric("Statistical Verdict", short, help=stats.binomial_verdict)

    st.divider()

    # Conviction analysis — promoted above the P&L chart: "do 'guaranteed
    # multibagger' calls actually perform worse than ordinary ones?" is
    # one of the most novel, quotable findings this tool can produce.
    if stats.conviction_count > 0:
        st.subheader("🎯 Conviction Analysis — do bold claims hold up?")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Conviction Calls", stats.conviction_count)
        with col2:
            if stats.conviction_hit_rate is not None:
                st.metric("Conviction Hit Rate", f"{stats.conviction_hit_rate:.1%}")
        with col3:
            if stats.non_conviction_hit_rate is not None:
                st.metric("Regular Hit Rate", f"{stats.non_conviction_hit_rate:.1%}")
        st.divider()

    # Simulation chart
    if stats.simulation_pnl is not None:
        from hisaab.pipeline.stats import simulate_portfolio

        scored_tips = [t for t in run.tips if t.is_scored]
        sim = simulate_portfolio(scored_tips)
        if sim and sim["timeline"]:
            import plotly.graph_objects as go

            fig = go.Figure()
            dates = [t["date"] for t in sim["timeline"]]
            fig.add_trace(go.Scatter(
                x=dates,
                y=[t["cumulative_pnl"] for t in sim["timeline"]],
                name="Portfolio (₹10K/tip)",
                line=dict(color="#2196F3", width=2),
            ))
            fig.add_trace(go.Scatter(
                x=dates,
                y=[t["cumulative_nifty"] for t in sim["timeline"]],
                name="NIFTY 50 (same dates)",
                line=dict(color="#FF9800", width=2, dash="dash"),
            ))
            fig.update_layout(
                title="₹10,000 Per Tip: Portfolio vs NIFTY 50",
                yaxis_title="Cumulative P&L (₹)",
                hovermode="x unified",
                template="plotly_white",
            )
            st.plotly_chart(fig, use_container_width=True)

    # Tips table
    st.subheader("All Tips")
    import pandas as pd


    scored = [t for t in run.tips if t.is_scored]
    if scored:
        rows = []
        for tip in sorted(scored, key=lambda t: t.entry_date or ""):
            quote = tip.quote_english
            quote_display = quote[:60] + "..." if len(quote) > 60 else quote
            rows.append({
                "Date": str(tip.entry_date) if tip.entry_date else "—",
                "Stock": tip.ticker or tip.company_name_raw,
                "Direction": tip.direction.value,
                "Quote": quote_display,
                "Target": f"₹{tip.stated_target:,.0f}" if tip.stated_target else "—",
                "Stop Loss": f"₹{tip.stated_stop_loss:,.0f}" if tip.stated_stop_loss else "—",
                "Outcome": tip.outcome.value if tip.outcome else "—",
                "Return": f"{tip.stock_return:+.1%}" if tip.stock_return is not None else "—",
                "vs NIFTY": f"{tip.excess_return:+.1%}" if tip.excess_return is not None else "—",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True)

    # Unscored breakdown
    if stats.unscored_breakdown:
        st.subheader("Unscored Tips")
        for reason, count in sorted(stats.unscored_breakdown.items()):
            st.text(f"  {reason}: {count}")

    # Funnel
    with st.expander("Pipeline Funnel"):
        f = run.funnel
        st.text(f"Videos discovered: {f.videos_discovered}")
        st.text(f"Videos selected: {f.videos_selected}")
        st.text(f"Transcripts obtained: {f.videos_with_transcripts}")
        st.text(f"Windows scanned: {f.windows_total}")
        st.text(f"Windows with keywords: {f.windows_with_keywords}")
        st.text(f"Tips extracted: {f.tips_extracted}")
        st.text(f"Tips verified: {f.tips_verified}")
        st.text(f"Tips resolved: {f.tips_resolved}")
        st.text(f"Tips scored: {f.tips_scored}")

elif page == "🔍 Tip Detail":
    st.title("🔍 Tip Detail")

    run = st.session_state.get("latest_run")
    if not run:
        # Same store fallback as Scorecard — without this, Tip Detail dead-
        # ends on a fresh session even when past runs are on disk, unless
        # the user happens to visit Scorecard first (whose fallback is what
        # actually populates session_state as a side effect).
        from hisaab.store import HisaabStore
        store = HisaabStore()
        channels = store.list_channels()
        if channels:
            selected = st.selectbox(
                "Select channel", [c["channel_title"] for c in channels], key="tip_detail_channel"
            )
            ch = next(c for c in channels if c["channel_title"] == selected)
            run = store.get_latest_run(ch["channel_id"])
            if run:
                st.session_state["latest_run"] = run

    if not run or not run.tips:
        st.info("No tips to display. Run an audit first.")
        st.stop()

    scored_tips = [t for t in run.tips if t.is_scored]
    if not scored_tips:
        st.info("No scored tips.")
        st.stop()

    # Tip selector
    tip_labels = [
        f"{t.ticker or t.company_name_raw} — {t.direction.value} — "
        f"{t.outcome.value if t.outcome else '?'}"
        for t in scored_tips
    ]
    selected_idx = st.selectbox(
        "Select tip", range(len(tip_labels)), format_func=lambda i: tip_labels[i]
    )
    tip = scored_tips[selected_idx]

    col1, col2 = st.columns([1, 1])

    with col1:
        # Embedded YouTube player at exact timestamp. video_id is
        # interpolated into raw HTML below (unsafe_allow_html) — validate
        # it looks like a real YouTube ID first rather than trusting
        # whatever ended up in storage (it ultimately traces back to a
        # regex extraction off a user-pasted URL in discover.py).
        import re as _re

        start_seconds = tip.start_ms // 1000
        if _re.fullmatch(r"[A-Za-z0-9_-]{11}", tip.video_id or ""):
            yt_url = (
                f"https://www.youtube.com/embed/{tip.video_id}?start={start_seconds}&autoplay=0"
            )
            st.markdown(
                f'<iframe width="100%" height="315" src="{yt_url}" '
                'frameborder="0" allowfullscreen></iframe>',
                unsafe_allow_html=True,
            )
            st.caption(f"Jump to {start_seconds // 60}:{start_seconds % 60:02d}")
        else:
            st.warning(f"Invalid video ID, can't embed player: {tip.video_id!r}")

        # Quote
        st.markdown(f"**Original:** _{tip.quote_original}_")
        st.markdown(f"**English:** {tip.quote_english}")
        if tip.verification_notes:
            st.caption(f"⚠ {tip.verification_notes}")

    with col2:
        # Outcome badge
        outcome_colors = {
            "TARGET_HIT": "🟢", "STOP_HIT": "🔴", "EXPIRED": "🟡", "OPEN": "⚪",
        }
        badge = outcome_colors.get(tip.outcome.value if tip.outcome else "", "⚪")
        st.markdown(f"### {badge} {tip.outcome.value if tip.outcome else 'Unknown'}")

        # Metrics
        mc1, mc2, mc3 = st.columns(3)
        with mc1:
            st.metric("Entry", f"₹{tip.entry_price:,.0f}" if tip.entry_price else "—")
        with mc2:
            st.metric("Exit", f"₹{tip.exit_price:,.0f}" if tip.exit_price else "—")
        with mc3:
            excess_str = f"{tip.excess_return:+.1%}" if tip.excess_return is not None else "—"
            st.metric("Excess Return", excess_str)

        # Price chart — the actual daily close path, not just entry/exit dots.
        # Uses the SAME window-selection logic as the audit itself
        # (prices._choose_window) so this hits the audit's own cache entry
        # instead of silently issuing a fresh live call with a hardcoded
        # window that misses for any tip older than ~6 months.
        if tip.entry_price and tip.exit_price and tip.ticker:
            import plotly.graph_objects as go

            from hisaab.pipeline.prices import _choose_window, _parse_price_series
            from hisaab.serp.client import SerpClient

            series = None
            try:
                chart_window = _choose_window([tip], f"{tip.ticker}:NSE")
                price_client = SerpClient(mode=os.environ.get("HISAAB_MODE", "live"))
                result = price_client.search_google_finance(
                    f"{tip.ticker}:NSE", window=chart_window
                )
                series = _parse_price_series(result)
            except Exception:
                series = None

            fig = go.Figure()

            if series is not None and not series.empty and tip.entry_date and tip.exit_date:
                window = series[
                    (series["date"] >= tip.entry_date) & (series["date"] <= tip.exit_date)
                ]
                if not window.empty:
                    fig.add_trace(
                        go.Scatter(
                            x=window["date"],
                            y=window["close"],
                            mode="lines",
                            name=f"{tip.ticker} close",
                            line=dict(color="#2196F3", width=2),
                        )
                    )
                else:
                    series = None  # fall through to the 2-point fallback below

            if series is None or series.empty:
                # Fallback: at least show the entry → exit move.
                dates = [str(tip.entry_date), str(tip.exit_date)]
                prices = [tip.entry_price, tip.exit_price]
                fig.add_trace(go.Scatter(x=dates, y=prices, mode="lines+markers", name="Price"))

            # Entry/exit markers
            fig.add_trace(
                go.Scatter(
                    x=[tip.entry_date, tip.exit_date],
                    y=[tip.entry_price, tip.exit_price],
                    mode="markers+text",
                    text=["Entry", "Exit"],
                    textposition="top center",
                    marker=dict(size=10, color=["#4CAF50", "#F44336"]),
                    name="Entry/Exit",
                    showlegend=False,
                )
            )

            # Target line
            if tip.stated_target:
                fig.add_hline(
                    y=tip.stated_target, line_dash="dash", line_color="green",
                    annotation_text=f"Target: ₹{tip.stated_target:,.0f}",
                )
            # Stop loss line
            if tip.stated_stop_loss:
                fig.add_hline(
                    y=tip.stated_stop_loss, line_dash="dash", line_color="red",
                    annotation_text=f"SL: ₹{tip.stated_stop_loss:,.0f}",
                )

            fig.update_layout(
                title=f"{tip.ticker}: {tip.direction.value} — {tip.entry_date} to {tip.exit_date}",
                yaxis_title="Price (₹)",
                template="plotly_white",
                height=350,
            )
            st.plotly_chart(fig, use_container_width=True)

        # News explanation
        if tip.news_explanation:
            st.markdown("**Why?**")
            st.markdown(f"_{tip.news_explanation}_")
            if tip.news_source_url:
                st.markdown(f"[Source]({tip.news_source_url})")

        # Conviction / disclosure flags
        flags = set(tip.conviction_flags)
        hedge_flags = flags & {"DISCLAIMED", "PERSONAL_POSITION"}
        conviction_only = flags - hedge_flags
        if "DISCLAIMED" in flags:
            st.info(
                "🛡️ The creator hedged this call in the same breath "
                "(e.g. \"not a recommendation, do your own research\")."
            )
        if "PERSONAL_POSITION" in flags:
            st.info("👤 Disclosed as the creator's own position, not direct advice to viewers.")
        if conviction_only:
            st.warning(f"Conviction claims: {', '.join(sorted(conviction_only))}")

elif page == "⚖️ Compare":
    st.title("⚖️ Compare Channels")

    from hisaab.store import HisaabStore

    store = HisaabStore()
    channels = store.list_channels()

    if len(channels) < 2:
        st.info("Need at least 2 audited channels to compare. Run more audits first.")
        st.stop()

    selected = st.multiselect(
        "Select channels to compare",
        [c["channel_title"] for c in channels],
        max_selections=3,
    )

    if len(selected) >= 2:
        cols = st.columns(len(selected))
        for i, name in enumerate(selected):
            ch = next(c for c in channels if c["channel_title"] == name)
            run = store.get_latest_run(ch["channel_id"])
            if not run or not run.stats:
                continue

            stats = run.stats
            with cols[i]:
                st.subheader(name)
                st.metric("Scored Tips", stats.total_scored)
                if stats.hit_rate_market is not None:
                    st.metric("Hit Rate", f"{stats.hit_rate_market:.1%}")
                if stats.mean_excess_return is not None:
                    st.metric("Excess Return", f"{stats.mean_excess_return:+.2%}")
                st.text(stats.binomial_verdict or "—")

elif page == "📐 Methodology":
    st.title("📐 Methodology")
    st.markdown("""
    ## How Hisaab Scores Stock Tips

    Every number on this scorecard is computed by deterministic Python code, not an LLM.
    The LLM's only job is reading transcripts and extracting structured data.

    ### Entry Rule
    The entry price is the closing price on the **first trading day strictly after** the
    video's publish date. This avoids using information the viewer couldn't have had at
    publish time.

    If the creator stated a specific entry price, the tip only counts as "triggered" if
    the close reaches within 2% of that entry within 5 trading days — but the entry
    price used for scoring is still the day-1 close, not the stated price; the stated
    price is only a trigger gate. Otherwise it's marked NOT_TRIGGERED.

    ### Horizon Rule
    The LLM extracts the creator's stated timeframe as text for display, but scoring
    always uses the fixed bucket default (a free-text "3 months" isn't parsed into a
    day count):
      - SWING: 10 trading days
      - POSITIONAL: 60 trading days
      - LONG_TERM: 250 trading days
      - UNSPECIFIED: 60 trading days

    ### Outcome (Creator's Terms)
    For tips with stated targets and/or stop losses, the close series is walked day by day:
    - **TARGET_HIT**: Target price reached before stop loss
    - **STOP_HIT**: Stop loss reached before target
    - **EXPIRED**: Neither reached by horizon end

    Only closing prices are used — intraday touches are not counted.

    ### Outcome (Market Terms)
    - **Stock Return**: (exit - entry) / entry (sign flipped for SHORT/AVOID)
    - **NIFTY Return**: NIFTY 50 return over identical dates
    - **Excess Return**: Stock Return − NIFTY Return

    ### Unscored Categories
    These are counted and shown but excluded from aggregates:
    - INTRADAY (daily data can't grade them)
    - F&O (strike and expiry make it out of scope)
    - IPO, Mutual Fund, Crypto
    - Unresolved tickers
    - Corporate action flags (>35% move in a single price-series period —
      a trading day on short windows, a full week on the 5Y window)
    - Not triggered (stated entry never reached)
    - OPEN (horizon not yet elapsed)

    ### Statistical Tests
    - **Hit Rate CI**: Wilson 95% confidence interval
    - **Excess Return CI**: Bootstrap 95% CI (10,000 resamples, fixed seed)
    - **Binomial Test**: Two-sided test against a 50% coin flip

    ### Limitations
    - Only closing prices available (not intraday)
    - Auto-generated transcripts may have errors
    - F&O calls are out of scope (need strike/expiry data)
    - Entry timing assumes next-day close (viewer may enter differently)
    - HOLD/WATCHLIST calls are scored as full long positions in the P&L simulation
    - The >35% move exclusion filters split/bonus noise but also drops genuine
      crashes, biasing aggregates slightly in the creator's favor
    - The ticker list only covers currently-listed companies — tips on since-
      delisted stocks (often the worst outcomes) can never be scored
    - Video selection uses SerpApi's in-channel search ranking, which skews
      toward whatever the creator's own audience engaged with most
    - A video with a transcript covering only its first minute still counts
      as "audited" — any tip made later in it is never seen
    - The stock and NIFTY legs of excess return can land on different price
      granularities (daily vs weekly), since the index's fetch window is
      chosen from the oldest tip in the whole run, not per-tip

    ### Disclaimer
    This tool is for **educational purposes only** and does not constitute investment advice.
    Past performance of any creator does not guarantee future results.
    """)

# Footer
st.sidebar.divider()
st.sidebar.caption("Built for the SerpApi India Hackathon 2026")
st.sidebar.caption("By Darshan Rajagoli")
