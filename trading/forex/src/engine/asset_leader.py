from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .sub_agent import BacktestResult, SubAgent

logger = logging.getLogger(__name__)


@dataclass
class CompetitionResult:
    symbol: str
    winner_config: Dict[str, Any]
    winner_sharpe: float
    hermes_reasoning: str
    hermes_confidence: float
    forward_pnl: float
    approved: bool
    applied: bool
    timestamp: float


class AssetLeader:
    def __init__(self, symbol: str, production_agent: Any, mt5_client: Any, hermes_client: Any):
        self.symbol = symbol
        self.production_agent = production_agent
        self.mt5 = mt5_client
        self.hermes = hermes_client

    async def run_competition(self) -> CompetitionResult:
        # fetch candles (200 bars) if client supports it
        candles = []
        try:
            if hasattr(self.mt5, "get_ohlcv"):
                candles = await maybe_await(self.mt5.get_ohlcv(self.symbol, 200))
            elif hasattr(self.mt5, "fetch_ohlcv"):
                candles = await maybe_await(self.mt5.fetch_ohlcv(self.symbol, 200))
        except Exception:
            logger.exception("Failed to fetch candles for competition; aborting")

        # create 12 subagents based on production_agent.dna.strategy_weights template if available
        configs = self._make_configs()

        subs = [SubAgent(self.symbol, cfg, mt5_client=self.mt5) for cfg in configs]

        # Phase 1: backtest in parallel
        tasks = [s.run_backtest(candles) for s in subs]
        results: List[BacktestResult] = await asyncio.gather(*tasks)

        # choose top-3 by sharpe
        indexed = list(enumerate(results))
        indexed.sort(key=lambda t: t[1].sharpe, reverse=True)
        top3 = indexed[:3]

        # Phase 2: ask Hermes (if available)
        winner_idx = top3[0][0]
        reasoning = "top sharpe fallback"
        confidence = 0.0
        try:
            if self.hermes:
                payload = {
                    "symbol": self.symbol,
                    "results": [ {"idx": i, "sharpe": r.sharpe, "pnl_pct": r.pnl_pct, "win_rate": r.win_rate} for i, r in enumerate(results) ]
                }
                resp = await maybe_await(self.hermes.select_winner(payload))
                winner_idx = resp.get("winner_idx", winner_idx)
                reasoning = resp.get("reasoning", reasoning)
                confidence = resp.get("confidence", confidence)
        except Exception:
            logger.exception("Hermes selection failed; falling back to top sharpe")

        # Phase 3: forward-test top-3 sequentially (simple)
        forward_pnl = 0.0
        for idx, _ in top3:
            f = await subs[idx].run_forward_test(duration_seconds=60)
            forward_pnl = max(forward_pnl, f.pnl)

        # Phase 4: Hermes verify
        approved = False
        apply_cfg = configs[winner_idx]
        try:
            if self.hermes:
                v = await maybe_await(self.hermes.verify_forward_test({"symbol": self.symbol, "forward_pnl": forward_pnl}))
                approved = bool(v.get("approved", False))
                apply_cfg = v.get("apply_config", apply_cfg)
        except Exception:
            logger.exception("Hermes verification failed; rejecting by default")

        applied = False
        if approved and self.production_agent:
            # attempt to apply
            try:
                if hasattr(self.production_agent, "update_strategy_weights"):
                    await maybe_await(self.production_agent.update_strategy_weights(apply_cfg))
                    applied = True
            except Exception:
                logger.exception("Failed to apply winner config to production agent")

        import time

        return CompetitionResult(
            self.symbol,
            apply_cfg,
            results[winner_idx].sharpe if results else 0.0,
            reasoning,
            confidence,
            forward_pnl,
            approved,
            applied,
            time.time(),
        )

    def _make_configs(self) -> List[Dict[str, float]]:
        # produce 12 simple configs; if production agent has dna, use it as baseline
        base = getattr(self.production_agent, "dna", None)
        base_weights = getattr(base, "strategy_weights", None) if base else None

        configs = []
        for i in range(12):
            if base_weights:
                configs.append(dict(base_weights))
            else:
                # default balanced config
                cfg = {
                    "momentum": 0.125,
                    "mean_reversion": 0.125,
                    "grid_scalp": 0.125,
                    "llm_sentiment": 0.125,
                    "order_flow": 0.125,
                    "breakout_atr": 0.125,
                    "session_open": 0.125,
                    "market_structure": 0.0,
                }
                configs.append(cfg)
        return configs


async def maybe_await(x):
    if asyncio.iscoroutine(x):
        return await x
    return x
