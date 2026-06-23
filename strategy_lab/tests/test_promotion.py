import json
from pathlib import Path

from strategy_lab.promotion import evaluate_shadow_gate, load_promotion_policy, promote_strategy_to_shadow


def _proposal():
    return {
        "name": "btc_shadow_candidate",
        "version": 1,
        "market": "crypto",
        "symbols": ["BTCUSDT"],
        "timeframes": {"entry": "M15", "confirm": "H1", "regime": "H4"},
        "type": "trend_following",
        "entry_rules": [{"action": "LONG", "when": "unit"}],
        "exit_rules": [{"action": "HOLD", "when": "unit"}],
        "risk_rules": {"risk_pct": 0.005},
        "parameters": {"fast_sma": 9, "slow_sma": 21},
        "status": "optimized",
    }


def _entry(best_overrides=None, status="optimized"):
    best = {
        "approved_for_forward_test": True,
        "gate_reasons": [],
        "trades": 18,
        "expectancy_pct": 0.12,
        "profit_factor": 1.35,
        "max_drawdown_pct": 3.1,
        "parameters": {"fast_sma": 9, "slow_sma": 21},
    }
    best.update(best_overrides or {})
    proposal = _proposal()
    return {
        "name": proposal["name"],
        "version": proposal["version"],
        "market": proposal["market"],
        "symbols": proposal["symbols"],
        "timeframes": proposal["timeframes"],
        "type": proposal["type"],
        "status": status,
        "proposal": proposal,
        "latest_report": {
            "strategy_name": proposal["name"],
            "symbol": "BTCUSDT",
            "tested": 81,
            "passed": 4,
            "best": best,
        },
    }


def _write_registry(path: Path, entry):
    path.write_text(json.dumps({"version": 1, "strategies": [entry]}, indent=2))


def test_shadow_gate_approves_only_optimizer_evidence_that_passes():
    decision = evaluate_shadow_gate(_entry())
    assert decision.approved is True
    assert decision.target_status == "shadow_testing"
    assert decision.reasons == []


def test_shadow_gate_fails_closed_on_negative_expectancy():
    decision = evaluate_shadow_gate(_entry({
        "approved_for_forward_test": False,
        "expectancy_pct": -0.1,
        "profit_factor": 0.8,
        "gate_reasons": ["expectancy is not positive"],
    }))
    assert decision.approved is False
    assert decision.target_status == "rejected"
    assert any("expectancy" in reason for reason in decision.reasons)
    assert any("profit factor" in reason for reason in decision.reasons)


def test_promote_strategy_to_shadow_writes_non_executing_manifest(tmp_path):
    registry = tmp_path / "registry.json"
    manifest = tmp_path / "shadow.json"
    events = tmp_path / "events.jsonl"
    _write_registry(registry, _entry())

    decision = promote_strategy_to_shadow(registry, "btc_shadow_candidate", manifest_path=manifest, events_path=events)

    assert decision.approved is True
    registry_data = json.loads(registry.read_text())
    assert registry_data["strategies"][0]["status"] == "shadow_testing"
    manifest_data = json.loads(manifest.read_text())
    deployment = manifest_data["deployments"][0]
    assert deployment["id"] == "crypto:btc_shadow_candidate:v1"
    assert deployment["strategy_name"] == "btc_shadow_candidate"
    assert deployment["mode"] == "testnet_shadow"
    assert deployment["network"] == "testnet"
    assert deployment["status"] == "active"
    assert deployment["order_execution"] == "disabled"
    assert deployment["execution_enabled"] is False
    assert deployment["paper_or_testnet_only"] is True
    assert "shadow_deployment_created" in events.read_text()


def test_promote_strategy_rejects_weak_candidate_without_manifest(tmp_path):
    registry = tmp_path / "registry.json"
    manifest = tmp_path / "shadow.json"
    events = tmp_path / "events.jsonl"
    _write_registry(registry, _entry({
        "approved_for_forward_test": False,
        "expectancy_pct": -0.2,
        "profit_factor": 0.5,
        "gate_reasons": ["expectancy is not positive"],
    }))

    decision = promote_strategy_to_shadow(registry, "btc_shadow_candidate", manifest_path=manifest, events_path=events)

    assert decision.approved is False
    assert manifest.exists() is False
    assert events.exists() is False
    registry_data = json.loads(registry.read_text())
    assert registry_data["strategies"][0]["status"] == "rejected"
    assert "promotion_decision" in registry_data["strategies"][0]["latest_report"]


def test_promote_strategy_reads_optimizer_thresholds_from_shared_policy(tmp_path):
    registry = tmp_path / "registry.json"
    manifest = tmp_path / "shadow.json"
    events = tmp_path / "events.jsonl"
    policy = tmp_path / "promotion_policy.json"
    policy.write_text(json.dumps({
        "version": 1,
        "optimizer_shadow_gate": {
            "min_trades": 20,
            "min_profit_factor": 1.5,
            "max_drawdown_pct": 8.0,
            "min_expectancy_pct": 0.0,
        },
    }))
    _write_registry(registry, _entry())

    loaded = load_promotion_policy(policy)
    decision = promote_strategy_to_shadow(
        registry,
        "btc_shadow_candidate",
        manifest_path=manifest,
        events_path=events,
        policy_path=policy,
    )

    assert loaded["optimizer_shadow_gate"]["min_trades"] == 20
    assert decision.approved is False
    assert any("closed trade sample below 20" in reason for reason in decision.reasons)
    assert any("profit factor below 1.5" in reason for reason in decision.reasons)
    assert manifest.exists() is False
