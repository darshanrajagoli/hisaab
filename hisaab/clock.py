"""
The pipeline's notion of "today".

Live mode uses the real date. Replay mode uses the date the fixture bundle
was recorded (fixtures/<bundle>/bundle.json → "as_of"), because several
decisions are relative to today — which Google Finance window to request,
whether a tip's horizon has elapsed, how to read "3 weeks ago" — and a
replay run must make the same decisions the recorded live run did, or it
asks for fixtures that were never recorded and the scorecard silently
shrinks as real time passes.
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

_FIXTURES_ROOT = Path(__file__).parent.parent / "fixtures"


def bundle_as_of(bundle: str) -> date | None:
    """The recording date of a fixture bundle, or None if it doesn't declare one."""
    meta = _FIXTURES_ROOT / bundle / "bundle.json"
    if not meta.exists():
        return None
    with open(meta, encoding="utf-8") as f:
        as_of = json.load(f).get("as_of")
    return date.fromisoformat(as_of) if as_of else None


def today() -> date:
    if os.getenv("HISAAB_MODE") == "replay":
        as_of = bundle_as_of(os.getenv("HISAAB_REPLAY_BUNDLE", "demo"))
        if as_of is not None:
            return as_of
    return date.today()
