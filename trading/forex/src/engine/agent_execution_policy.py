"""
Agent execution permission policy.

The manager may run many agents as signal candidates, but only a small,
deterministic set should be allowed to place real orders for each symbol.
"""
import os
from dataclasses import dataclass
from typing import Dict, List


DEFAULT_STRATEGY_PREFERENCE = [
    "momentum",
    "breakout_atr",
    "market_structure",
    "order_flow",
    "session_open",
    "grid_scalp",
    "mean_reversion",
    "llm_sentiment",
]

SYMBOL_TIMEFRAME_BIAS = {
    "EURUSDm": "M15",
    "GBPUSDm": "M15",
    "USDJPYm": "H1",
    "XAUUSDm": "H1",
    "AUDUSDm": "H1",
    "USDCADm": "H1",
    "USDCHFm": "H1",
    "NZDUSDm": "H4",
}


@dataclass
class AgentPermission:
    allowed: bool
    role: str
    reason: str
    score: float = 0.0

    def to_dict(self) -> Dict:
        return {
            "allowed": self.allowed,
            "role": self.role,
            "reason": self.reason,
            "score": round(self.score, 4),
        }


class AgentExecutionPolicy:
    def __init__(self):
        self.enabled = str(os.getenv("AGENT_EXECUTION_POLICY_ENABLED", "true")).lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        self.executors_per_symbol = max(1, int(os.getenv("AGENT_EXECUTORS_PER_SYMBOL", "1")))
        raw_preference = os.getenv("AGENT_EXECUTOR_STRATEGY_PREFERENCE", "")
        self.strategy_preference = [
            item.strip()
            for item in raw_preference.split(",")
            if item.strip()
        ] or list(DEFAULT_STRATEGY_PREFERENCE)
        self._last_by_symbol: Dict[str, Dict] = {}

    def select(self, symbol: str, agents: List, max_agents: int = 1) -> Dict:
        if not agents:
            entry = {
                "symbol": symbol,
                "enabled": self.enabled,
                "executor_limit": 0,
                "executors": [],
                "observers": [],
            }
            self._last_by_symbol[symbol] = entry
            return entry

        if not self.enabled:
            limit = max(1, int(max_agents or len(agents)))
        else:
            limit = min(max(1, int(max_agents or 1)), self.executors_per_symbol)

        ranked = sorted(agents, key=lambda agent: self._score_tuple(agent), reverse=True)
        executors = ranked[:limit]
        executor_names = {agent.dna.name for agent in executors}
        permissions = {}
        for agent in ranked:
            score = self.score(agent)
            if agent.dna.name in executor_names:
                permissions[agent.dna.name] = AgentPermission(
                    allowed=True,
                    role="executor",
                    reason=f"selected top {limit} execution candidate for {symbol}",
                    score=score,
                )
            else:
                permissions[agent.dna.name] = AgentPermission(
                    allowed=False,
                    role="observer",
                    reason="observer only; execution delegated to selected agent",
                    score=score,
                )

        entry = {
            "symbol": symbol,
            "enabled": self.enabled,
            "executor_limit": limit,
            "executors": [self.agent_summary(agent, permissions[agent.dna.name]) for agent in executors],
            "observers": [
                self.agent_summary(agent, permissions[agent.dna.name])
                for agent in ranked
                if agent.dna.name not in executor_names
            ],
            "permissions": {name: perm.to_dict() for name, perm in permissions.items()},
        }
        self._last_by_symbol[symbol] = entry
        return entry

    def permission_for(self, selection: Dict, agent) -> AgentPermission:
        raw = (selection.get("permissions") or {}).get(agent.dna.name)
        if not raw:
            return AgentPermission(False, "observer", "not selected for execution", self.score(agent))
        return AgentPermission(
            bool(raw.get("allowed")),
            str(raw.get("role") or "observer"),
            str(raw.get("reason") or ""),
            float(raw.get("score") or 0.0),
        )

    def agent_summary(self, agent, permission: AgentPermission) -> Dict:
        return {
            "name": agent.dna.name,
            "symbol": agent.dna.symbol,
            "role": permission.role,
            "score": round(permission.score, 4),
            "timeframe": agent.dna.timeframe,
            "preferred_timeframe": SYMBOL_TIMEFRAME_BIAS.get(agent.dna.symbol, "H1"),
            "strategy": self._dominant_strategy(agent),
            "trades": getattr(agent, "trades_count", 0),
            "win_rate": round(getattr(agent, "win_rate", 0.0) * 100, 1),
            "total_pnl": round(getattr(agent, "total_pnl", 0.0), 2),
            "consecutive_losses": int(getattr(agent, "_consecutive_losses", 0) or 0),
            "reason": permission.reason,
        }

    def score(self, agent) -> float:
        score, _ = self._score_tuple(agent)
        return score

    def _score_tuple(self, agent):
        dominant = self._dominant_strategy(agent)
        preferred_tf = SYMBOL_TIMEFRAME_BIAS.get(agent.dna.symbol, "H1")
        strategy_rank = self.strategy_preference.index(dominant) if dominant in self.strategy_preference else len(self.strategy_preference)
        strategy_score = max(0, len(self.strategy_preference) - strategy_rank) * 0.25
        timeframe_score = 3.0 if agent.dna.timeframe == preferred_tf else 0.0
        win_score = float(getattr(agent, "win_rate", 0.0) or 0.0)
        pnl_score = max(min(float(getattr(agent, "total_pnl", 0.0) or 0.0), 20.0), -20.0) / 20.0
        loss_penalty = float(getattr(agent, "_consecutive_losses", 0) or 0) * 0.75
        score = timeframe_score + strategy_score + win_score + pnl_score - loss_penalty
        return (score, -int(getattr(agent.dna, "id", 0) or 0))

    @staticmethod
    def _dominant_strategy(agent) -> str:
        weights = getattr(agent.dna, "strategy_weights", {}) or {}
        if not weights:
            return "unknown"
        return max(weights, key=lambda key: weights[key])

    def summary(self) -> Dict:
        return {
            "enabled": self.enabled,
            "executors_per_symbol": self.executors_per_symbol,
            "strategy_preference": self.strategy_preference,
            "by_symbol": self._last_by_symbol,
        }
