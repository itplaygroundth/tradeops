"""Position dedup guard for the crypto agent swarm.

Adapted from trading/forex/src/engine/position_dedup_guard.py.
Key differences from forex version:
- No MT5 managed_magic filter — uses agent is_in_trade state directly
- Positions are dicts from get_open_positions() with {symbol, side} keys
- No DB lookup (crypto uses in-memory position tracking)
"""
import os
import time
from dataclasses import dataclass
from typing import Dict, List, Optional


MAX_POSITIONS_PER_PAIR = int(os.getenv("CRYPTO_MAX_POSITIONS_PER_PAIR", "1"))
MAX_POSITIONS_PER_PAIR_SIDE = int(os.getenv("CRYPTO_MAX_POSITIONS_PER_PAIR_SIDE", "1"))
POSITION_COOLDOWN_SECONDS = int(os.getenv("CRYPTO_POSITION_COOLDOWN_SECONDS", "900"))
ALLOW_HEDGE_SAME_PAIR = str(os.getenv("CRYPTO_ALLOW_HEDGE_SAME_PAIR", "false")).lower() in ("1", "true", "yes", "on")


@dataclass
class DedupDecision:
    allowed: bool
    reason: str = ""
    pair_positions: int = 0
    same_side_positions: int = 0
    opposite_side_positions: int = 0
    cooldown_remaining_seconds: int = 0


class PositionDedupGuard:
    """Prevents duplicate live entries by pair, side, and recent open cooldown."""

    def __init__(
        self,
        max_per_pair: int = MAX_POSITIONS_PER_PAIR,
        max_per_pair_side: int = MAX_POSITIONS_PER_PAIR_SIDE,
        cooldown_seconds: int = POSITION_COOLDOWN_SECONDS,
        allow_hedge: bool = ALLOW_HEDGE_SAME_PAIR,
    ):
        self.max_per_pair = max_per_pair
        self.max_per_pair_side = max_per_pair_side
        self.cooldown_seconds = cooldown_seconds
        self.allow_hedge = allow_hedge
        self._last_open_by_symbol: Dict[str, float] = {}

    def evaluate(
        self,
        symbol: str,
        side: str,
        open_positions: List[dict],
        now: Optional[float] = None,
        max_per_pair: Optional[int] = None,
        max_per_pair_side: Optional[int] = None,
        cooldown_seconds: Optional[int] = None,
    ) -> DedupDecision:
        now = now or time.time()
        side = str(side or "").upper()
        max_pair = self.max_per_pair if max_per_pair is None else int(max_per_pair)
        max_side = self.max_per_pair_side if max_per_pair_side is None else int(max_per_pair_side)
        cooldown = self.cooldown_seconds if cooldown_seconds is None else int(cooldown_seconds)

        active = [p for p in open_positions if p.get("symbol") == symbol]
        same_side = [p for p in active if str(p.get("side") or p.get("action") or "").upper() == side]
        opposite_side = [p for p in active if str(p.get("side") or p.get("action") or "").upper() not in ("", side)]

        last_open = self._last_open_by_symbol.get(symbol)
        if last_open:
            remaining = int(cooldown - max(now - last_open, 0))
            if remaining > 0:
                return DedupDecision(False, f"{symbol} cooldown {remaining}s after recent open", len(active), len(same_side), len(opposite_side), remaining)

        if len(active) >= max_pair:
            return DedupDecision(False, f"{symbol} already has {len(active)} position(s); max {max_pair}", len(active), len(same_side), len(opposite_side))

        if len(same_side) >= max_side:
            return DedupDecision(False, f"{symbol} {side} already has {len(same_side)} position(s); max {max_side}", len(active), len(same_side), len(opposite_side))

        if opposite_side and not self.allow_hedge:
            return DedupDecision(False, f"{symbol} has opposite-side position; hedge disabled", len(active), len(same_side), len(opposite_side))

        return DedupDecision(True, pair_positions=len(active), same_side_positions=len(same_side), opposite_side_positions=len(opposite_side))

    def record_open(self, symbol: str, now: Optional[float] = None) -> None:
        self._last_open_by_symbol[symbol] = now or time.time()

    def summary(self) -> dict:
        return {
            "max_per_pair": self.max_per_pair,
            "max_per_pair_side": self.max_per_pair_side,
            "cooldown_seconds": self.cooldown_seconds,
            "allow_hedge": self.allow_hedge,
            "last_open_by_symbol": dict(self._last_open_by_symbol),
        }
