"""Tests for MarkovRegimeDetector."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest
from engine.markov_regime import detect_regime, STATES


def _make_candles(rets, base=1.0):
    """Build minimal OHLCV candles from a list of daily returns."""
    candles = []
    price = base
    for r in rets:
        open_ = price
        close = price * (1 + r)
        high = max(open_, close) * 1.002
        low = min(open_, close) * 0.998
        candles.append({"open": open_, "high": high, "low": low, "close": close, "volume": 1000})
        price = close
    return candles


def test_trending_up_detected():
    rets = [0.005] * 30  # consistent +0.5% daily
    regime, trans = detect_regime(_make_candles(rets))
    assert regime == "TREND_UP"
    assert "TREND_UP" in trans


def test_trending_down_detected():
    rets = [-0.005] * 30
    regime, _ = detect_regime(_make_candles(rets))
    assert regime == "TREND_DOWN"


def test_ranging_detected():
    # alternate +0.1% / -0.1% → no direction
    rets = [0.001 if i % 2 == 0 else -0.001 for i in range(30)]
    regime, _ = detect_regime(_make_candles(rets))
    assert regime == "RANGING"


def test_insufficient_data_defaults_ranging():
    regime, trans = detect_regime([])
    assert regime == "RANGING"
    for s in STATES:
        assert abs(sum(trans[s].values()) - 1.0) < 1e-6


def test_transition_probs_sum_to_one():
    rets = [0.004, -0.003, 0.001, -0.001, 0.006] * 10
    _, trans = detect_regime(_make_candles(rets))
    for s in STATES:
        assert abs(sum(trans[s].values()) - 1.0) < 1e-6, f"row {s} doesn't sum to 1"


def test_regime_in_asset_leader_configs():
    """_make_configs biases sum=1 configs for each regime."""
    from engine.asset_leader import AssetLeader
    KEYS = list({"momentum", "mean_reversion", "grid_scalp", "llm_sentiment",
                 "order_flow", "breakout_atr", "session_open", "market_structure"})

    for regime in ("TREND_UP", "TREND_DOWN", "RANGING"):
        al = AssetLeader("EURUSDm", None, None, None)
        cfgs = al._make_configs(regime)
        assert len(cfgs) == 12
        for cfg in cfgs:
            total = sum(cfg.values())
            assert abs(total - 1.0) < 1e-4, f"cfg sum={total} for regime={regime}"

    # TREND_UP: momentum weight should dominate vs RANGING config 0
    cfgs_trend = AssetLeader("EURUSDm", None, None, None)._make_configs("TREND_UP")
    cfgs_range = AssetLeader("EURUSDm", None, None, None)._make_configs("RANGING")
    # config 0 is momentum-heavy; under TREND_UP momentum share > RANGING momentum share
    assert cfgs_trend[0]["momentum"] > cfgs_range[0]["momentum"]
    # RANGING: mean_reversion share in config 1 > TREND_UP
    assert cfgs_range[1]["mean_reversion"] > cfgs_trend[1]["mean_reversion"]
