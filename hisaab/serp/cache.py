"""
Persistent SerpApi response cache backed by SQLite.

Cache key = sha256 of canonically sorted parameters (api_key stripped).
TTL varies by engine — transcripts are immutable, prices expire daily.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

# TTL in seconds per engine family
ENGINE_TTL: dict[str, int] = {
    "youtube_video_transcript": -1,  # immutable, never expires
    "youtube_video": -1,  # immutable
    "youtube_channel": 86400,  # 1 day
    "google_finance": 86400,  # 1 day
    "google_news": 86400,  # 1 day
    "google_trends": 86400,  # 1 day
}
DEFAULT_TTL = 3600  # 1 hour, matches SerpApi's own cache


def _make_cache_key(params: dict[str, Any]) -> str:
    """Create a deterministic cache key from search parameters."""
    filtered = {k: v for k, v in sorted(params.items()) if k != "api_key"}
    canonical = json.dumps(filtered, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


class SerpCache:
    """SQLite-backed response cache for SerpApi calls."""

    def __init__(self, db_path: str | Path = "hisaab_cache.db"):
        self.db_path = Path(db_path)
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _init_db(self) -> None:
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cache (
                cache_key TEXT PRIMARY KEY,
                engine TEXT NOT NULL,
                params_json TEXT NOT NULL,
                response_json TEXT NOT NULL,
                created_at REAL NOT NULL,
                ttl INTEGER NOT NULL
            )
            """
        )
        self._conn.commit()

    def get(self, params: dict[str, Any]) -> Optional[dict]:
        """Look up a cached response. Returns None on miss or expiry."""
        key = _make_cache_key(params)
        row = self._conn.execute(
            "SELECT response_json, created_at, ttl FROM cache WHERE cache_key = ?",
            (key,),
        ).fetchone()
        if row is None:
            return None
        response_json, created_at, ttl = row
        if ttl != -1 and (time.time() - created_at) > ttl:
            self._conn.execute("DELETE FROM cache WHERE cache_key = ?", (key,))
            self._conn.commit()
            return None
        return json.loads(response_json)

    def put(self, params: dict[str, Any], response: dict) -> None:
        """Store a response in the cache."""
        key = _make_cache_key(params)
        engine = params.get("engine", "unknown")
        ttl = ENGINE_TTL.get(engine, DEFAULT_TTL)
        self._conn.execute(
            """
            INSERT OR REPLACE INTO cache (cache_key, engine, params_json, response_json, created_at, ttl)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                key,
                engine,
                json.dumps(params, sort_keys=True),
                json.dumps(response),
                time.time(),
                ttl,
            ),
        )
        self._conn.commit()

    def has(self, params: dict[str, Any]) -> bool:
        """Check if a valid (non-expired) cached response exists."""
        return self.get(params) is not None

    def stats(self) -> dict[str, int]:
        """Return count of cached entries by engine."""
        rows = self._conn.execute("SELECT engine, COUNT(*) FROM cache GROUP BY engine").fetchall()
        return dict(rows)

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
