"""
Export the local SQLite caches into a replay fixture bundle.

Every response Hisaab has ever fetched live is sitting in hisaab_cache.db
(SerpApi) and hisaab_llm_cache.db (Gemini), keyed by the same cache_key the
replay-mode client/LLM layer look up. This script dumps both caches into
fixtures/<bundle>/, so `hisaab audit --replay <bundle> <channel>` can
reproduce a full real audit with zero API keys.

Usage:
    python scripts/export_fixtures.py [bundle_name]
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent


def export_serp(out_dir: Path) -> int:
    cache_db = ROOT / "hisaab_cache.db"
    if not cache_db.exists():
        print(f"No SerpApi cache DB found at {cache_db}. Run a live audit first.")
        return 0

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
    return len(index)


def export_llm(out_dir: Path) -> int:
    """Copy the Gemini response cache in as-is; llm.py reads this same schema."""
    cache_db = ROOT / "hisaab_llm_cache.db"
    if not cache_db.exists():
        print(f"No LLM cache DB found at {cache_db}. Run a live audit first.")
        return 0

    conn = sqlite3.connect(str(cache_db))
    count = conn.execute("SELECT COUNT(*) FROM llm_cache").fetchone()[0]
    conn.close()

    shutil.copyfile(cache_db, out_dir / "llm_cache.db")
    return count


def export(bundle_name: str = "demo") -> None:
    out_dir = ROOT / "fixtures" / bundle_name
    out_dir.mkdir(parents=True, exist_ok=True)

    serp_count = export_serp(out_dir)
    llm_count = export_llm(out_dir)

    print(f"Exported {serp_count} SerpApi fixtures and {llm_count} LLM responses to {out_dir}")


if __name__ == "__main__":
    bundle = sys.argv[1] if len(sys.argv) > 1 else "demo"
    export(bundle)
