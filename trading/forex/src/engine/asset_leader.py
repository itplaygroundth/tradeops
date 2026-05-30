from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .dna import STRATEGY_METHODS
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
                winner_idx = max(0, min(int(winner_idx), len(configs) - 1))
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
        """12 distinct strategy configs per spec (indices 0-11).

        Indices 0-9 are deterministic; 10-11 are seeded random.
        All configs sum to exactly 1.0.
        """
        import random as _random

        rng42 = _random.Random(42)
        rng99 = _random.Random(99)
        KEYS = STRATEGY_METHODS

        def _rand(rng: _random.Random) -> Dict[str, float]:
            w = [rng.random() for _ in KEYS]
            s = sum(w)
            return dict(zip(KEYS, [v / s for v in w]))

        return [
            # 0: momentum-heavy
            {"momentum": 0.60, "mean_reversion": 0.10, "grid_scalp": 0.10, "llm_sentiment": 0.05,
             "order_flow": 0.05, "breakout_atr": 0.05, "session_open": 0.05, "market_structure": 0.00},
            # 1: mean-rev-heavy
            {"momentum": 0.10, "mean_reversion": 0.60, "grid_scalp": 0.10, "llm_sentiment": 0.05,
             "order_flow": 0.05, "breakout_atr": 0.05, "session_open": 0.05, "market_structure": 0.00},
            # 2: grid-heavy
            {"momentum": 0.10, "mean_reversion": 0.10, "grid_scalp": 0.60, "llm_sentiment": 0.05,
             "order_flow": 0.05, "breakout_atr": 0.05, "session_open": 0.05, "market_structure": 0.00},
            # 3: order-flow-heavy
            {"momentum": 0.10, "mean_reversion": 0.10, "grid_scalp": 0.05, "llm_sentiment": 0.05,
             "order_flow": 0.60, "breakout_atr": 0.05, "session_open": 0.05, "market_structure": 0.00},
            # 4: breakout-heavy
            {"momentum": 0.10, "mean_reversion": 0.05, "grid_scalp": 0.05, "llm_sentiment": 0.05,
             "order_flow": 0.10, "breakout_atr": 0.55, "session_open": 0.10, "market_structure": 0.00},
            # 5: session-heavy
            {"momentum": 0.10, "mean_reversion": 0.05, "grid_scalp": 0.05, "llm_sentiment": 0.05,
             "order_flow": 0.10, "breakout_atr": 0.10, "session_open": 0.55, "market_structure": 0.00},
            # 6: structure-heavy
            {"momentum": 0.05, "mean_reversion": 0.10, "grid_scalp": 0.05, "llm_sentiment": 0.05,
             "order_flow": 0.15, "breakout_atr": 0.10, "session_open": 0.10, "market_structure": 0.40},
            # 7: balanced-8 (equal weight all 8)
            {"momentum": 0.125, "mean_reversion": 0.125, "grid_scalp": 0.125, "llm_sentiment": 0.125,
             "order_flow": 0.125, "breakout_atr": 0.125, "session_open": 0.125, "market_structure": 0.125},
            # 8: flow+breakout
            {"momentum": 0.05, "mean_reversion": 0.05, "grid_scalp": 0.05, "llm_sentiment": 0.05,
             "order_flow": 0.35, "breakout_atr": 0.35, "session_open": 0.05, "market_structure": 0.05},
            # 9: session+structure
            {"momentum": 0.05, "mean_reversion": 0.10, "grid_scalp": 0.05, "llm_sentiment": 0.05,
             "order_flow": 0.10, "breakout_atr": 0.10, "session_open": 0.35, "market_structure": 0.20},
            # 10: random-A seed 42
            _rand(rng42),
            # 11: random-B seed 99
            _rand(rng99),
        ]


async def maybe_await(x):
    if asyncio.iscoroutine(x):
        return await x
    return x
