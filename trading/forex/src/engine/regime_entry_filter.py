"""Regime-based entry filter — blocks entries for symbols in unfavorable regimes.

Evidence-backed (b99c40fb): XAUUSDm had -50.41 net PnL, expectancy -1.867, PF 0.782
across 27 trades. Primary losses came from SL hits in trending regimes where
mean-reversion/grid strategies were active.
"""
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class RegimeFilterDecision:
    allowed: bool
    reason: str = ""


class RegimeEntryFilter:
    """Blocks entries for symbol/regime combinations with proven negative edge."""

    # Default configuration — can be overridden via env or constructor
    DEFAULT_BLOCKED: Dict[str, list[str]] = {
        "XAUUSDm": ["TRENDING_UP", "TRENDING_DOWN"],  # trend strategies fail on XAU
        # Add more symbol: [regime] pairs as evidence accumulates
    }

    def __init__(
        self,
        enabled: bool = True,
        blocked: Optional[Dict[str, list[str]]] = None,
    ):
        self.enabled = enabled
        # Normalize blocked dict keys to uppercase for case-insensitive matching
        self.blocked = {k.upper(): [r.upper() for r in v] for k, v in (blocked or self.DEFAULT_BLOCKED).items()}

    def evaluate(self, symbol: str, regime: str) -> RegimeFilterDecision:
        if not self.enabled:
            return RegimeFilterDecision(True)
        if not symbol or not regime:
            return RegimeFilterDecision(True)

        blocked_regimes = self.blocked.get(symbol.upper(), [])
        if regime.upper() in blocked_regimes:
            return RegimeFilterDecision(
                False,
                f"{symbol} entries blocked in {regime} regime (negative expectancy evidence)",
            )
        return RegimeFilterDecision(True)

    def summary(self) -> dict:
        return {
            "enabled": self.enabled,
            "blocked_pairs": self.blocked,
        }
