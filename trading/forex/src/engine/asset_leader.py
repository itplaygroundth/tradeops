from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .dna import STRATEGY_METHODS
from .markov_regime import detect_regime
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
    regime: str = "RANGING"
    selection_source: str = "deterministic"
    llm_error: str = ""
    deterministic_winner_idx: int = 0
    llm_winner_idx: Optional[int] = None
    proposal_status: str = "not_checked"
    proposal_reason: str = ""
    proposal_source: str = ""


class AssetLeader:
    def __init__(self, symbol: str, production_agent: Any, mt5_client: Any, hermes_client: Any):
        self.symbol = symbol
        self.production_agent = production_agent
        self.mt5 = mt5_client
        self.hermes = hermes_client

    async def run_competition(self) -> CompetitionResult:
        # fetch M15 candles for backtest
        candles: List[Dict] = []
        try:
            if hasattr(self.mt5, "get_ohlcv"):
                candles = await maybe_await(self.mt5.get_ohlcv(self.symbol, timeframe="M15", count=200))
            elif hasattr(self.mt5, "fetch_ohlcv"):
                candles = await maybe_await(self.mt5.fetch_ohlcv(self.symbol, 200))
        except Exception:
            logger.exception("Failed to fetch M15 candles for competition")

        # fetch D1 candles for Markov regime detection
        d1_candles: List[Dict] = []
        try:
            if hasattr(self.mt5, "get_ohlcv"):
                d1_candles = await maybe_await(self.mt5.get_ohlcv(self.symbol, timeframe="D1", count=60))
        except Exception:
            logger.exception("Failed to fetch D1 candles; regime defaults to RANGING")

        regime, _ = detect_regime(d1_candles)
        logger.info("Competition regime for %s: %s", self.symbol, regime)

        # create 12 subagents biased by regime
        configs = self._make_configs(regime)

        subs = [SubAgent(self.symbol, cfg, mt5_client=self.mt5) for cfg in configs]

        # Phase 1: backtest in parallel
        tasks = [s.run_backtest(candles) for s in subs]
        results: List[BacktestResult] = await asyncio.gather(*tasks)

        # choose top-3 by deterministic score
        indexed = list(enumerate(results))
        indexed.sort(key=lambda t: self._score_result(t[1]), reverse=True)
        top3 = indexed[:3]

        # Phase 2: deterministic baseline, with optional Hermes advisory.
        deterministic_winner_idx = top3[0][0] if top3 else 0
        winner_idx = deterministic_winner_idx
        llm_winner_idx: Optional[int] = None
        selection_source = "deterministic"
        llm_error = ""
        reasoning = "deterministic score fallback"
        confidence = 0.0
        llm_enabled = _env_bool("LLM_DECISION_ENABLED", True)
        if llm_enabled and self.hermes:
            try:
                payload = {
                    "symbol": self.symbol,
                    "regime": regime,
                    "deterministic_winner_idx": deterministic_winner_idx,
                    "results": [
                        {
                            "idx": i,
                            "score": self._score_result(r),
                            "sharpe": r.sharpe,
                            "pnl_pct": r.pnl_pct,
                            "win_rate": r.win_rate,
                            "max_drawdown": r.max_drawdown,
                            "trades": r.trades,
                        }
                        for i, r in enumerate(results)
                    ],
                }
                resp = await maybe_await(self.hermes.select_winner(payload))
                llm_winner_idx = max(0, min(int(resp.get("winner_idx", winner_idx)), len(configs) - 1))
                winner_idx = llm_winner_idx
                selection_source = "hermes"
                reasoning = resp.get("reasoning", reasoning)
                confidence = resp.get("confidence", confidence)
            except Exception as exc:
                llm_error = f"{type(exc).__name__}: {exc}"
                selection_source = "deterministic_fallback"
                logger.warning("Hermes selection failed; falling back to deterministic score: %s", llm_error)

        # Phase 3: forward-test top-3 sequentially (simple)
        forward_pnl = 0.0
        forward_results: List[Dict[str, Any]] = []
        for idx, _ in top3:
            f = await subs[idx].run_forward_test(duration_seconds=60)
            forward_pnl = max(forward_pnl, f.pnl)
            forward_results.append({
                "idx": idx,
                "pnl": f.pnl,
                "max_drawdown": f.max_drawdown,
                "trade_count": f.trade_count,
                "pnl_pct": f.pnl_pct,
            })

        # Phase 4: deterministic guardrails, with optional Hermes verification.
        approved = forward_pnl >= 0.0
        apply_cfg = configs[winner_idx]
        if llm_enabled and self.hermes:
            try:
                v = await maybe_await(self.hermes.verify_forward_test({
                    "symbol": self.symbol,
                    "winner_idx": winner_idx,
                    "winner_config": apply_cfg,
                    "forward_pnl": forward_pnl,
                    "forward_results": forward_results,
                }))
                approved = bool(v.get("approved", False))
                apply_cfg = v.get("apply_config", apply_cfg)
            except Exception as exc:
                verify_error = f"{type(exc).__name__}: {exc}"
                llm_error = f"{llm_error}; verify {verify_error}" if llm_error else f"verify {verify_error}"
                logger.warning("Hermes verification failed; using deterministic approval=%s: %s", approved, verify_error)

        proposal_status = "disabled"
        proposal_reason = ""
        proposal_source = ""
        if _env_bool("SUPERVISOR_PROPOSALS_ENABLED", True):
            proposal = self._load_proposal()
            if proposal:
                proposal_status, proposal_reason, proposal_cfg = self._validate_proposal(proposal, apply_cfg)
                proposal_source = str(proposal.get("source", "supervisor"))
                if proposal_status == "accepted" and approved:
                    apply_cfg = proposal_cfg
                    selection_source = "supervisor_proposal"
                    reasoning = f"{reasoning}; supervisor proposal accepted: {proposal_reason}"
            else:
                proposal_status = "none"

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
            regime,
            selection_source,
            llm_error,
            deterministic_winner_idx,
            llm_winner_idx,
            proposal_status,
            proposal_reason,
            proposal_source,
        )

    def _score_result(self, result: BacktestResult) -> float:
        """Bounded deterministic score for ranking sub-agent backtests."""
        return (
            result.sharpe
            + (result.pnl_pct / 100.0)
            + result.win_rate
            - abs(result.max_drawdown / 100.0)
            + min(result.trades, 20) * 0.01
        )

    def _load_proposal(self) -> Optional[Dict[str, Any]]:
        path = Path(os.getenv(
            "STRATEGY_PROPOSALS_PATH",
            str(Path(__file__).resolve().parent.parent.parent / "data" / "strategy_proposals.json"),
        ))
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text())
        except Exception as exc:
            logger.warning("Failed to read strategy proposals from %s: %s", path, exc)
            return {"symbol": self.symbol, "_invalid": f"read_error: {exc}"}

        proposals = raw.get("proposals", raw if isinstance(raw, list) else [])
        if not isinstance(proposals, list):
            return {"symbol": self.symbol, "_invalid": "proposals must be a list"}

        now = time.time()
        candidates = [
            p for p in proposals
            if isinstance(p, dict) and p.get("symbol") == self.symbol and float(p.get("expires_at", now + 1)) >= now
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda p: (float(p.get("confidence", 0.0)), float(p.get("created_at", 0.0))), reverse=True)
        return candidates[0]

    def _validate_proposal(
        self,
        proposal: Dict[str, Any],
        current_config: Dict[str, Any],
    ) -> Tuple[str, str, Dict[str, float]]:
        if proposal.get("_invalid"):
            return "rejected", str(proposal["_invalid"]), {}
        if proposal.get("symbol") != self.symbol:
            return "rejected", "symbol mismatch", {}
        now = time.time()
        if float(proposal.get("expires_at", 0.0)) < now:
            return "rejected", "proposal expired", {}
        min_conf = float(os.getenv("SUPERVISOR_MIN_CONFIDENCE", "0.6"))
        confidence = float(proposal.get("confidence", 0.0))
        if confidence < min_conf:
            return "rejected", f"confidence {confidence:.2f} below {min_conf:.2f}", {}
        weights = proposal.get("strategy_weights")
        if not isinstance(weights, dict):
            return "rejected", "strategy_weights must be an object", {}

        cleaned: Dict[str, float] = {}
        for key, value in weights.items():
            if key not in STRATEGY_METHODS:
                return "rejected", f"unknown strategy weight: {key}", {}
            try:
                weight = float(value)
            except (TypeError, ValueError):
                return "rejected", f"non-numeric weight: {key}", {}
            if weight < 0:
                return "rejected", f"negative weight: {key}", {}
            cleaned[key] = weight

        if set(cleaned) != set(STRATEGY_METHODS):
            return "rejected", "proposal must include all strategy weights", {}
        total = sum(cleaned.values())
        if total <= 0:
            return "rejected", "weights sum must be positive", {}
        normalized = {k: v / total for k, v in cleaned.items()}
        if abs(sum(normalized.values()) - 1.0) > 1e-6:
            return "rejected", "weights do not normalize to 1.0", {}

        max_delta = float(os.getenv("SUPERVISOR_MAX_WEIGHT_DELTA", "0.35"))
        baseline = self._current_strategy_weights(current_config)
        for key, weight in normalized.items():
            if abs(weight - baseline.get(key, 0.0)) > max_delta:
                return "rejected", f"{key} delta exceeds {max_delta:.2f}", {}

        return "accepted", str(proposal.get("reason", "valid supervisor proposal")), normalized

    def _current_strategy_weights(self, fallback: Dict[str, Any]) -> Dict[str, float]:
        dna = getattr(self.production_agent, "dna", None)
        weights = getattr(dna, "strategy_weights", None)
        if isinstance(weights, dict):
            return {k: float(weights.get(k, 0.0)) for k in STRATEGY_METHODS}
        return {k: float(fallback.get(k, 0.0)) for k in STRATEGY_METHODS}

    def _make_configs(self, regime: str = "RANGING") -> List[Dict[str, float]]:
        """12 distinct strategy configs per spec (indices 0-11).

        Indices 0-9 are deterministic; 10-11 are seeded random.
        All configs sum to exactly 1.0.

        Regime bias:
          TREND_UP/DOWN  → promote momentum, breakout_atr; suppress mean_reversion, grid
          RANGING        → promote mean_reversion, grid_scalp; suppress momentum
        """
        import random as _random

        rng42 = _random.Random(42)
        rng99 = _random.Random(99)
        KEYS = STRATEGY_METHODS

        def _rand(rng: _random.Random) -> Dict[str, float]:
            w = [rng.random() for _ in KEYS]
            s = sum(w)
            return dict(zip(KEYS, [v / s for v in w]))

        def _bias(cfg: Dict[str, float]) -> Dict[str, float]:
            """Apply regime multiplier then renormalise to sum=1.0."""
            if regime in ("TREND_UP", "TREND_DOWN"):
                mult = {
                    "momentum": 1.4, "breakout_atr": 1.3, "order_flow": 1.2,
                    "market_structure": 1.1, "session_open": 1.0,
                    "llm_sentiment": 0.9, "mean_reversion": 0.5, "grid_scalp": 0.4,
                }
            else:  # RANGING
                mult = {
                    "mean_reversion": 1.5, "grid_scalp": 1.4, "llm_sentiment": 1.0,
                    "session_open": 1.0, "order_flow": 0.9, "market_structure": 0.8,
                    "breakout_atr": 0.5, "momentum": 0.5,
                }
            from math import fsum
            biased = {k: cfg[k] * mult.get(k, 1.0) for k in cfg}
            raw_total = fsum(biased.values()) or 1.0
            keys = list(biased)
            vals = [biased[k] / raw_total for k in keys]
            # correct residual float error so sum is exactly 1.0
            vals[-1] += 1.0 - fsum(vals)
            return dict(zip(keys, vals))

        base = [
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
        return [_bias(cfg) for cfg in base]


async def maybe_await(x):
    if asyncio.iscoroutine(x):
        return await x
    return x


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in ("0", "false", "no", "off", "")
