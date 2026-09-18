"""
Persistent storage layer backed by SQLite.

Stores channels, videos, tips, scores, and run metadata.
Both the CLI and Streamlit UI read from this single store.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from hisaab.models import AuditRun, ChannelInfo, ChannelStats, ScoredTip, VideoInfo

DEFAULT_DB = Path("hisaab_data.db")


class HisaabStore:
    """SQLite-backed persistence for audit data."""

    def __init__(self, db_path: str | Path = DEFAULT_DB):
        self.db_path = Path(db_path)
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _init_db(self) -> None:
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS channels (
                channel_id TEXT PRIMARY KEY,
                channel_title TEXT,
                handle TEXT,
                data_json TEXT,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS videos (
                video_id TEXT PRIMARY KEY,
                channel_id TEXT,
                title TEXT,
                publish_date TEXT,
                data_json TEXT,
                FOREIGN KEY (channel_id) REFERENCES channels(channel_id)
            );

            CREATE TABLE IF NOT EXISTS tips (
                tip_id TEXT PRIMARY KEY,
                video_id TEXT,
                channel_id TEXT,
                ticker TEXT,
                direction TEXT,
                data_json TEXT,
                FOREIGN KEY (video_id) REFERENCES videos(video_id)
            );

            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                channel_id TEXT,
                started_at TEXT,
                completed_at TEXT,
                stats_json TEXT,
                funnel_json TEXT,
                data_json TEXT,
                FOREIGN KEY (channel_id) REFERENCES channels(channel_id)
            );
            """
        )
        self._conn.commit()

    def save_run(self, run: AuditRun) -> None:
        """Save a complete audit run."""
        # Save channel
        self._conn.execute(
            """INSERT OR REPLACE INTO channels
               (channel_id, channel_title, handle, data_json, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                run.channel.channel_id,
                run.channel.channel_title,
                run.channel.handle,
                run.channel.model_dump_json(),
                datetime.now().isoformat(),
            ),
        )

        # Save videos
        for video in run.videos:
            self._conn.execute(
                """INSERT OR REPLACE INTO videos
                   (video_id, channel_id, title, publish_date, data_json)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    video.video_id,
                    video.channel_id,
                    video.title,
                    str(video.publish_date) if video.publish_date else None,
                    video.model_dump_json(),
                ),
            )

        # Save tips
        for tip in run.tips:
            tip_id = f"{tip.video_id}_{tip.start_ms}_{tip.company_name_raw}"
            self._conn.execute(
                """INSERT OR REPLACE INTO tips
                   (tip_id, video_id, channel_id, ticker, direction, data_json)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    tip_id,
                    tip.video_id,
                    run.channel.channel_id,
                    tip.ticker,
                    tip.direction.value,
                    tip.model_dump_json(),
                ),
            )

        # Save run
        self._conn.execute(
            """INSERT OR REPLACE INTO runs
               (run_id, channel_id, started_at, completed_at, stats_json, funnel_json, data_json)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                run.run_id,
                run.channel.channel_id,
                run.started_at.isoformat() if run.started_at else None,
                run.completed_at.isoformat() if run.completed_at else None,
                run.stats.model_dump_json() if run.stats else None,
                run.funnel.model_dump_json(),
                json.dumps({"cost": run.cost.model_dump()}),
            ),
        )
        self._conn.commit()

    def get_run(self, run_id: str) -> Optional[AuditRun]:
        """Load a run by ID."""
        row = self._conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if not row:
            return None
        return self._parse_run(row)

    def get_latest_run(self, channel_id: str) -> Optional[AuditRun]:
        """Get the most recent run for a channel."""
        row = self._conn.execute(
            "SELECT * FROM runs WHERE channel_id = ? ORDER BY started_at DESC LIMIT 1",
            (channel_id,),
        ).fetchone()
        if not row:
            return None
        return self._parse_run(row)

    def list_channels(self) -> list[dict]:
        """List all audited channels."""
        rows = self._conn.execute(
            "SELECT channel_id, channel_title, updated_at FROM channels ORDER BY updated_at DESC"
        ).fetchall()
        return [{"channel_id": r[0], "channel_title": r[1], "updated_at": r[2]} for r in rows]

    def get_tips_for_channel(self, channel_id: str) -> list[ScoredTip]:
        """Get all tips for a channel."""
        rows = self._conn.execute(
            "SELECT data_json FROM tips WHERE channel_id = ?", (channel_id,)
        ).fetchall()
        return [ScoredTip.model_validate_json(r[0]) for r in rows]

    def _parse_run(self, row) -> AuditRun:
        """Parse a database row into an AuditRun."""
        run_id, channel_id, started_at, completed_at, stats_json, funnel_json, data_json = row

        # Load channel
        ch_row = self._conn.execute(
            "SELECT data_json FROM channels WHERE channel_id = ?", (channel_id,)
        ).fetchone()
        channel = (
            ChannelInfo.model_validate_json(ch_row[0])
            if ch_row
            else ChannelInfo(channel_id=channel_id)
        )

        # Load videos
        vid_rows = self._conn.execute(
            "SELECT data_json FROM videos WHERE channel_id = ?", (channel_id,)
        ).fetchall()
        videos = [VideoInfo.model_validate_json(r[0]) for r in vid_rows]

        # Load tips
        tip_rows = self._conn.execute(
            "SELECT data_json FROM tips WHERE channel_id = ?", (channel_id,)
        ).fetchall()
        tips = [ScoredTip.model_validate_json(r[0]) for r in tip_rows]

        stats = ChannelStats.model_validate_json(stats_json) if stats_json else None

        from hisaab.models import PipelineFunnel

        funnel = (
            PipelineFunnel.model_validate_json(funnel_json) if funnel_json else PipelineFunnel()
        )

        return AuditRun(
            run_id=run_id,
            channel=channel,
            videos=videos,
            tips=tips,
            stats=stats,
            funnel=funnel,
            started_at=datetime.fromisoformat(started_at) if started_at else None,
            completed_at=datetime.fromisoformat(completed_at) if completed_at else None,
        )

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
