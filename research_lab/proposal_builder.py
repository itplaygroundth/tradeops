from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from strategy_lab.schema import validate_strategy_proposal


DEFAULT_CRYPTO_SYMBOLS = ["BTCUSDT", "ETHUSDT"]
DEFAULT_TIMEFRAMES = {"entry": "M15", "confirm": "H1", "regime": "H4"}


def hypothesis_to_proposal(hypothesis: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    family = str(hypothesis.get("strategy_family") or "")
    regime = str(hypothesis.get("regime") or "unknown")
    if family == "mean_reversion":
        proposal = _mean_reversion_proposal(hypothesis)
    elif family == "order_flow_liquidity":
        proposal = _order_flow_filter_proposal(hypothesis)
    elif family == "volatility_regime_filter":
        proposal = _volatility_filter_proposal(hypothesis)
    elif family == "trend_risk_model" or regime == "trend":
        proposal = _trend_filter_proposal(hypothesis)
    else:
        return None
    validate_strategy_proposal(proposal)
    return proposal


def build_proposals(hypotheses: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    proposals = []
    seen = set()
    for hypothesis in hypotheses:
        proposal = hypothesis_to_proposal(hypothesis)
        if not proposal:
            continue
        key = (proposal["name"], proposal.get("version", 1))
        if key in seen:
            continue
        seen.add(key)
        proposals.append(proposal)
    return proposals


def write_proposals(proposals: Iterable[Dict[str, Any]], directory: str | Path) -> List[Path]:
    out_dir = Path(directory)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for proposal in proposals:
        path = out_dir / f"{proposal['name']}.json"
        path.write_text(json.dumps(proposal, indent=2, sort_keys=True))
        paths.append(path)
    return paths


def _base(hypothesis: Dict[str, Any], name: str, strategy_type: str, risk_pct: float = 0.003) -> Dict[str, Any]:
    return {
        "name": name,
        "version": 1,
        "market": "crypto",
        "symbols": DEFAULT_CRYPTO_SYMBOLS,
        "timeframes": dict(DEFAULT_TIMEFRAMES),
        "type": strategy_type,
        "entry_rules": [],
        "exit_rules": [],
        "risk_rules": {"risk_pct": risk_pct, "max_positions": 1},
        "parameters": {
            "source_hypothesis_id": hypothesis.get("hypothesis_id"),
            "source_paper_id": hypothesis.get("source_paper_id"),
            "research_confidence": hypothesis.get("confidence", 0),
        },
        "status": "draft",
    }


def _first(params: Dict[str, List[Any]], key: str, default: Any) -> Any:
    values = params.get(key) or []
    return values[0] if values else default


def _mean_reversion_proposal(hypothesis: Dict[str, Any]) -> Dict[str, Any]:
    params = hypothesis.get("testable_parameters") or {}
    proposal = _base(hypothesis, "generated_mean_reversion_range_v1", "mean_reversion", risk_pct=0.003)
    proposal["entry_rules"] = [{"action": "LONG", "when": "price_deviates_below_mean_in_range_regime"}]
    proposal["exit_rules"] = [{"action": "HOLD", "when": "price_reverts_to_mean_or_regime_flips"}]
    proposal["parameters"].update({
        "mean_window": _first(params, "mean_window", 20),
        "entry_deviation_pct": _first(params, "entry_deviation_pct", 0.6),
        "exit_deviation_pct": _first(params, "exit_deviation_pct", 0.0),
        "max_hold_bars": _first(params, "max_hold_bars", 12),
        "fee_bps": 10,
        "slippage_bps": 2,
    })
    return proposal


def _order_flow_filter_proposal(hypothesis: Dict[str, Any]) -> Dict[str, Any]:
    params = hypothesis.get("testable_parameters") or {}
    proposal = _base(hypothesis, "generated_order_flow_liquidity_filter_v1", "market_structure", risk_pct=0.0025)
    proposal["entry_rules"] = [{"action": "LONG", "when": "market_structure_break_with_liquidity_filter"}]
    proposal["exit_rules"] = [{"action": "HOLD", "when": "liquidity_imbalance_fades_or_time_stop"}]
    proposal["parameters"].update({
        "imbalance_window": _first(params, "imbalance_window", 20),
        "min_depth_imbalance": _first(params, "min_depth_imbalance", 0.25),
        "max_spread_bps": _first(params, "max_spread_bps", 5),
        "max_hold_bars": _first(params, "max_hold_bars", 8),
        "fast_sma": 9,
        "slow_sma": 21,
        "max_entry_rsi": 72,
        "fee_bps": 10,
        "slippage_bps": 2,
    })
    return proposal


def _volatility_filter_proposal(hypothesis: Dict[str, Any]) -> Dict[str, Any]:
    params = hypothesis.get("testable_parameters") or {}
    proposal = _base(hypothesis, "generated_volatility_regime_filter_v1", "market_structure", risk_pct=0.002)
    proposal["entry_rules"] = [{"action": "LONG", "when": "market_structure_break_and_volatility_below_cap"}]
    proposal["exit_rules"] = [{"action": "HOLD", "when": "volatility_exceeds_cap_or_structure_fails"}]
    proposal["parameters"].update({
        "atr_period": _first(params, "atr_period", 14),
        "max_atr_pct": _first(params, "max_atr_pct", 2.5),
        "vol_zscore_window": _first(params, "vol_zscore_window", 100),
        "vol_zscore_limit": _first(params, "vol_zscore_limit", 1.5),
        "fast_sma": 9,
        "slow_sma": 21,
        "max_entry_rsi": 72,
        "max_hold_bars": 12,
        "fee_bps": 10,
        "slippage_bps": 2,
    })
    return proposal


def _trend_filter_proposal(hypothesis: Dict[str, Any]) -> Dict[str, Any]:
    params = hypothesis.get("testable_parameters") or {}
    proposal = _base(hypothesis, "generated_trend_risk_model_v1", "trend_following", risk_pct=0.0025)
    proposal["entry_rules"] = [{"action": "LONG", "when": "trend_strength_positive_and_volatility_risk_acceptable"}]
    proposal["exit_rules"] = [{"action": "HOLD", "when": "trend_strength_decays_or_risk_cap_hit"}]
    proposal["parameters"].update({
        "trend_window": _first(params, "trend_window", 50),
        "risk_scale": _first(params, "risk_scale", 0.5),
        "volatility_cap": _first(params, "volatility_cap", 2.5),
        "fast_sma": 9,
        "slow_sma": 34,
        "max_entry_rsi": 72,
        "max_hold_bars": 12,
        "fee_bps": 10,
        "slippage_bps": 2,
    })
    return proposal

