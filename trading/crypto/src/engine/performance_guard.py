"""Per-pair performance guard for the crypto agent swarm.

Adapted from trading/forex/src/engine/performance_guard.py.
Key differences from forex version:
- Uses in-memory order_history list (no journal DB)
- No expectancy guard (needs more trades to be meaningful in crypto)
- PnL in USDT not USD/pip units — thresholds are % of balance
"""
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


PAIR_LOSS_STREAK_LIMIT = int(os.getenv("CRYPTO_PAIR_LOSS_STREAK_LIMIT", "3"))
AGENT_LOSS_STREAK_LIMIT = int(os.getenv("CRYPTO_AGENT_LOSS_STREAK_LIMIT", "2"))
PERFORMANCE_GUARD_COOLDOWN_SECONDS = int(os.getenv("CRYPTO_PERFORMANCE_GUARD_COOLDOWN_SECONDS", "14400"))
RECENT_PAIR_GUARD_ENABLED = str(os.getenv("CRYPTO_RECENT_PAIR_GUARD_ENABLED", "true")).lower() in ("1", "true", "yes", "on")
RECENT_PAIR_LOOKBACK_SECONDS = float(os.getenv("CRYPTO_RECENT_PAIR_LOOKBACK_SECONDS", str(3 * 86400)))
RECENT_PAIR_MIN_TRADES = int(os.getenv("CRYPTO_RECENT_PAIR_MIN_TRADES", "3"))
RECENT_PAIR_NET_PNL_BLOCK_THRESHOLD = float(os.getenv("CRYPTO_RECENT_PAIR_NET_PNL_BLOCK_THRESHOLD", "-15.0"))
RECENT_PAIR_COOLDOWN_SECONDS = int(os.getenv("CRYPTO_RECENT_PAIR_COOLDOWN_SECONDS", "172800"))
MANUAL_PAUSED_PAIRS: set[str] = {
    item.strip()
    for item in os.getenv("CRYPTO_MANUAL_PAUSED_PAIRS", "").split(",")
    if item.strip()
}


@dataclass
class PairPerformanceDecision:
    allowed: bool
    reason: str = ""
    pair_streak: int = 0
    agent_streak: int = 0


def _float(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


class PairPerformanceGuard:
    """Blocks pairs/agents with fresh losing streaks from the in-memory order history."""

    def __init__(
        self,
        pair_loss_limit: int = PAIR_LOSS_STREAK_LIMIT,
        agent_loss_limit: int = AGENT_LOSS_STREAK_LIMIT,
        cooldown_seconds: int = PERFORMANCE_GUARD_COOLDOWN_SECONDS,
    ):
        self.pair_loss_limit = pair_loss_limit
        self.agent_loss_limit = agent_loss_limit
        self.cooldown_seconds = cooldown_seconds
        self._last_summary: Dict[str, Any] = {}

    @staticmethod
    def _closed_rows(history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [row for row in history if row.get("action") == "CLOSE" and row.get("pnl") is not None]

    @staticmethod
    def _loss_streak(rows: List[Dict[str, Any]], key: str, value: str) -> tuple[int, float]:
        streak = 0
        last_ts = 0.0
        for row in sorted(rows, key=lambda r: r.get("timestamp") or 0.0, reverse=True):
            if str(row.get(key) or "") != value:
                continue
            pnl = _float(row.get("pnl"))
            if pnl < 0:
                streak += 1
                if not last_ts:
                    last_ts = float(row.get("timestamp") or 0.0)
                continue
            break
        return streak, last_ts

    @staticmethod
    def _recent_pair_stats(rows: List[Dict[str, Any]], now: float) -> Dict[str, Dict[str, Any]]:
        cutoff = now - RECENT_PAIR_LOOKBACK_SECONDS
        stats: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            symbol = str(row.get("symbol") or "")
            ts = float(row.get("timestamp") or 0.0)
            if not symbol or ts < cutoff:
                continue
            bucket = stats.setdefault(symbol, {"trades": 0, "wins": 0, "losses": 0, "net_pnl": 0.0, "last_ts": 0.0})
            pnl = _float(row.get("pnl"))
            bucket["trades"] += 1
            bucket["net_pnl"] = round(bucket["net_pnl"] + pnl, 4)
            bucket["last_ts"] = max(bucket["last_ts"], ts)
            if pnl > 0:
                bucket["wins"] += 1
            else:
                bucket["losses"] += 1
        return stats

    def evaluate(self, symbol: str, agent: str, order_history: List[Dict[str, Any]], now: Optional[float] = None) -> PairPerformanceDecision:
        now = now or time.time()
        if symbol in MANUAL_PAUSED_PAIRS:
            return PairPerformanceDecision(False, f"{symbol} manually paused")

        rows = self._closed_rows(order_history)

        pair_streak, last_ts = self._loss_streak(rows, "symbol", symbol)
        if pair_streak >= self.pair_loss_limit:
            remaining = int(self.cooldown_seconds - max(now - last_ts, 0)) if last_ts else 0
            if remaining > 0:
                return PairPerformanceDecision(False, f"{symbol} loss streak {pair_streak} >= {self.pair_loss_limit}; cooldown {remaining}s", pair_streak=pair_streak)

        if RECENT_PAIR_GUARD_ENABLED:
            recent = self._recent_pair_stats(rows, now)
            stat = recent.get(symbol)
            if stat and stat["trades"] >= RECENT_PAIR_MIN_TRADES and stat["net_pnl"] <= RECENT_PAIR_NET_PNL_BLOCK_THRESHOLD:
                remaining = int(RECENT_PAIR_COOLDOWN_SECONDS - max(now - stat["last_ts"], 0)) if stat["last_ts"] else 0
                if remaining > 0:
                    return PairPerformanceDecision(
                        False,
                        f"{symbol} recent net PnL {stat['net_pnl']:.2f} <= {RECENT_PAIR_NET_PNL_BLOCK_THRESHOLD:.2f} over {RECENT_PAIR_LOOKBACK_SECONDS/86400:g}d; cooldown {remaining}s",
                    )

        agent_streak, last_ts = self._loss_streak(rows, "agent", agent)
        if agent_streak >= self.agent_loss_limit:
            remaining = int(self.cooldown_seconds - max(now - last_ts, 0)) if last_ts else 0
            if remaining > 0:
                return PairPerformanceDecision(False, f"{agent} loss streak {agent_streak} >= {self.agent_loss_limit}; cooldown {remaining}s", agent_streak=agent_streak)

        return PairPerformanceDecision(True)

    def summary(self, order_history: List[Dict[str, Any]], now: Optional[float] = None) -> Dict[str, Any]:
        now = now or time.time()
        rows = self._closed_rows(order_history)
        recent = self._recent_pair_stats(rows, now) if RECENT_PAIR_GUARD_ENABLED else {}
        self._last_summary = {
            "pair_loss_limit": self.pair_loss_limit,
            "agent_loss_limit": self.agent_loss_limit,
            "cooldown_seconds": self.cooldown_seconds,
            "manual_paused_pairs": sorted(MANUAL_PAUSED_PAIRS),
            "recent_pair_guard_enabled": RECENT_PAIR_GUARD_ENABLED,
            "recent_pair_stats": recent,
        }
        return self._last_summary
