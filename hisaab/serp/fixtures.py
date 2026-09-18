"""
Fixture loading for replay mode.

When HISAAB_MODE=replay, the SerpApi client reads from a fixture bundle
instead of making network calls. This lets judges clone and run the full
app with no API key.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

DEFAULT_FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures" / "demo"


class FixtureStore:
    """Loads pre-recorded SerpApi responses from a fixtures directory."""

    def __init__(self, fixtures_dir: str | Path = DEFAULT_FIXTURES_DIR):
        self.fixtures_dir = Path(fixtures_dir)
        self._index: dict[str, Path] = {}
        self._load_index()

    def _load_index(self) -> None:
        """Build an index of available fixtures by cache key."""
        index_path = self.fixtures_dir / "index.json"
        if index_path.exists():
            with open(index_path) as f:
                raw = json.load(f)
            for key, filename in raw.items():
                self._index[key] = self.fixtures_dir / filename
        else:
            # Fall back to scanning directory for .json files
            for path in self.fixtures_dir.glob("*.json"):
                if path.name != "index.json":
                    self._index[path.stem] = path

    def get(self, cache_key: str) -> Optional[dict[str, Any]]:
        """Look up a fixture by its cache key."""
        path = self._index.get(cache_key)
        if path and path.exists():
            with open(path) as f:
                return json.load(f)
        return None

    def has(self, cache_key: str) -> bool:
        return cache_key in self._index

    @staticmethod
    def save_fixture(
        response: dict[str, Any],
        cache_key: str,
        fixtures_dir: str | Path = DEFAULT_FIXTURES_DIR,
    ) -> Path:
        """Save a response as a fixture file. Used during development."""
        fixtures_dir = Path(fixtures_dir)
        fixtures_dir.mkdir(parents=True, exist_ok=True)
        path = fixtures_dir / f"{cache_key}.json"
        with open(path, "w") as f:
            json.dump(response, f, indent=2)
        return path

    @staticmethod
    def build_index(fixtures_dir: str | Path = DEFAULT_FIXTURES_DIR) -> None:
        """Rebuild the index.json from files in the directory."""
        fixtures_dir = Path(fixtures_dir)
        index = {}
        for path in sorted(fixtures_dir.glob("*.json")):
            if path.name != "index.json":
                index[path.stem] = path.name
        with open(fixtures_dir / "index.json", "w") as f:
            json.dump(index, f, indent=2)
