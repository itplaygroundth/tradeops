from pathlib import Path

import pytest

from strategy_lab.backtest import run_crypto_backtest
from strategy_lab.registry import StrategyRegistry
from strategy_lab.schema import StrategyValidationError, validate_strategy_proposal


def _proposal():
    return {
        "name": "btc_eth_trend_pullback_v1",
        "market": "crypto",
        "symbols": ["BTCUSDT", "ETHUSDT"],
        "timeframes": {"entry": "M15", "confirm": "H1", "regime": "H4"},
        "type": "trend_following",
        "entry_rules": [{"action": "LONG", "when": "fast_sma_above_slow_sma"}],
        "exit_rules": [{"action": "HOLD", "when": "fast_sma_below_slow_sma"}],
        "risk_rules": {"risk_pct": 0.005},
        "parameters": {"fast_sma": 3, "slow_sma": 8, "max_hold_bars": 6, "fee_bps": 1, "slippage_bps": 1},
    }


def _candles():
    prices = []
    price = 100.0
    for cycle in range(8):
        for _ in range(6):
            price -= 0.8
            prices.append(price)
        for _ in range(10):
            price += 1.0
            prices.append(price)
        for _ in range(8):
            price -= 1.0
            prices.append(price)
    return [
        {"open": p - 0.2, "high": p + 0.4, "low": p - 0.4, "close": p, "volume": 1000, "time": idx}
        for idx, p in enumerate(prices)
    ]


def test_validate_strategy_proposal_accepts_crypto_schema():
    proposal = validate_strategy_proposal(_proposal())

    assert proposal.name == "btc_eth_trend_pullback_v1"
    assert proposal.market == "crypto"
    assert proposal.timeframes["entry"] == "M15"


def test_validate_strategy_proposal_rejects_unknown_timeframe():
    raw = _proposal()
    raw["timeframes"]["entry"] = "M2"

    with pytest.raises(StrategyValidationError):
        validate_strategy_proposal(raw)


def test_crypto_backtest_returns_gate_report():
    proposal = validate_strategy_proposal(_proposal())

    report = run_crypto_backtest(proposal, "BTCUSDT", _candles())

    assert report.symbol == "BTCUSDT"
    assert report.trades >= 5
    assert isinstance(report.approved_for_forward_test, bool)
    assert "trade_log" in report.to_dict()


def test_registry_upsert_and_filter_approved(tmp_path: Path):
    proposal = validate_strategy_proposal(_proposal())
    registry = StrategyRegistry(tmp_path / "approved_strategies.json")

    registry.upsert(proposal.to_dict(), status="approved", report={"profit_factor": 1.5})

    approved = registry.approved("crypto")
    assert len(approved) == 1
    assert approved[0]["name"] == proposal.name
    assert approved[0]["latest_report"]["profit_factor"] == 1.5
