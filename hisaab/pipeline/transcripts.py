"""
Step 6: Transcript retrieval.

Fetches auto-generated transcripts via youtube_video_transcript.
Tries Hindi first for Indian channels, falls back to English.
"""

from __future__ import annotations

import logging
from typing import Optional

from hisaab.models import TranscriptSnippet, VideoInfo
from hisaab.serp.client import SerpClient

logger = logging.getLogger(__name__)


def fetch_transcript(
    client: SerpClient,
    video: VideoInfo,
    prefer_language: str = "hi",
) -> Optional[list[TranscriptSnippet]]:
    """
    Fetch transcript for a video.

    Tries the preferred language first, then falls back to English.
    Returns None if no transcript is available.
    """
    # Try preferred language (Hindi for Indian channels)
    snippets = _try_fetch(client, video.video_id, prefer_language)
    if snippets:
        return snippets

    # Fall back to English
    if prefer_language != "en":
        snippets = _try_fetch(client, video.video_id, "en")
        if snippets:
            return snippets

    # Try without specifying language
    snippets = _try_fetch(client, video.video_id, None)
    return snippets


def _try_fetch(
    client: SerpClient,
    video_id: str,
    language_code: Optional[str],
) -> Optional[list[TranscriptSnippet]]:
    """Attempt to fetch a transcript in a specific language."""
    try:
        params = {"video_id": video_id, "type": "asr"}
        if language_code:
            params["lang"] = language_code

        result = client.search("youtube_video_transcript", params)

        # Check if we got transcript data
        transcript_results = result.get("transcript_results", result.get("results", []))

        if not transcript_results:
            # Try alternate response structures
            transcript_results = result.get("transcript", [])

        if not transcript_results:
            return None

        snippets = []
        for item in transcript_results:
            text = item.get("text", item.get("snippet", "")).strip()
            if not text:
                continue

            start_ms = _to_ms(item.get("start_ms", item.get("start", 0)))
            end_ms = _to_ms(item.get("end_ms", item.get("end", item.get("duration", 0) + start_ms)))

            snippets.append(TranscriptSnippet(text=text, start_ms=start_ms, end_ms=end_ms))

        if snippets:
            logger.debug(
                f"Transcript for {video_id}: {len(snippets)} snippets (lang={language_code})"
            )
            return snippets
        return None

    except Exception as e:
        logger.debug(f"Transcript fetch failed for {video_id} (lang={language_code}): {e}")
        return None


def _to_ms(value) -> int:
    """Convert a time value to milliseconds."""
    if value is None:
        return 0
    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError:
            return 0
    # If value looks like seconds (< 100000), convert to ms
    if isinstance(value, (int, float)):
        if value < 100000:
            return int(value * 1000)
        return int(value)
    return 0


def fetch_all_transcripts(
    client: SerpClient,
    videos: list[VideoInfo],
    prefer_language: str = "hi",
) -> dict[str, list[TranscriptSnippet]]:
    """Fetch transcripts for all videos. Returns {video_id: snippets}."""
    transcripts: dict[str, list[TranscriptSnippet]] = {}

    for video in videos:
        snippets = fetch_transcript(client, video, prefer_language)
        if snippets:
            transcripts[video.video_id] = snippets
            logger.info(f"✓ Transcript: {video.video_id} ({len(snippets)} snippets)")
        else:
            logger.warning(f"✗ No transcript: {video.video_id}")

    logger.info(f"Transcripts: {len(transcripts)}/{len(videos)} videos have transcripts")
    return transcripts
