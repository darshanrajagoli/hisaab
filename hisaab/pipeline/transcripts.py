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
    prefer_language: str = "en",
) -> Optional[list[TranscriptSnippet]]:
    """
    Fetch transcript for a video.

    SerpApi's youtube_video_transcript engine returns whichever caption
    track YouTube generated (often Hindi/Hinglish for these channels
    regardless of `language_code`) — the param is a hint, not a filter.
    Returns None if no transcript is available at all.
    """
    snippets = _try_fetch(client, video.video_id, prefer_language)
    if snippets:
        return snippets

    fallback_language = "hi" if prefer_language != "hi" else "en"
    snippets = _try_fetch(client, video.video_id, fallback_language)
    if snippets:
        return snippets

    return None


def _try_fetch(
    client: SerpClient,
    video_id: str,
    language_code: Optional[str],
) -> Optional[list[TranscriptSnippet]]:
    """Attempt to fetch a transcript in a specific language."""
    try:
        params = {"v": video_id}
        if language_code:
            params["language_code"] = language_code

        result = client.search("youtube_video_transcript", params)

        # Real response key is "transcript"; keep older guesses as fallbacks
        # in case SerpApi renames the field in the future.
        transcript_results = (
            result.get("transcript")
            or result.get("transcript_results")
            or result.get("results")
            or []
        )

        if not transcript_results:
            return None

        raw_items = []
        for item in transcript_results:
            text = (item.get("snippet") or item.get("text") or "").strip()
            if not text:
                continue
            start_ms = int(item.get("start_ms", item.get("start", 0)) or 0)
            end_ms = item.get("end_ms")
            raw_items.append((start_ms, end_ms, text))

        if not raw_items:
            return None

        raw_items.sort(key=lambda triple: triple[0])

        # The API supplies end_ms directly. Only derive it from the next
        # snippet's start (or a 4s tail for the last one) if it's missing.
        snippets = []
        for idx, (start_ms, end_ms, text) in enumerate(raw_items):
            if end_ms is None:
                if idx + 1 < len(raw_items):
                    end_ms = raw_items[idx + 1][0]
                else:
                    end_ms = start_ms + 4000
            snippets.append(TranscriptSnippet(text=text, start_ms=start_ms, end_ms=int(end_ms)))

        logger.debug(
            f"Transcript for {video_id}: {len(snippets)} snippets (lang={language_code})"
        )
        return snippets

    except Exception as e:
        logger.debug(f"Transcript fetch failed for {video_id} (lang={language_code}): {e}")
        return None


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
