"""Strategy-level performance guard for the crypto agent swarm."""
import os
import time
from collections import deque
from dataclasses import dataclass


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class StrategyGuardDecision:
    allowed: bool
    reason: str = ""
    cooldown_remaining_seconds: int = 0


class StrategyPerformanceGuard:
    """Pause strategies whose recent closed trades show persistent loss."""

    def __init__(
        self,
        enabled: bool | None = None,
        min_trades: int | None = None,
        loss_streak: int | None = None,
        min_expectancy: float | None = None,
        cooldown_seconds: int | None = None,
        history_limit: int = 50,
    ):
        self.enabled = _env_bool("STRATEGY_GUARD_ENABLED", True) if enabled is None else enabled
        self.min_trades = min_trades if min_trades is not None else _env_int("STRATEGY_GUARD_MIN_TRADES", 3)
        self.loss_streak = loss_streak if loss_streak is not None else _env_int("STRATEGY_GUARD_LOSS_STREAK", 3)
        self.min_expectancy = (
            min_expectancy
            if min_expectancy is not None
            else _env_float("STRATEGY_GUARD_MIN_EXPECTANCY", -0.10)
        )
        self.cooldown_seconds = (
            cooldown_seconds
            if cooldown_seconds is not None
            else _env_int("STRATEGY_GUARD_COOLDOWN_SECONDS", 14400)
        )
        self._history_limit = history_limit
        self._stats: dict[str, dict] = {}

    def record(self, strategy: str, pnl: float, now: float | None = None) -> None:
        if not strategy:
            return
        ts = time.time() if now is None else now
        stat = self._stats.setdefault(
            strategy,
            {
                "trades": 0,
                "wins": 0,
                "losses": 0,
                "loss_streak": 0,
                "total_pnl": 0.0,
                "last_closed_at": 0.0,
                "recent": deque(maxlen=self._history_limit),
            },
        )
        pnl = float(pnl)
        stat["trades"] += 1
        stat["total_pnl"] += pnl
        stat["last_closed_at"] = ts
        stat["recent"].append(pnl)
        if pnl > 0:
            stat["wins"] += 1
            stat["loss_streak"] = 0
        else:
            stat["losses"] += 1
            stat["loss_streak"] += 1

    def evaluate(self, strategy: str, now: float | None = None) -> StrategyGuardDecision:
        if not self.enabled or not strategy:
            return StrategyGuardDecision(True)
        stat = self._stats.get(strategy)
        if not stat:
            return StrategyGuardDecision(True)
        reason = self._blocked_reason(stat)
        if not reason:
            return StrategyGuardDecision(True)

        ts = time.time() if now is None else now
        elapsed = max(0.0, ts - stat["last_closed_at"])
        remaining = int(max(0.0, self.cooldown_seconds - elapsed))
        if remaining <= 0:
            return StrategyGuardDecision(True)
        return StrategyGuardDecision(False, reason, remaining)

    def summary(self, now: float | None = None) -> dict:
        ts = time.time() if now is None else now
        strategies = {}
        for strategy, stat in self._stats.items():
            decision = self.evaluate(strategy, ts)
            trades = stat["trades"]
            strategies[strategy] = {
                "allowed": decision.allowed,
                "reason": decision.reason,
                "cooldown_remaining_seconds": decision.cooldown_remaining_seconds,
                "trades": trades,
                "wins": stat["wins"],
                "losses": stat["losses"],
                "loss_streak": stat["loss_streak"],
                "total_pnl": round(stat["total_pnl"], 2),
                "expectancy": round(stat["total_pnl"] / trades, 4) if trades else 0.0,
            }
        return {
            "enabled": self.enabled,
            "guard_mode": self.guard_mode(ts),
            "min_trades": self.min_trades,
            "loss_streak": self.loss_streak,
            "min_expectancy": self.min_expectancy,
            "cooldown_seconds": self.cooldown_seconds,
            "strategies": strategies,
        }

    def guard_mode(self, now: float | None = None) -> str:
        if not self.enabled:
            return "NORMAL"
        total_pnl = sum(float(stat.get("total_pnl") or 0.0) for stat in self._stats.values())
        max_streak = max((int(stat.get("loss_streak") or 0) for stat in self._stats.values()), default=0)
        any_blocked = any(not self.evaluate(strategy, now).allowed for strategy in self._stats)
        if total_pnl <= -40 or max_streak >= 5:
            return "HARD_STOP"
        if any_blocked or total_pnl <= -20 or max_streak >= 3:
            return "DEFENSE"
        if total_pnl <= -10 or max_streak >= 2:
            return "CAUTION"
        return "NORMAL"

    def _blocked_reason(self, stat: dict) -> str:
        if stat["loss_streak"] >= self.loss_streak:
            return f"loss streak {stat['loss_streak']} >= {self.loss_streak}"
        if stat["trades"] >= self.min_trades:
            expectancy = stat["total_pnl"] / stat["trades"]
            if expectancy <= self.min_expectancy:
                return f"expectancy {expectancy:.4f} <= {self.min_expectancy:.4f}"
        return ""
