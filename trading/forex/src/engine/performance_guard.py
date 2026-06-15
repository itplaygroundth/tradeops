import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


SYMBOL_LOSS_STREAK_LIMIT = int(os.getenv("SYMBOL_LOSS_STREAK_LIMIT", "3"))
AGENT_LOSS_STREAK_LIMIT = int(os.getenv("AGENT_LOSS_STREAK_LIMIT", "2"))
PERFORMANCE_GUARD_LOOKBACK = int(os.getenv("PERFORMANCE_GUARD_LOOKBACK", "200"))
PERFORMANCE_GUARD_COOLDOWN_SECONDS = int(os.getenv("PERFORMANCE_GUARD_COOLDOWN_SECONDS", "14400"))
EXPECTANCY_SYMBOL_GUARD_ENABLED = str(os.getenv("EXPECTANCY_SYMBOL_GUARD_ENABLED", "true")).lower() in ("1", "true", "yes", "on")
EXPECTANCY_SYMBOL_MIN_TRADES = int(os.getenv("EXPECTANCY_SYMBOL_MIN_TRADES", "10"))
EXPECTANCY_SYMBOL_BLOCK_THRESHOLD = float(os.getenv("EXPECTANCY_SYMBOL_BLOCK_THRESHOLD", "-0.10"))
# Expectancy block must expire, otherwise a paused symbol can never trade again
# (no new trades -> losses never age out of the lookback -> permanent ban).
# After this cooldown elapses since the symbol's last closed trade, allow a
# probation trade so its expectancy can refresh.
EXPECTANCY_SYMBOL_COOLDOWN_SECONDS = int(os.getenv("EXPECTANCY_SYMBOL_COOLDOWN_SECONDS", "14400"))
RECENT_SYMBOL_GUARD_ENABLED = str(os.getenv("RECENT_SYMBOL_GUARD_ENABLED", "true")).lower() in ("1", "true", "yes", "on")
RECENT_SYMBOL_LOOKBACK_DAYS = float(os.getenv("RECENT_SYMBOL_LOOKBACK_DAYS", "3"))
RECENT_SYMBOL_MIN_TRADES = int(os.getenv("RECENT_SYMBOL_MIN_TRADES", "3"))
RECENT_SYMBOL_NET_PNL_BLOCK_THRESHOLD = float(os.getenv("RECENT_SYMBOL_NET_PNL_BLOCK_THRESHOLD", "-5"))
RECENT_SYMBOL_COOLDOWN_SECONDS = int(os.getenv("RECENT_SYMBOL_COOLDOWN_SECONDS", "172800"))
MANUAL_PAUSED_SYMBOLS = {
    item.strip()
    for item in os.getenv("MANUAL_PAUSED_SYMBOLS", "AUDUSDm").split(",")
    if item.strip()
}


@dataclass
class PerformanceDecision:
    allowed: bool
    reason: str = ""
    symbol_streak: int = 0
    agent_streak: int = 0


def _float(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _parse_utc(value: Any) -> float:
    if not value:
        return 0.0
    try:
        text = str(value)
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text).timestamp()
    except Exception:
        return 0.0


class PerformanceGuard:
    """Blocks symbols/agents with fresh losing streaks from the realized journal."""

    def __init__(
        self,
        symbol_loss_limit: int = SYMBOL_LOSS_STREAK_LIMIT,
        agent_loss_limit: int = AGENT_LOSS_STREAK_LIMIT,
        cooldown_seconds: int = PERFORMANCE_GUARD_COOLDOWN_SECONDS,
        lookback: int = PERFORMANCE_GUARD_LOOKBACK,
    ):
        self.symbol_loss_limit = symbol_loss_limit
        self.agent_loss_limit = agent_loss_limit
        self.cooldown_seconds = cooldown_seconds
        self.lookback = lookback
        self._last_summary: Dict[str, Any] = {
            "paused_symbols": {},
            "paused_agents": {},
            "expectancy_blocked_symbols": {},
            "recent_blocked_symbols": {},
            "manual_paused_symbols": sorted(MANUAL_PAUSED_SYMBOLS),
            "symbol_stats": {},
            "agent_stats": {},
        }

    def _load_journal(self) -> List[Dict[str, Any]]:
        try:
            from storage.history_db import query_orders_for_export
            from storage.trading_journal import build_institutional_journal
            orders = query_orders_for_export(limit=self.lookback)
            return build_institutional_journal(orders)
        except Exception:
            return []

    @staticmethod
    def _closed_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [
            row for row in rows
            if str(row.get("lifecycle_status") or "").upper() == "CLOSED"
            and row.get("net_pnl") not in (None, "")
        ]

    @staticmethod
    def _stats(rows: List[Dict[str, Any]], key: str) -> Dict[str, Dict[str, Any]]:
        stats: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            name = str(row.get(key) or "")
            if not name:
                continue
            bucket = stats.setdefault(name, {"closed": 0, "wins": 0, "losses": 0, "net_pnl": 0.0})
            pnl = _float(row.get("net_pnl"))
            bucket["closed"] += 1
            bucket["net_pnl"] = round(bucket["net_pnl"] + pnl, 2)
            if pnl > 0:
                bucket["wins"] += 1
            elif pnl < 0:
                bucket["losses"] += 1
        for bucket in stats.values():
            closed = bucket["closed"]
            bucket["win_rate"] = round((bucket["wins"] / closed * 100.0) if closed else 0.0, 1)
        return stats

    @staticmethod
    def _loss_streak(rows: List[Dict[str, Any]], key: str, value: str) -> tuple[int, float]:
        streak = 0
        last_ts = 0.0
        for row in sorted(rows, key=lambda item: item.get("exit_time_utc") or "", reverse=True):
            if str(row.get(key) or "") != value:
                continue
            pnl = _float(row.get("net_pnl"))
            if pnl < 0:
                streak += 1
                if not last_ts:
                    last_ts = _parse_utc(row.get("exit_time_utc"))
                continue
            break
        return streak, last_ts

    @staticmethod
    def _last_trade_ts(rows: List[Dict[str, Any]], symbol: str) -> float:
        last_ts = 0.0
        for row in rows:
            if str(row.get("symbol") or "") != symbol:
                continue
            last_ts = max(last_ts, _parse_utc(row.get("exit_time_utc")))
        return last_ts

    @staticmethod
    def _recent_symbol_stats(rows: List[Dict[str, Any]], now: float) -> Dict[str, Dict[str, Any]]:
        cutoff = now - (RECENT_SYMBOL_LOOKBACK_DAYS * 86400)
        stats: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            symbol = str(row.get("symbol") or "")
            if not symbol:
                continue
            ts = _parse_utc(row.get("exit_time_utc"))
            if not ts or ts < cutoff:
                continue
            bucket = stats.setdefault(symbol, {
                "trades": 0,
                "wins": 0,
                "losses": 0,
                "net_pnl": 0.0,
                "last_trade_ts": 0.0,
            })
            pnl = _float(row.get("net_pnl"))
            bucket["trades"] += 1
            bucket["net_pnl"] = round(bucket["net_pnl"] + pnl, 2)
            bucket["last_trade_ts"] = max(bucket["last_trade_ts"], ts)
            if pnl > 0:
                bucket["wins"] += 1
            elif pnl < 0:
                bucket["losses"] += 1
        for bucket in stats.values():
            trades = bucket["trades"]
            bucket["win_rate"] = round((bucket["wins"] / trades * 100.0) if trades else 0.0, 1)
        return stats

    def refresh(self, now: Optional[float] = None) -> Dict[str, Any]:
        now = now or datetime.now(tz=timezone.utc).timestamp()
        rows = self._closed_rows(self._load_journal())
        symbol_stats = self._stats(rows, "symbol")
        agent_stats = self._stats(rows, "agent")
        paused_symbols = {}
        paused_agents = {}
        expectancy_blocked_symbols = {}
        recent_blocked_symbols = {}

        for symbol in symbol_stats:
            streak, last_ts = self._loss_streak(rows, "symbol", symbol)
            remaining = int(self.cooldown_seconds - max(now - last_ts, 0)) if last_ts else 0
            if streak >= self.symbol_loss_limit and remaining > 0:
                paused_symbols[symbol] = {
                    "loss_streak": streak,
                    "cooldown_remaining_seconds": remaining,
                    "reason": f"{symbol} loss streak {streak} >= {self.symbol_loss_limit}",
                }

        for agent in agent_stats:
            streak, last_ts = self._loss_streak(rows, "agent", agent)
            remaining = int(self.cooldown_seconds - max(now - last_ts, 0)) if last_ts else 0
            if streak >= self.agent_loss_limit and remaining > 0:
                paused_agents[agent] = {
                    "loss_streak": streak,
                    "cooldown_remaining_seconds": remaining,
                    "reason": f"{agent} loss streak {streak} >= {self.agent_loss_limit}",
                }

        recent_symbol_stats = self._recent_symbol_stats(rows, now) if RECENT_SYMBOL_GUARD_ENABLED else {}
        for symbol, stats in recent_symbol_stats.items():
            if (
                int(stats.get("trades") or 0) >= RECENT_SYMBOL_MIN_TRADES
                and float(stats.get("net_pnl") or 0.0) <= RECENT_SYMBOL_NET_PNL_BLOCK_THRESHOLD
            ):
                last_ts = float(stats.get("last_trade_ts") or 0.0)
                remaining = int(RECENT_SYMBOL_COOLDOWN_SECONDS - max(now - last_ts, 0)) if last_ts else 0
                if remaining <= 0:
                    continue
                recent_blocked_symbols[symbol] = {
                    "trades": stats.get("trades"),
                    "wins": stats.get("wins"),
                    "losses": stats.get("losses"),
                    "win_rate": stats.get("win_rate"),
                    "net_pnl": stats.get("net_pnl"),
                    "cooldown_remaining_seconds": remaining,
                    "reason": (
                        f"{symbol} recent net PnL {float(stats.get('net_pnl') or 0.0):.2f} "
                        f"<= {RECENT_SYMBOL_NET_PNL_BLOCK_THRESHOLD:.2f} over "
                        f"{RECENT_SYMBOL_LOOKBACK_DAYS:g}d"
                    ),
                }

        if EXPECTANCY_SYMBOL_GUARD_ENABLED:
            try:
                from storage.journal_analysis import analyze_journal
                analysis = analyze_journal(rows, min_trades=EXPECTANCY_SYMBOL_MIN_TRADES)
                for symbol, stats in analysis.get("by_symbol", {}).items():
                    if (
                        int(stats.get("trades") or 0) >= EXPECTANCY_SYMBOL_MIN_TRADES
                        and float(stats.get("expectancy") or 0.0) <= EXPECTANCY_SYMBOL_BLOCK_THRESHOLD
                    ):
                        # Skip the block once the cooldown since the last trade has
                        # elapsed, so the symbol gets a probation trade to recover.
                        last_ts = self._last_trade_ts(rows, symbol)
                        if last_ts and (now - last_ts) >= EXPECTANCY_SYMBOL_COOLDOWN_SECONDS:
                            continue
                        expectancy_blocked_symbols[symbol] = {
                            "trades": stats.get("trades"),
                            "expectancy": stats.get("expectancy"),
                            "win_rate": stats.get("win_rate"),
                            "net_pnl": stats.get("net_pnl"),
                            "reason": (
                                f"{symbol} expectancy {float(stats.get('expectancy') or 0.0):.4f} "
                                f"<= {EXPECTANCY_SYMBOL_BLOCK_THRESHOLD:.4f}"
                            ),
                        }
            except Exception:
                expectancy_blocked_symbols = {}

        self._last_summary = {
            "paused_symbols": paused_symbols,
            "paused_agents": paused_agents,
            "expectancy_blocked_symbols": expectancy_blocked_symbols,
            "recent_blocked_symbols": recent_blocked_symbols,
            "manual_paused_symbols": sorted(MANUAL_PAUSED_SYMBOLS),
            "symbol_stats": symbol_stats,
            "agent_stats": agent_stats,
            "recent_symbol_stats": recent_symbol_stats,
            "cooldown_seconds": self.cooldown_seconds,
            "recent_guard": {
                "enabled": RECENT_SYMBOL_GUARD_ENABLED,
                "lookback_days": RECENT_SYMBOL_LOOKBACK_DAYS,
                "min_trades": RECENT_SYMBOL_MIN_TRADES,
                "net_pnl_block_threshold": RECENT_SYMBOL_NET_PNL_BLOCK_THRESHOLD,
                "cooldown_seconds": RECENT_SYMBOL_COOLDOWN_SECONDS,
            },
            "expectancy_guard": {
                "enabled": EXPECTANCY_SYMBOL_GUARD_ENABLED,
                "min_trades": EXPECTANCY_SYMBOL_MIN_TRADES,
                "block_threshold": EXPECTANCY_SYMBOL_BLOCK_THRESHOLD,
            },
        }
        return self._last_summary

    def evaluate(self, symbol: str, agent: str, now: Optional[float] = None) -> PerformanceDecision:
        summary = self.refresh(now=now)
        if symbol in MANUAL_PAUSED_SYMBOLS:
            return PerformanceDecision(False, f"{symbol} manually paused")
        symbol_pause = summary["paused_symbols"].get(symbol)
        if symbol_pause:
            return PerformanceDecision(False, symbol_pause["reason"], symbol_streak=symbol_pause["loss_streak"])
        recent_pause = summary.get("recent_blocked_symbols", {}).get(symbol)
        if recent_pause:
            return PerformanceDecision(False, recent_pause["reason"])
        expectancy_pause = summary.get("expectancy_blocked_symbols", {}).get(symbol)
        if expectancy_pause:
            return PerformanceDecision(False, expectancy_pause["reason"])
        agent_pause = summary["paused_agents"].get(agent)
        if agent_pause:
            return PerformanceDecision(False, agent_pause["reason"], agent_streak=agent_pause["loss_streak"])
        return PerformanceDecision(True)

    def summary(self) -> Dict[str, Any]:
        return self._last_summary
