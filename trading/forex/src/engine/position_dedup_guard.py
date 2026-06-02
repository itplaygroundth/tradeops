import os
import time
from dataclasses import dataclass
from typing import Dict, List, Optional


MAX_POSITIONS_PER_SYMBOL = int(os.getenv("MAX_POSITIONS_PER_SYMBOL", "1"))
MAX_POSITIONS_PER_SYMBOL_SIDE = int(os.getenv("MAX_POSITIONS_PER_SYMBOL_SIDE", "1"))
POSITION_COOLDOWN_SECONDS = int(os.getenv("POSITION_COOLDOWN_SECONDS", "900"))
ALLOW_HEDGE_SAME_SYMBOL = str(os.getenv("ALLOW_HEDGE_SAME_SYMBOL", "false")).lower() in ("1", "true", "yes", "on")
MANAGED_MAGIC = int(os.getenv("MTAI_MAGIC", "20260101"))


@dataclass
class DedupDecision:
    allowed: bool
    reason: str = ""
    symbol_positions: int = 0
    same_side_positions: int = 0
    opposite_side_positions: int = 0
    cooldown_remaining_seconds: int = 0


class PositionDedupGuard:
    """Prevents duplicate live entries by symbol, side, and recent open cooldown."""

    def __init__(
        self,
        max_per_symbol: int = MAX_POSITIONS_PER_SYMBOL,
        max_per_symbol_side: int = MAX_POSITIONS_PER_SYMBOL_SIDE,
        cooldown_seconds: int = POSITION_COOLDOWN_SECONDS,
        allow_hedge: bool = ALLOW_HEDGE_SAME_SYMBOL,
        managed_magic: int = MANAGED_MAGIC,
    ):
        self.max_per_symbol = max_per_symbol
        self.max_per_symbol_side = max_per_symbol_side
        self.cooldown_seconds = cooldown_seconds
        self.allow_hedge = allow_hedge
        self.managed_magic = managed_magic
        self._last_open_by_symbol: Dict[str, float] = {}
        self._last_summary: Dict[str, object] = {
            "max_per_symbol": max_per_symbol,
            "max_per_symbol_side": max_per_symbol_side,
            "cooldown_seconds": cooldown_seconds,
            "allow_hedge": allow_hedge,
            "last_open_by_symbol": {},
        }

    @staticmethod
    def _side(pos: dict) -> str:
        side = pos.get("type")
        if side == 0:
            return "BUY"
        if side == 1:
            return "SELL"
        return str(side or "").upper()

    def _managed_positions(self, positions: List[dict]) -> List[dict]:
        managed = []
        for pos in positions:
            try:
                magic = int(pos.get("magic") or 0)
            except Exception:
                magic = 0
            if magic == self.managed_magic:
                managed.append(pos)
        return managed

    def evaluate(
        self,
        symbol: str,
        side: str,
        positions: List[dict],
        now: Optional[float] = None,
    ) -> DedupDecision:
        now = now or time.time()
        side = str(side or "").upper()
        active = [pos for pos in self._managed_positions(positions) if pos.get("symbol") == symbol]
        same_side = [pos for pos in active if self._side(pos) == side]
        opposite_side = [pos for pos in active if self._side(pos) and self._side(pos) != side]

        last_open = self._last_open_by_symbol.get(symbol)
        cooldown_remaining = 0
        if last_open:
            cooldown_remaining = int(self.cooldown_seconds - max(now - last_open, 0))
            if cooldown_remaining > 0:
                return DedupDecision(
                    False,
                    f"{symbol} cooldown {cooldown_remaining}s after recent open",
                    len(active),
                    len(same_side),
                    len(opposite_side),
                    cooldown_remaining,
                )

        if len(active) >= self.max_per_symbol:
            return DedupDecision(
                False,
                f"{symbol} already has {len(active)} managed position(s); max {self.max_per_symbol}",
                len(active),
                len(same_side),
                len(opposite_side),
            )

        if len(same_side) >= self.max_per_symbol_side:
            return DedupDecision(
                False,
                f"{symbol} {side} already has {len(same_side)} managed position(s); max {self.max_per_symbol_side}",
                len(active),
                len(same_side),
                len(opposite_side),
            )

        if opposite_side and not self.allow_hedge:
            return DedupDecision(
                False,
                f"{symbol} has opposite-side managed position; hedge disabled",
                len(active),
                len(same_side),
                len(opposite_side),
            )

        return DedupDecision(True, symbol_positions=len(active), same_side_positions=len(same_side), opposite_side_positions=len(opposite_side))

    def record_open(self, symbol: str, now: Optional[float] = None):
        self._last_open_by_symbol[symbol] = now or time.time()

    def summary(self) -> Dict[str, object]:
        self._last_summary = {
            "max_per_symbol": self.max_per_symbol,
            "max_per_symbol_side": self.max_per_symbol_side,
            "cooldown_seconds": self.cooldown_seconds,
            "allow_hedge": self.allow_hedge,
            "last_open_by_symbol": dict(self._last_open_by_symbol),
        }
        return self._last_summary
