from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from .registry import StrategyRegistry


DEFAULT_MIN_TRADES = 10
DEFAULT_MIN_PROFIT_FACTOR = 1.15
DEFAULT_MAX_DRAWDOWN_PCT = 8.0
DEFAULT_MIN_EXPECTANCY_PCT = 0.0
DEFAULT_POLICY_PATH = "strategy_lab/config/promotion_policy.json"


@dataclass
class PromotionDecision:
    strategy: str
    version: int
    market: str
    target_status: str
    approved: bool
    reasons: List[str]
    evidence: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def evaluate_shadow_gate(
    registry_entry: Dict[str, Any],
    *,
    min_trades: int = DEFAULT_MIN_TRADES,
    min_profit_factor: float = DEFAULT_MIN_PROFIT_FACTOR,
    max_drawdown_pct: float = DEFAULT_MAX_DRAWDOWN_PCT,
    min_expectancy_pct: float = DEFAULT_MIN_EXPECTANCY_PCT,
) -> PromotionDecision:
    proposal = dict(registry_entry.get("proposal") or {})
    report = dict(registry_entry.get("latest_report") or {})
    best = dict(report.get("best") or {})
    status = str(registry_entry.get("status") or proposal.get("status") or "draft")
    reasons: List[str] = []

    if status not in {"optimized", "backtested"}:
        reasons.append(f"strategy status must be optimized/backtested, got {status}")
    if not best:
        reasons.append("missing optimizer best evidence")
    if best and best.get("approved_for_forward_test") is not True:
        reasons.append("optimizer best is not approved for forward test")

    trades = int(best.get("trades") or 0)
    profit_factor = float(best.get("profit_factor") or 0)
    expectancy = float(best.get("expectancy_pct") or 0)
    max_drawdown = float(best.get("max_drawdown_pct") or 0)
    upstream_gate_reasons = [str(item) for item in best.get("gate_reasons") or []]

    if trades < min_trades:
        reasons.append(f"closed trade sample below {min_trades}: {trades}")
    if expectancy <= min_expectancy_pct:
        reasons.append(f"expectancy must be above {min_expectancy_pct}: {expectancy}")
    if profit_factor < min_profit_factor:
        reasons.append(f"profit factor below {min_profit_factor}: {profit_factor}")
    if max_drawdown > max_drawdown_pct:
        reasons.append(f"max drawdown above {max_drawdown_pct}%: {max_drawdown}")
    reasons.extend(upstream_gate_reasons)

    approved = len(reasons) == 0
    return PromotionDecision(
        strategy=str(registry_entry.get("name") or proposal.get("name") or ""),
        version=int(registry_entry.get("version") or proposal.get("version") or 1),
        market=str(registry_entry.get("market") or proposal.get("market") or ""),
        target_status="shadow_testing" if approved else "rejected",
        approved=approved,
        reasons=reasons,
        evidence={
            "status": status,
            "symbol": report.get("symbol"),
            "tested": report.get("tested"),
            "passed": report.get("passed"),
            "best": best,
            "thresholds": {
                "min_trades": min_trades,
                "min_profit_factor": min_profit_factor,
                "max_drawdown_pct": max_drawdown_pct,
                "min_expectancy_pct": min_expectancy_pct,
            },
        },
    )


def load_promotion_policy(path: str | Path = DEFAULT_POLICY_PATH) -> Dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return {}
    return json.loads(target.read_text())


def optimizer_shadow_thresholds(policy: Dict[str, Any] | None = None) -> Dict[str, Any]:
    data = dict((policy or {}).get("optimizer_shadow_gate") or {})
    return {
        "min_trades": int(data.get("min_trades", DEFAULT_MIN_TRADES)),
        "min_profit_factor": float(data.get("min_profit_factor", DEFAULT_MIN_PROFIT_FACTOR)),
        "max_drawdown_pct": float(data.get("max_drawdown_pct", DEFAULT_MAX_DRAWDOWN_PCT)),
        "min_expectancy_pct": float(data.get("min_expectancy_pct", DEFAULT_MIN_EXPECTANCY_PCT)),
    }


def promote_strategy_to_shadow(
    registry_path: str | Path,
    name: str,
    *,
    version: int = 1,
    manifest_path: str | Path = "strategy_lab/shadow/deployments.json",
    events_path: str | Path = "strategy_lab/shadow/events.jsonl",
    mode: str = "testnet_shadow",
    network: str = "testnet",
    policy_path: str | Path = DEFAULT_POLICY_PATH,
    write_rejection: bool = True,
) -> PromotionDecision:
    registry = StrategyRegistry(registry_path)
    data = registry.load()
    entries = list(data.get("strategies") or [])
    entry = next(
        (
            item for item in entries
            if item.get("name") == name and int(item.get("version") or 1) == int(version)
        ),
        None,
    )
    if not entry:
        raise ValueError(f"strategy not found in registry: {name} v{version}")

    thresholds = optimizer_shadow_thresholds(load_promotion_policy(policy_path))
    decision = evaluate_shadow_gate(entry, **thresholds)
    raw = dict(entry.get("proposal") or {})
    if decision.approved:
        raw["status"] = "shadow_testing"
        registry.upsert(raw, status="shadow_testing", report=entry.get("latest_report") or {})
        _append_shadow_manifest(manifest_path, entry, decision, events_path=events_path, mode=mode, network=network)
    elif write_rejection:
        raw["status"] = "rejected"
        registry.upsert(raw, status="rejected", report={
            **dict(entry.get("latest_report") or {}),
            "promotion_decision": decision.to_dict(),
        })
    return decision


def _append_shadow_manifest(
    path: str | Path,
    entry: Dict[str, Any],
    decision: PromotionDecision,
    *,
    events_path: str | Path,
    mode: str,
    network: str,
) -> Dict[str, Any]:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        data = json.loads(target.read_text())
    else:
        data = {"version": 1, "deployments": []}

    now = datetime.now(timezone.utc).isoformat()
    safe_mode = mode if mode in {"signal_only", "paper", "testnet_shadow"} else "testnet_shadow"
    safe_network = "production" if network == "production" else "testnet"
    deployment_id = f"{decision.market}:{decision.strategy}:v{decision.version}"
    deployment = {
        "id": deployment_id,
        "strategy": decision.strategy,
        "strategy_name": decision.strategy,
        "version": decision.version,
        "market": decision.market,
        "created_at": now,
        "deployed_at": now,
        "updated_at": now,
        "mode": safe_mode,
        "network": safe_network,
        "order_execution": "disabled",
        "status": "active",
        "source_status": "shadow_testing",
        "execution_enabled": False,
        "paper_or_testnet_only": True,
        "symbols": list(entry.get("symbols") or []),
        "timeframes": dict(entry.get("timeframes") or {}),
        "latest_signal": None,
        "notes": "Shadow deployment observes promoted strategies only; live order execution remains disabled.",
        "proposal": dict(entry.get("proposal") or {}),
        "promotion_decision": decision.to_dict(),
    }

    deployments = [
        item for item in list(data.get("deployments") or [])
        if item.get("id") != deployment_id
    ]
    deployments.append(deployment)
    data["deployments"] = deployments
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
    tmp.replace(target)
    _append_shadow_event(events_path, {
        "ts": now,
        "event": "shadow_deployment_created",
        "deployment_id": deployment_id,
        "strategy_name": decision.strategy,
        "mode": safe_mode,
        "network": safe_network,
        "order_execution": "disabled",
    })
    return deployment


def _append_shadow_event(path: str | Path, event: Dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, sort_keys=True) + "\n")
