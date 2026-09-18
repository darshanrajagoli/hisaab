"""
Step 10: Ticker resolution.

Maps company names from transcripts to NSE ticker symbols using:
1. Static aliases (hand-maintained, includes Hindi names)
2. Fuzzy match against NSE equity list
3. LLM disambiguation for ambiguous cases
4. Google Finance validation (also fetches prices)
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Optional

import yaml
from rapidfuzz import fuzz, process

from hisaab.llm import call_llm_json
from hisaab.models import ResolvedTip, VerifiedTip

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent / "data"
NSE_CSV = DATA_DIR / "nse_equities.csv"
ALIASES_YAML = DATA_DIR / "aliases.yaml"


class TickerResolver:
    """Resolves company names to NSE ticker symbols."""

    def __init__(self):
        self.nse_data: dict[str, dict] = {}  # symbol -> {name, isin}
        self.name_to_symbol: dict[str, str] = {}  # lowercase name -> symbol
        self.aliases: dict[str, str] = {}  # alias -> symbol
        self._load_data()

    def _load_data(self) -> None:
        """Load NSE equity list and aliases."""
        # Load NSE equities
        if NSE_CSV.exists():
            with open(NSE_CSV) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    symbol = row.get("SYMBOL", row.get("symbol", "")).strip()
                    name = row.get(
                        "NAME OF COMPANY", row.get("name", row.get("company_name", ""))
                    ).strip()
                    isin = row.get("ISIN NUMBER", row.get("isin", "")).strip()
                    if symbol:
                        self.nse_data[symbol] = {"name": name, "isin": isin}
                        self.name_to_symbol[name.lower()] = symbol
                        # Also index by symbol
                        self.name_to_symbol[symbol.lower()] = symbol
            logger.info(f"Loaded {len(self.nse_data)} NSE equities")

        # Load aliases
        if ALIASES_YAML.exists():
            with open(ALIASES_YAML) as f:
                aliases_raw = yaml.safe_load(f) or {}
            for symbol, alias_list in aliases_raw.items():
                symbol = symbol.upper()
                for alias in alias_list:
                    self.aliases[alias.lower()] = symbol
            logger.info(f"Loaded {len(self.aliases)} aliases")

    def resolve(self, company_name: str, context: str = "") -> Optional[dict]:
        """
        Resolve a company name to an NSE symbol.

        Returns: {"symbol": "RELIANCE", "nse_ticker": "RELIANCE:NSE", "isin": "...", "method": "..."}
        """
        name = company_name.strip()
        name_lower = name.lower()

        # 1. Exact alias match
        if name_lower in self.aliases:
            symbol = self.aliases[name_lower]
            return self._make_result(symbol, "alias")

        # 2. Exact name match
        if name_lower in self.name_to_symbol:
            symbol = self.name_to_symbol[name_lower]
            return self._make_result(symbol, "exact")

        # 3. Fuzzy match against company names
        if self.name_to_symbol:
            candidates = list(self.name_to_symbol.keys())
            matches = process.extract(name_lower, candidates, scorer=fuzz.token_sort_ratio, limit=5)
            if matches and matches[0][1] >= 80:
                if len(matches) > 1 and matches[0][1] - matches[1][1] < 10:
                    # Ambiguous — try LLM disambiguation
                    top_matches = [
                        {"name": m[0], "symbol": self.name_to_symbol[m[0]], "score": m[1]}
                        for m in matches[:3]
                    ]
                    resolved = self._llm_disambiguate(name, top_matches, context)
                    if resolved:
                        return self._make_result(resolved, "llm")

                symbol = self.name_to_symbol[matches[0][0]]
                return self._make_result(symbol, "fuzzy")

        # 4. Fuzzy match against symbols themselves
        if self.nse_data:
            symbols = list(self.nse_data.keys())
            matches = process.extract(name.upper(), symbols, scorer=fuzz.ratio, limit=3)
            if matches and matches[0][1] >= 85:
                return self._make_result(matches[0][0], "fuzzy_symbol")

        return None

    def _make_result(self, symbol: str, method: str) -> dict:
        info = self.nse_data.get(symbol, {})
        return {
            "symbol": symbol,
            "nse_ticker": f"{symbol}:NSE",
            "isin": info.get("isin", ""),
            "company_name": info.get("name", ""),
            "method": method,
        }

    def _llm_disambiguate(
        self, raw_name: str, candidates: list[dict], context: str
    ) -> Optional[str]:
        """Use LLM to pick the right ticker from ambiguous candidates."""
        prompt = f"""The speaker mentioned "{raw_name}" in a stock tip video.
Context from the transcript: "{context[:300]}"

Which of these NSE-listed companies are they most likely referring to?
{[f"{c['symbol']} ({c['name']})" for c in candidates]}

Return ONLY a JSON object: {{"symbol": "CHOSEN_SYMBOL"}}
If none match, return {{"symbol": null}}"""

        try:
            result = call_llm_json(
                prompt,
                model="claude-haiku-4-5-20251001",
                max_tokens=128,
            )
            symbol = result.get("symbol")
            if symbol and symbol in self.nse_data:
                return symbol
        except Exception as e:
            logger.debug(f"LLM disambiguation failed: {e}")

        return None


def resolve_tips(
    tips: list[VerifiedTip],
    resolver: Optional[TickerResolver] = None,
) -> list[ResolvedTip]:
    """Resolve all tips to NSE tickers."""
    if resolver is None:
        resolver = TickerResolver()

    resolved: list[ResolvedTip] = []
    for tip in tips:
        rtip = ResolvedTip(**tip.model_dump())

        result = resolver.resolve(
            tip.company_name_raw,
            context=tip.quote_original,
        )
        if result:
            rtip.ticker = result["symbol"]
            rtip.ticker_nse = result["nse_ticker"]
            rtip.isin = result["isin"]
            rtip.resolved = True
            rtip.resolution_method = result["method"]
            logger.debug(
                f"Resolved: {tip.company_name_raw} → {result['symbol']} ({result['method']})"
            )
        else:
            logger.warning(f"Unresolved: {tip.company_name_raw}")

        resolved.append(rtip)

    resolved_count = sum(1 for t in resolved if t.resolved)
    logger.info(f"Resolution: {resolved_count}/{len(resolved)} tips resolved")
    return resolved
