"""
Step 3: Discovery.

Find tip-related videos from a YouTube channel using within-channel search
to conserve budget. Extracts channel info and video stubs.
"""

from __future__ import annotations

import logging
import re
from typing import Optional
from urllib.parse import parse_qs, urlparse

from hisaab.models import ChannelInfo, VideoInfo
from hisaab.serp.client import SerpClient

logger = logging.getLogger(__name__)

# Keywords that indicate stock tips — used for within-channel search
TIP_KEYWORDS_EN = ["target", "stock buy", "multibagger", "breakout", "stop loss", "share buy"]
TIP_KEYWORDS_HI = ["target", "kharid", "stoploss", "share khareedein"]


def parse_channel_input(user_input: str) -> dict[str, str]:
    """
    Parse user input into a channel identifier.

    Accepts:
    - Channel URL: https://www.youtube.com/@handle or /channel/UC...
    - Channel handle: @handle
    - Channel ID: UC...
    - Video URL: extracts video_id for single-video mode
    """
    user_input = user_input.strip()

    # Video URL
    if "watch?v=" in user_input or "youtu.be/" in user_input:
        parsed = urlparse(user_input)
        if "youtu.be" in parsed.netloc:
            video_id = parsed.path.strip("/")
        else:
            video_id = parse_qs(parsed.query).get("v", [""])[0]
        return {"type": "video", "video_id": video_id}

    # Channel URL with handle
    handle_match = re.search(r"youtube\.com/@([\w.-]+)", user_input)
    if handle_match:
        return {"type": "channel", "handle": f"@{handle_match.group(1)}"}

    # Channel URL with ID
    id_match = re.search(r"youtube\.com/channel/(UC[\w-]+)", user_input)
    if id_match:
        return {"type": "channel", "channel_id": id_match.group(1)}

    # Bare handle
    if user_input.startswith("@"):
        return {"type": "channel", "handle": user_input}

    # Bare channel ID
    if user_input.startswith("UC") and len(user_input) > 20:
        return {"type": "channel", "channel_id": user_input}

    # Assume handle
    return {"type": "channel", "handle": f"@{user_input}"}


def discover_videos(
    client: SerpClient,
    channel_input: dict[str, str],
    max_search_calls: int = 2,
) -> tuple[ChannelInfo, list[VideoInfo]]:
    """
    Discover tip-related videos from a channel.

    Uses within-channel search with tip keywords to find relevant videos
    without paging through the entire channel.
    """
    videos: list[VideoInfo] = []
    seen_ids: set[str] = set()
    channel_info = ChannelInfo(channel_id="", channel_title="")

    # Build base params
    base_params: dict = {}
    if "channel_id" in channel_input:
        base_params["channel_id"] = channel_input["channel_id"]
    elif "handle" in channel_input:
        base_params["handle"] = channel_input["handle"]

    # Search with tip keywords
    search_queries = TIP_KEYWORDS_EN[:max_search_calls]
    for query in search_queries:
        params = {**base_params, "search_query": query}
        try:
            result = client.search("youtube_channel", params)
        except Exception as e:
            logger.warning(f"Channel search failed for '{query}': {e}")
            continue

        # Extract channel info from first response
        if not channel_info.channel_id:
            channel_info = _extract_channel_info(result)

        # Extract videos
        for video in result.get("videos", []):
            vid_id = video.get("video_id", "")
            if vid_id and vid_id not in seen_ids:
                seen_ids.add(vid_id)
                videos.append(
                    VideoInfo(
                        video_id=vid_id,
                        title=video.get("title", ""),
                        channel_id=channel_info.channel_id,
                        channel_title=channel_info.channel_title,
                        view_count=_parse_views(video.get("views")),
                    )
                )

    logger.info(f"Discovered {len(videos)} videos from {channel_info.channel_title}")
    return channel_info, videos


def discover_single_video(client: SerpClient, video_id: str) -> tuple[ChannelInfo, list[VideoInfo]]:
    """Handle single-video mode."""
    result = client.search_youtube_video(video_id)
    info = result.get("video_results", result)

    channel_id = info.get("channel", {}).get("id", "")
    channel_title = info.get("channel", {}).get("name", "")

    channel = ChannelInfo(
        channel_id=channel_id,
        channel_title=channel_title,
    )
    video = VideoInfo(
        video_id=video_id,
        title=info.get("title", ""),
        channel_id=channel_id,
        channel_title=channel_title,
        description=info.get("description", ""),
    )
    return channel, [video]


def _extract_channel_info(result: dict) -> ChannelInfo:
    """Extract channel metadata from a youtube_channel response."""
    header = result.get("channel_results", result.get("header", {}))
    channel_id = header.get("channel_id", "")
    title = header.get("title", "")
    # Try alternate locations
    if not channel_id:
        meta = result.get("search_parameters", {})
        channel_id = meta.get("channel_id", "")
    return ChannelInfo(
        channel_id=channel_id,
        channel_title=title,
    )


def _parse_views(views_str) -> Optional[int]:
    """Parse view count from string like '1.2M views'."""
    if views_str is None:
        return None
    if isinstance(views_str, (int, float)):
        return int(views_str)
    views_str = str(views_str).lower().replace(",", "").replace(" views", "").strip()
    try:
        if "m" in views_str:
            return int(float(views_str.replace("m", "")) * 1_000_000)
        if "k" in views_str:
            return int(float(views_str.replace("k", "")) * 1_000)
        return int(views_str)
    except (ValueError, TypeError):
        return None
