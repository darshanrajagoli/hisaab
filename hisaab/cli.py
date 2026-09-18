"""
Hisaab CLI — grade Indian finfluencer stock tips.

Usage:
    hisaab audit <channel_or_video>       # Live audit
    hisaab audit --replay demo <channel>  # Replay from fixtures
    hisaab channels                       # List audited channels
    hisaab report <channel_id>            # Show scorecard
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Optional

# Windows terminals default stdout/stderr to the cp1252 codepage, which
# can't encode Rich's unicode glyphs (●, ✓, ✗, etc.) and crashes mid-run.
if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8")

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from hisaab.models import AuditRun, TipOutcome
from hisaab.pipeline.orchestrator import run_audit
from hisaab.serp.client import SerpClient
from hisaab.store import HisaabStore

load_dotenv()

app = typer.Typer(
    name="hisaab",
    help="Grade Indian finfluencer stock tips against actual market outcomes.",
    add_completion=False,
)
console = Console()


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _progress_callback(stage: str, message: str, data: dict) -> None:
    """Rich console progress display."""
    engine = data.get("engine", "")
    badge = f" [{engine}]" if engine else ""
    style = {
        "init": "bold blue",
        "discover": "cyan",
        "select": "cyan",
        "metadata": "yellow",
        "transcripts": "yellow",
        "windows": "green",
        "extract": "magenta",
        "verify": "magenta",
        "resolve": "blue",
        "prices": "yellow",
        "corporate_actions": "red",
        "score": "green",
        "stats": "green",
        "explain": "yellow",
        "complete": "bold green",
    }.get(stage, "white")

    console.print(f"  [{style}]●[/{style}] {message}{badge}")


@app.command()
def audit(
    input: str = typer.Argument(help="YouTube channel URL/handle or video URL"),
    replay: Optional[str] = typer.Option(
        None, "--replay", "-r", help="Replay from fixture bundle (e.g., 'demo')"
    ),
    max_videos: int = typer.Option(10, "--max-videos", "-n", help="Max videos to audit"),
    no_llm_verify: bool = typer.Option(False, "--no-llm-verify", help="Skip LLM verification"),
    no_news: bool = typer.Option(False, "--no-news", help="Skip news explanations"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging"),
) -> None:
    """Run an audit on a YouTube channel or video."""
    _setup_logging(verbose)

    console.print(
        Panel(
            "[bold]Hisaab[/bold] — Grading stock tips against market outcomes",
            subtitle="hisaab keeps the receipts",
        )
    )

    # Setup mode
    mode = "replay" if replay else "live"
    if replay:
        os.environ["HISAAB_MODE"] = "replay"
        console.print(f"  Mode: [yellow]replay[/yellow] (fixtures: {replay})")
    else:
        console.print("  Mode: [green]live[/green]")

    # Initialize
    try:
        client = SerpClient(mode=mode)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if mode == "live" and not os.getenv("GEMINI_API_KEY"):
        console.print(
            "[red]Error:[/red] GEMINI_API_KEY is not set. Live mode needs it for tip "
            "extraction/verification — without it every SerpApi call still runs "
            "(spending your monthly quota) but the pipeline extracts zero tips. "
            "Set it in .env or use --replay demo to run with no API keys."
        )
        raise typer.Exit(1)

    store = HisaabStore()

    # Show budget
    budget = client.budget
    console.print(
        f"  Budget: {budget.remaining_monthly()} monthly searches remaining "
        f"(cap: {budget.monthly_cap})"
    )
    console.print()

    # Run audit
    try:
        run = run_audit(
            user_input=input,
            client=client,
            store=store,
            max_videos=max_videos,
            use_llm_verify=not no_llm_verify,
            explain_news=not no_news,
            progress=_progress_callback,
        )
    except Exception as e:
        console.print(f"\n[red]Error during audit:[/red] {e}")
        if verbose:
            console.print_exception()
        raise typer.Exit(1)

    # Display results
    console.print()
    _display_scorecard(run)

    # Budget summary
    console.print()
    summary = client.budget.summary()
    console.print(
        f"  API calls this run: {summary['run_used']} "
        f"(monthly remaining: {summary['monthly_remaining']})"
    )
    for engine, stats in summary["engines"].items():
        console.print(f"    {engine}: {stats['calls']} calls, {stats['cache_hits']} cache hits")


def _display_scorecard(run: AuditRun) -> None:
    """Display the scorecard in the terminal."""
    stats = run.stats
    if not stats:
        console.print("[yellow]No statistics available.[/yellow]")
        return

    # Header
    console.print(
        Panel(
            f"[bold]{run.channel.channel_title}[/bold]\nChannel ID: {run.channel.channel_id}",
            title="📊 Scorecard",
        )
    )

    # Headline numbers
    if stats.insufficient_evidence:
        console.print(
            Panel(
                f"[yellow bold]⚠ INSUFFICIENT EVIDENCE[/yellow bold]\n"
                f"Only {stats.total_scored} scored tips. "
                f"Need at least 10 for statistical analysis.",
                style="yellow",
            )
        )

    headline = Table(show_header=False, box=None, padding=(0, 2))
    headline.add_column("Metric", style="bold")
    headline.add_column("Value")

    headline.add_row("Scored Tips", str(stats.total_scored))

    if stats.hit_rate_market is not None:
        hr = f"{stats.hit_rate_market:.1%}"
        ci = f"[{stats.hit_rate_market_ci_low:.1%}, {stats.hit_rate_market_ci_high:.1%}]"
        headline.add_row("Hit Rate (vs NIFTY)", f"{hr} {ci}")

    if stats.mean_excess_return is not None:
        mr = f"{stats.mean_excess_return:+.2%}"
        ci = f"[{stats.mean_excess_ci_low:+.2%}, {stats.mean_excess_ci_high:+.2%}]"
        headline.add_row("Mean Excess Return", f"{mr} {ci}")

    if stats.binomial_verdict:
        headline.add_row("Statistical Test", stats.binomial_verdict)

    if stats.simulation_pnl is not None:
        headline.add_row(
            "₹10K/tip Simulation",
            f"Portfolio: ₹{stats.simulation_pnl:+,.0f} | "
            f"NIFTY: ₹{stats.simulation_nifty_pnl:+,.0f}",
        )

    console.print(headline)
    console.print()

    # Conviction analysis
    if stats.conviction_count > 0:
        console.print(
            f"  Conviction calls ({stats.conviction_count}): "
            f"{stats.conviction_hit_rate:.1%} hit rate vs "
            f"{stats.non_conviction_hit_rate:.1%} for regular calls"
        )

    # Tips table
    scored_tips = [t for t in run.tips if t.is_scored]
    if scored_tips:
        console.print()
        table = Table(title="Scored Tips")
        table.add_column("Date", style="dim")
        table.add_column("Stock")
        table.add_column("Call")
        table.add_column("Outcome")
        table.add_column("Return", justify="right")
        table.add_column("vs NIFTY", justify="right")

        for tip in sorted(scored_tips, key=lambda t: t.entry_date or ""):
            outcome_style = {
                TipOutcome.TARGET_HIT: "green",
                TipOutcome.STOP_HIT: "red",
                TipOutcome.EXPIRED: "yellow",
            }.get(tip.outcome, "white")

            table.add_row(
                str(tip.entry_date) if tip.entry_date else "—",
                tip.ticker or tip.company_name_raw,
                tip.direction.value,
                Text(tip.outcome.value if tip.outcome else "—", style=outcome_style),
                f"{tip.stock_return:+.1%}" if tip.stock_return is not None else "—",
                f"{tip.excess_return:+.1%}" if tip.excess_return is not None else "—",
            )

        console.print(table)

    # Unscored summary
    if stats.unscored_breakdown:
        console.print()
        console.print("[dim]Unscored tips:[/dim]")
        for reason, count in sorted(stats.unscored_breakdown.items()):
            console.print(f"  {reason}: {count}")

    # Funnel
    console.print()
    console.print("[dim]Pipeline funnel:[/dim]")
    f = run.funnel
    console.print(f"  Videos discovered: {f.videos_discovered}")
    console.print(f"  Videos selected: {f.videos_selected}")
    console.print(f"  Transcripts obtained: {f.videos_with_transcripts}")
    console.print(f"  Windows scanned: {f.windows_total}")
    console.print(f"  Windows with keywords: {f.windows_with_keywords}")
    console.print(f"  Tips extracted: {f.tips_extracted}")
    console.print(f"  Tips verified: {f.tips_verified}")
    console.print(f"  Tips resolved: {f.tips_resolved}")
    console.print(f"  Tips scored: {f.tips_scored}")


@app.command()
def channels() -> None:
    """List all audited channels."""
    store = HisaabStore()
    channels = store.list_channels()
    if not channels:
        console.print("[yellow]No channels audited yet.[/yellow]")
        return

    table = Table(title="Audited Channels")
    table.add_column("Channel")
    table.add_column("ID")
    table.add_column("Last Audited")

    for ch in channels:
        table.add_row(ch["channel_title"], ch["channel_id"], ch["updated_at"])

    console.print(table)


@app.command()
def report(
    channel_id: str = typer.Argument(help="Channel ID to show report for"),
) -> None:
    """Show the scorecard for a previously audited channel."""
    store = HisaabStore()
    run = store.get_latest_run(channel_id)
    if not run:
        console.print(f"[yellow]No audit found for channel {channel_id}[/yellow]")
        raise typer.Exit(1)

    _display_scorecard(run)


if __name__ == "__main__":
    app()
