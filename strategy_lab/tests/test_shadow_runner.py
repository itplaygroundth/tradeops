import json

from strategy_lab.shadow_runner import run_shadow_signals


def _proposal():
    return {
        "name": "shadow_trend",
        "version": 1,
        "market": "crypto",
        "symbols": ["BTCUSDT"],
        "timeframes": {"entry": "M15", "confirm": "H1", "regime": "H4"},
        "type": "trend_following",
        "entry_rules": [{"action": "LONG", "when": "unit"}],
        "exit_rules": [{"action": "HOLD", "when": "unit"}],
        "risk_rules": {"risk_pct": 0.001},
        "parameters": {"fast_sma": 3, "slow_sma": 8, "max_entry_rsi": 101},
        "status": "shadow_testing",
    }


def _deployment():
    return {
        "id": "crypto:shadow_trend:v1",
        "strategy_name": "shadow_trend",
        "version": 1,
        "market": "crypto",
        "symbols": ["BTCUSDT"],
        "timeframes": {"entry": "M15", "confirm": "H1", "regime": "H4"},
        "mode": "testnet_shadow",
        "network": "testnet",
        "order_execution": "disabled",
        "execution_enabled": False,
        "status": "active",
        "proposal": _proposal(),
    }


def _candles():
    prices = [100 + idx * 0.4 for idx in range(40)]
    return [
        {"open": p - 0.1, "high": p + 0.2, "low": p - 0.2, "close": p, "volume": 1000, "time": idx}
        for idx, p in enumerate(prices)
    ]


def test_shadow_runner_writes_signal_without_enabling_execution(tmp_path):
    deployments = tmp_path / "deployments.json"
    signals = tmp_path / "signals.jsonl"
    deployments.write_text(json.dumps({"version": 1, "deployments": [_deployment()]}))

    result = run_shadow_signals(
        deployments_path=deployments,
        signals_path=signals,
        candles_by_symbol={"BTCUSDT": _candles()},
    )

    assert result["ok"] is True
    assert result["signals"] == 1
    assert result["items"][0]["action"] == "LONG"
    assert result["items"][0]["order_execution"] == "disabled"
    assert result["items"][0]["execution_enabled"] is False
    updated = json.loads(deployments.read_text())
    assert updated["deployments"][0]["latest_signal"]["action"] == "LONG"
    assert signals.read_text().count("\n") == 1


def test_shadow_runner_skips_when_execution_is_enabled(tmp_path):
    deployment = _deployment()
    deployment["execution_enabled"] = True
    deployments = tmp_path / "deployments.json"
    signals = tmp_path / "signals.jsonl"
    deployments.write_text(json.dumps({"version": 1, "deployments": [deployment]}))

    result = run_shadow_signals(
        deployments_path=deployments,
        signals_path=signals,
        candles_by_symbol={"BTCUSDT": _candles()},
    )

    assert result["signals"] == 0
    assert result["skipped"][0]["reason"] == "deployment is not active signal-only shadow"
    assert signals.exists() is False
