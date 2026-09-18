"""
Step 5: Video metadata retrieval.

Fetches exact publish dates and descriptions from youtube_video.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Optional

from hisaab.models import VideoInfo
from hisaab.serp.client import SerpClient

logger = logging.getLogger(__name__)


def fetch_metadata(client: SerpClient, videos: list[VideoInfo]) -> list[VideoInfo]:
    """
    Enrich videos with exact publish dates and descriptions.

    Calls youtube_video for each selected video.
    """
    enriched = []
    for video in videos:
        try:
            result = client.search_youtube_video(video.video_id)
            info = result.get("video_results", result)

            # Extract publish date
            publish_date = _extract_publish_date(info)
            if publish_date:
                video.publish_date = publish_date

            # Extract description — sometimes a plain string, sometimes
            # {"content": "...", "link": "..."} depending on the response.
            description = info.get("description", "")
            if isinstance(description, dict):
                description = description.get("content", "")
            if description:
                video.description = description

            # Extract view count
            views = info.get("views")
            if views is not None:
                try:
                    video.view_count = int(str(views).replace(",", ""))
                except (ValueError, TypeError):
                    pass

            enriched.append(video)
            logger.debug(f"Metadata: {video.video_id} → {video.publish_date}")

        except Exception as e:
            logger.warning(f"Failed to fetch metadata for {video.video_id}: {e}")
            enriched.append(video)  # Keep the video even without metadata

    logger.info(
        f"Fetched metadata for {len(enriched)} videos, "
        f"{sum(1 for v in enriched if v.publish_date)} with dates"
    )
    return enriched


def _extract_publish_date(info: dict) -> Optional[date]:
    """
    Extract the publish date from various fields in the youtube_video response.

    Tries multiple fields since the location may vary.
    """
    # Try direct date fields
    for field in ["published_date", "date", "upload_date", "publish_date"]:
        val = info.get(field)
        if val:
            parsed = _parse_date_str(str(val))
            if parsed:
                return parsed

    # Try nested channel info
    channel = info.get("channel", {})
    for field in ["published_date", "date"]:
        val = channel.get(field)
        if val:
            parsed = _parse_date_str(str(val))
            if parsed:
                return parsed

    # Try rich_snippet or similar nested structures
    for key in ["rich_snippet", "primary_info", "microformat"]:
        nested = info.get(key, {})
        if isinstance(nested, dict):
            for field in ["published_date", "date", "uploadDate", "publishDate"]:
                val = nested.get(field)
                if val:
                    parsed = _parse_date_str(str(val))
                    if parsed:
                        return parsed

    return None


_DATE_PREFIX_RE = re.compile(
    r"^(premiered|streamed live on|scheduled for|live)\s+", re.IGNORECASE
)


def _parse_date_str(date_str: str) -> Optional[date]:
    """Parse various date formats."""
    date_str = _DATE_PREFIX_RE.sub("", date_str.strip())

    # Relative dates (fallback — imprecise)
    relative_match = re.match(r"(\d+)\s+(day|week|month|year)s?\s+ago", date_str, re.IGNORECASE)
    if relative_match:
        num = int(relative_match.group(1))
        unit = relative_match.group(2).lower()
        from datetime import timedelta

        today = date.today()
        if unit == "day":
            return today - timedelta(days=num)
        elif unit == "week":
            return today - timedelta(weeks=num)
        elif unit == "month":
            return today - timedelta(days=num * 30)
        elif unit == "year":
            return today - timedelta(days=num * 365)

    # ISO formats
    for fmt in [
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d",
        "%b %d, %Y",
        "%B %d, %Y",
        "%d %b %Y",
        "%d %B %Y",
        "%Y/%m/%d",
    ]:
        try:
            return datetime.strptime(date_str[: len(fmt) + 5], fmt).date()
        except ValueError:
            continue

    # Try dateutil as last resort
    try:
        from dateutil import parser as dateutil_parser

        return dateutil_parser.parse(date_str).date()
    except Exception:
        pass

    return None
