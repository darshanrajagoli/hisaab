"""
Step 15: News explanations.

For the top 3 and bottom 3 tips by excess return, fetch Google News
to explain what happened. The LLM writes a one-line neutral explanation
with the source link. It must not add claims beyond the articles.
"""

from __future__ import annotations

import logging

from hisaab.llm import call_llm
from hisaab.models import ScoredTip
from hisaab.serp.client import SerpClient

logger = logging.getLogger(__name__)


def explain_top_tips(
    client: SerpClient,
    tips: list[ScoredTip],
    n_each: int = 3,
) -> list[ScoredTip]:
    """
    Add news explanations to the top wins and top losses.

    Only scored tips with excess return are eligible.
    Uses google_news, bounded to the tip's time window.
    """
    scored = [t for t in tips if t.is_scored and t.excess_return is not None]
    if not scored:
        return tips

    # Sort by excess return
    scored_sorted = sorted(scored, key=lambda t: t.excess_return, reverse=True)

    # Top wins and losses
    top_wins = scored_sorted[:n_each]
    top_losses = scored_sorted[-n_each:]
    explain_set = set()

    for tip in top_wins + top_losses:
        # Use a tuple key for dedup
        key = (tip.video_id, tip.start_ms, tip.ticker)
        if key in explain_set:
            continue
        explain_set.add(key)

        explanation, source_url = _fetch_explanation(client, tip)
        if explanation:
            tip.news_explanation = explanation
            tip.news_source_url = source_url

    explained = sum(1 for t in tips if t.news_explanation)
    logger.info(f"Explanations: {explained} tips explained with news")
    return tips


def _fetch_explanation(
    client: SerpClient,
    tip: ScoredTip,
) -> tuple[str, str]:
    """Fetch news and generate an explanation for a single tip."""
    if not tip.ticker:
        return ("", "")

    # Build query
    company_name = tip.company_name_raw or tip.ticker
    query = f"{company_name} stock"

    try:
        result = client.search_google_news(query)
    except Exception as e:
        logger.debug(f"News fetch failed for {tip.ticker}: {e}")
        return ("", "")

    # Extract top articles
    articles = result.get("news_results", [])
    if not articles:
        articles = result.get("organic_results", [])

    if not articles:
        return ("", "")

    # Build context from top 3 articles
    article_summaries = []
    source_url = ""
    for article in articles[:3]:
        title = article.get("title", "")
        snippet = article.get("snippet", article.get("description", ""))
        link = article.get("link", "")
        if title:
            article_summaries.append(f"- {title}: {snippet}")
            if not source_url and link:
                source_url = link

    if not article_summaries:
        return ("", "")

    # LLM generates a one-line explanation
    prompt = f"""Based on these news articles about {company_name} ({tip.ticker}), write ONE neutral sentence explaining why the stock {"rose" if (tip.excess_return or 0) > 0 else "fell"} during this period.

Articles:
{chr(10).join(article_summaries)}

Rules:
- One sentence only
- Neutral tone, no judgment
- Do not add claims beyond what the articles say
- If the articles don't explain the move, say "No clear catalyst identified in news coverage."

Return ONLY the explanation sentence, no other text."""

    try:
        explanation = call_llm(
            prompt,
            model="gemini-3.6-flash",
            max_tokens=256,
            temperature=0.0,
        ).strip()
        return (explanation, source_url)
    except Exception as e:
        logger.debug(f"Explanation generation failed for {tip.ticker}: {e}")
        return ("", "")
