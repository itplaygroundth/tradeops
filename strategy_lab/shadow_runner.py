from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List

from .backtest import _entry_signal, _exit_signal
from .schema import validate_strategy_proposal


@dataclass
class ShadowSignal:
    deployment_id: str
    strategy_name: str
    symbol: str
    action: str
    reason: str
    price: float | None
    timestamp: float
    regime: str = "unknown"
    guard_status: str = "allowed"
    order_execution: str = "disabled"
    execution_enabled: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def run_shadow_signals(
    *,
    deployments_path: str | Path = "strategy_lab/shadow/deployments.json",
    signals_path: str | Path = "strategy_lab/shadow/signals.jsonl",
    guard_policy_path: str | Path = "strategy_lab/handoff/shadow_guard_policy.json",
    candles_by_symbol: Dict[str, List[Dict[str, Any]]] | None = None,
) -> Dict[str, Any]:
    deployments_file = Path(deployments_path)
    store = _read_json(deployments_file, {"version": 1, "deployments": []})
    guard_policy = _read_json(Path(guard_policy_path), {"no_trade_regimes": [], "enforcement": {}})
    candles_by_symbol = candles_by_symbol or {}
    signals: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []

    for deployment in list(store.get("deployments") or []):
        if not _is_signal_only_active(deployment):
            skipped.append({
                "deployment_id": deployment.get("id", ""),
                "reason": "deployment is not active signal-only shadow",
            })
            continue
        proposal_raw = deployment.get("proposal") or _proposal_from_deployment(deployment)
        try:
            proposal = validate_strategy_proposal(proposal_raw)
        except Exception as error:
            skipped.append({
                "deployment_id": deployment.get("id", ""),
                "reason": f"invalid proposal: {error}",
            })
            continue

        latest_signal = None
        for symbol in proposal.symbols:
            candles = candles_by_symbol.get(symbol) or []
            if len(candles) < 30:
                skipped.append({
                    "deployment_id": deployment.get("id", ""),
                    "symbol": symbol,
                    "reason": "insufficient candles",
                })
                continue
            signal = evaluate_shadow_signal(deployment, proposal_raw, symbol, candles, guard_policy=guard_policy)
            latest_signal = signal.to_dict()
            signals.append(latest_signal)
            _append_jsonl(signals_path, latest_signal)
        if latest_signal:
            deployment["latest_signal"] = latest_signal
            deployment["updated_at"] = latest_signal["timestamp"]

    if signals:
        _write_json_atomic(deployments_file, store)
    return {
        "ok": True,
        "signals": len(signals),
        "skipped": skipped,
        "items": signals,
    }


def evaluate_shadow_signal(
    deployment: Dict[str, Any],
    proposal_raw: Dict[str, Any],
    symbol: str,
    candles: List[Dict[str, Any]],
    guard_policy: Dict[str, Any] | None = None,
) -> ShadowSignal:
    proposal = validate_strategy_proposal(proposal_raw)
    closes = [float(candle["close"]) for candle in candles]
    price = closes[-1] if closes else None
    regime = _current_regime(deployment, candles)
    blocked_regimes = _blocked_regimes(guard_policy or {})
    if _normalise_regime(regime) in blocked_regimes:
        return ShadowSignal(
            deployment_id=str(deployment.get("id") or ""),
            strategy_name=proposal.name,
            symbol=symbol,
            action="HOLD",
            reason=f"shadow guard blocked new entries in regime={regime}",
            price=price,
            timestamp=time.time(),
            regime=regime,
            guard_status="blocked_no_trade_regime",
        )
    entry = _entry_signal(proposal.strategy_type, closes, candles, proposal.parameters)
    exit_ = _exit_signal(proposal.strategy_type, closes, candles, proposal.parameters)
    if exit_:
        action = "HOLD"
        reason = "exit condition detected; shadow runner does not close or open orders"
    elif entry:
        action = "LONG"
        reason = "entry conditions detected in shadow mode"
    else:
        action = "HOLD"
        reason = "no entry conditions detected"
    return ShadowSignal(
        deployment_id=str(deployment.get("id") or ""),
        strategy_name=proposal.name,
        symbol=symbol,
        action=action,
        reason=reason,
        price=price,
        timestamp=time.time(),
        regime=regime,
        guard_status="allowed",
    )


def _blocked_regimes(policy: Dict[str, Any]) -> set[str]:
    raw = policy.get("no_trade_regimes") or policy.get("enforcement", {}).get("block_new_entries_when_regime_in") or []
    return {_normalise_regime(item) for item in raw}


def _current_regime(deployment: Dict[str, Any], candles: List[Dict[str, Any]]) -> str:
    for key in ("current_regime", "regime", "market_regime"):
        if deployment.get(key):
            return str(deployment[key])
    if len(candles) < 20:
        return "unknown"
    closes = [float(candle["close"]) for candle in candles if candle.get("close") is not None]
    if len(closes) < 20:
        return "unknown"
    returns = [abs(closes[index] / closes[index - 1] - 1) for index in range(1, len(closes))]
    avg_abs_return = sum(returns[-20:]) / min(20, len(returns))
    if avg_abs_return >= 0.012:
        return "high_volatility"
    if abs(closes[-1] / closes[-20] - 1) <= 0.02:
        return "sideways"
    return "trend"


def _normalise_regime(regime: Any) -> str:
    value = str(regime or "unknown").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "high_vol": "high_volatility",
        "highvol": "high_volatility",
        "volatile": "high_volatility",
        "volatility": "high_volatility",
        "sideway": "sideways",
        "range": "sideways",
        "ranging": "sideways",
    }
    return aliases.get(value, value)


def _is_signal_only_active(deployment: Dict[str, Any]) -> bool:
    return (
        deployment.get("status") == "active"
        and deployment.get("order_execution") == "disabled"
        and deployment.get("execution_enabled") is not True
    )


def _proposal_from_deployment(deployment: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "name": deployment.get("strategy_name") or deployment.get("strategy") or "",
        "version": deployment.get("version") or 1,
        "market": deployment.get("market") or "crypto",
        "symbols": deployment.get("symbols") or [],
        "timeframes": deployment.get("timeframes") or {"entry": "M15", "confirm": "H1", "regime": "H4"},
        "type": deployment.get("type") or "trend_following",
        "entry_rules": [{"action": "LONG", "when": "shadow deployment proposal fallback"}],
        "exit_rules": [{"action": "HOLD", "when": "shadow deployment proposal fallback"}],
        "risk_rules": {"risk_pct": 0.001},
        "parameters": {},
        "status": "shadow_testing",
    }


def _read_json(path: Path, fallback: Dict[str, Any]) -> Dict[str, Any]:
    if not path.exists():
        return fallback
    return json.loads(path.read_text())


def _write_json_atomic(path: Path, value: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True))
    tmp.replace(path)


def _append_jsonl(path: str | Path, value: Dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(value, sort_keys=True) + "\n")
