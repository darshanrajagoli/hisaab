"""
Step 3: Discovery.

Find tip-related videos from a YouTube channel using within-channel search
to conserve budget. Extracts channel info and video stubs.

SerpApi's youtube_channel engine takes a single `channel_id` param that
accepts EITHER a UC... id OR an @handle directly — there is no separate
`handle` param. Search results come back as a flat `search_results` list
mixing `type: "video"` and `type: "playlist"` entries (playlists nest their
own `videos` list, which we skip — those lack view/date metadata).
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
        return {"type": "channel", "channel_id": f"@{handle_match.group(1)}"}

    # Channel URL with ID
    id_match = re.search(r"youtube\.com/channel/(UC[\w-]+)", user_input)
    if id_match:
        return {"type": "channel", "channel_id": id_match.group(1)}

    # Bare handle
    if user_input.startswith("@"):
        return {"type": "channel", "channel_id": user_input}

    # Bare channel ID
    if user_input.startswith("UC") and len(user_input) > 20:
        return {"type": "channel", "channel_id": user_input}

    # Assume handle
    return {"type": "channel", "channel_id": f"@{user_input}"}


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

    channel_id_param = channel_input.get("channel_id", "")

    # Search with tip keywords
    search_queries = TIP_KEYWORDS_EN[:max_search_calls]
    for query in search_queries:
        params = {"channel_id": channel_id_param, "search_query": query}
        try:
            result = client.search("youtube_channel", params)
        except Exception as e:
            logger.warning(f"Channel search failed for '{query}': {e}")
            continue

        # Extract channel info from first response
        if not channel_info.channel_id:
            channel_info = _extract_channel_info(result, fallback_id=channel_id_param)

        # Extract video-type entries (skip nested playlist videos — no metadata)
        for entry in result.get("search_results", []):
            if entry.get("type") != "video":
                continue
            vid_id = entry.get("video_id", "")
            if vid_id and vid_id not in seen_ids:
                seen_ids.add(vid_id)
                videos.append(
                    VideoInfo(
                        video_id=vid_id,
                        title=entry.get("title", ""),
                        channel_id=channel_info.channel_id,
                        channel_title=channel_info.channel_title,
                        view_count=_parse_views(
                            entry.get("extracted_views", entry.get("views"))
                        ),
                    )
                )

    logger.info(f"Discovered {len(videos)} videos from {channel_info.channel_title}")
    return channel_info, videos


def discover_single_video(client: SerpClient, video_id: str) -> tuple[ChannelInfo, list[VideoInfo]]:
    """Handle single-video mode."""
    result = client.search_youtube_video(video_id)
    info = result.get("video_results", result)

    channel = info.get("channel", {})
    channel_title = channel.get("name", "")
    channel_id = _channel_id_from_link(channel.get("link", ""))

    channel_info = ChannelInfo(
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
    return channel_info, [video]


def _channel_id_from_link(link: str) -> str:
    """Extract a usable channel identifier (UC id or @handle) from a channel link."""
    if not link:
        return ""
    id_match = re.search(r"/channel/(UC[\w-]+)", link)
    if id_match:
        return id_match.group(1)
    handle_match = re.search(r"/@([\w.-]+)", link)
    if handle_match:
        return f"@{handle_match.group(1)}"
    return ""


def _extract_channel_info(result: dict, fallback_id: str = "") -> ChannelInfo:
    """Extract channel metadata from a youtube_channel response."""
    header = result.get("channel_results", {})
    # `external_id` is the real UC... id; keep the @handle as a display fallback.
    channel_id = header.get("external_id", "") or fallback_id
    title = header.get("title", "")
    handle = header.get("handle", "")
    subscribers = header.get("subscribers")
    return ChannelInfo(
        channel_id=channel_id,
        channel_title=title,
        handle=handle,
        subscriber_count=subscribers if isinstance(subscribers, int) else None,
    )


def _parse_views(views_str) -> Optional[int]:
    """Parse view count from string like '1.2M views' or '134,475 views'."""
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
