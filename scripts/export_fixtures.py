"""
Export the local SQLite cache into a replay fixture bundle.

Every response Hisaab has ever fetched live is sitting in hisaab_cache.db,
keyed by the same cache_key the replay-mode client looks up. This script
dumps that cache straight into fixtures/<bundle>/, so `hisaab audit --replay
<bundle> <channel>` can reproduce a full real audit with zero API keys.

Usage:
    python scripts/export_fixtures.py [bundle_name]
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent


def export(bundle_name: str = "demo") -> None:
    cache_db = ROOT / "hisaab_cache.db"
    if not cache_db.exists():
        print(f"No cache DB found at {cache_db}. Run a live audit first.")
        sys.exit(1)

    out_dir = ROOT / "fixtures" / bundle_name
    out_dir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(cache_db))
    rows = conn.execute("SELECT cache_key, response_json FROM cache").fetchall()
    conn.close()

    index: dict[str, str] = {}
    for cache_key, response_json in rows:
        response = json.loads(response_json)
        # search_metadata carries account-linked SerpApi archive permalinks
        # (serpapi.com/searches/<token>/...) — not secrets, but no reason to
        # publish them in a public repo. The rest of the response (what the
        # pipeline actually reads) is untouched.
        response.pop("search_metadata", None)

        filename = f"{cache_key}.json"
        (out_dir / filename).write_text(json.dumps(response), encoding="utf-8")
        index[cache_key] = filename

    (out_dir / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
    print(f"Exported {len(index)} fixtures to {out_dir}")


if __name__ == "__main__":
    bundle = sys.argv[1] if len(sys.argv) > 1 else "demo"
    export(bundle)
