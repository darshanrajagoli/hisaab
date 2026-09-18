"""
Budget governor for SerpApi calls.

Enforces per-run and monthly caps. Tracks calls, cache hits, and misses
per engine. Raises BudgetExceeded before any over-limit call happens.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


class BudgetExceeded(Exception):
    """Raised when a SerpApi call would exceed the configured budget."""

    def __init__(self, message: str, engine: str = "", run_used: int = 0, monthly_used: int = 0):
        self.engine = engine
        self.run_used = run_used
        self.monthly_used = monthly_used
        super().__init__(message)


@dataclass
class EngineStats:
    """Per-engine call tracking."""

    calls: int = 0
    cache_hits: int = 0
    cache_misses: int = 0


@dataclass
class BudgetGovernor:
    """
    Tracks and limits SerpApi usage.

    - run_cap: max new (non-cached) calls per audit run
    - monthly_cap: soft cap on total monthly calls
    """

    run_cap: int = field(default_factory=lambda: int(os.getenv("HISAAB_RUN_CAP", "50")))
    monthly_cap: int = field(default_factory=lambda: int(os.getenv("HISAAB_MONTHLY_CAP", "240")))
    monthly_used: int = 0
    run_used: int = 0
    engine_stats: dict[str, EngineStats] = field(default_factory=dict)

    def _get_engine(self, engine: str) -> EngineStats:
        if engine not in self.engine_stats:
            self.engine_stats[engine] = EngineStats()
        return self.engine_stats[engine]

    def check(self, engine: str) -> None:
        """Raise BudgetExceeded if the next call would exceed caps."""
        if self.run_used >= self.run_cap:
            raise BudgetExceeded(
                f"Run budget exhausted: {self.run_used}/{self.run_cap} calls used",
                engine=engine,
                run_used=self.run_used,
                monthly_used=self.monthly_used,
            )
        if self.monthly_used >= self.monthly_cap:
            raise BudgetExceeded(
                f"Monthly budget exhausted: {self.monthly_used}/{self.monthly_cap} calls used",
                engine=engine,
                run_used=self.run_used,
                monthly_used=self.monthly_used,
            )

    def record_call(self, engine: str) -> None:
        """Record a new (non-cached) API call."""
        stats = self._get_engine(engine)
        stats.calls += 1
        stats.cache_misses += 1
        self.run_used += 1
        self.monthly_used += 1

    def record_cache_hit(self, engine: str) -> None:
        """Record a cache hit (no API call made)."""
        stats = self._get_engine(engine)
        stats.cache_hits += 1

    def remaining_run(self) -> int:
        return max(0, self.run_cap - self.run_used)

    def remaining_monthly(self) -> int:
        return max(0, self.monthly_cap - self.monthly_used)

    def summary(self) -> dict:
        """Return a summary for display."""
        return {
            "run_used": self.run_used,
            "run_cap": self.run_cap,
            "run_remaining": self.remaining_run(),
            "monthly_used": self.monthly_used,
            "monthly_cap": self.monthly_cap,
            "monthly_remaining": self.remaining_monthly(),
            "engines": {
                name: {
                    "calls": s.calls,
                    "cache_hits": s.cache_hits,
                    "cache_misses": s.cache_misses,
                }
                for name, s in self.engine_stats.items()
            },
        }

    def reset_run(self) -> None:
        """Reset run counters for a new audit."""
        self.run_used = 0
        for stats in self.engine_stats.values():
            stats.calls = 0
            stats.cache_hits = 0
            stats.cache_misses = 0
