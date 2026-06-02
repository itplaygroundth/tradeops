"""Sub-agent competition tests — 8 strategies"""
import pytest
import asyncio
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from engine.sub_agent import SubAgent, ForwardTestResult

import math

def make_candles_sine(n=200):
    """Sine-wave candles for predictable signal testing."""
    now = time.time()
    candles = []
    for i in range(n):
        price = 1.1 + math.sin(i * 0.15) * 0.003
        candles.append({
            "open": price - 0.0001,
            "high": price + 0.0003,
            "low": price - 0.0003,
            "close": price,
            "volume": 1000 + i * 5,
            "timestamp": now + i * 60,
        })
    return candles

ALL_STRATS = ["momentum","mean_reversion","grid_scalp","llm_sentiment",
              "order_flow","breakout_atr","session_open","market_structure"]

def make_cfg(primary):
    cfg = {s: 0.0 for s in ALL_STRATS}
    cfg[primary] = 1.0
    return cfg

def test_subagent_backtest_order_flow():
    candles = make_candles_sine()
    sub = SubAgent("EURUSDm", make_cfg("order_flow"))
    result = asyncio.run(sub.run_backtest(candles))
    assert hasattr(result, "sharpe")
    assert isinstance(result.trades, int)

def test_subagent_backtest_breakout_atr():
    candles = make_candles_sine()
    sub = SubAgent("EURUSDm", make_cfg("breakout_atr"))
    result = asyncio.run(sub.run_backtest(candles))
    assert hasattr(result, "sharpe")
    assert 0.0 <= result.win_rate <= 1.0

def test_subagent_backtest_session_open():
    candles = make_candles_sine()
    sub = SubAgent("EURUSDm", make_cfg("session_open"))
    result = asyncio.run(sub.run_backtest(candles))
    assert hasattr(result, "sharpe")

def test_subagent_backtest_market_structure():
    candles = make_candles_sine()
    sub = SubAgent("EURUSDm", make_cfg("market_structure"))
    result = asyncio.run(sub.run_backtest(candles))
    assert hasattr(result, "sharpe")
    assert isinstance(result.trades, int)

def test_backtest_result_fields():
    """All 8 strategies must return valid BacktestResult fields."""
    candles = make_candles_sine()
    for strat in ALL_STRATS:
        sub = SubAgent("EURUSDm", make_cfg(strat))
        result = asyncio.run(sub.run_backtest(candles))
        assert hasattr(result, "sharpe"), f"{strat} missing sharpe"
        assert hasattr(result, "pnl"), f"{strat} missing pnl"
        assert hasattr(result, "pnl_pct"), f"{strat} missing pnl_pct"
        assert hasattr(result, "win_rate"), f"{strat} missing win_rate"
        assert 0.0 <= result.win_rate <= 1.0, f"{strat} win_rate out of range: {result.win_rate}"
        assert hasattr(result, "max_drawdown"), f"{strat} missing max_drawdown"
        assert hasattr(result, "trades"), f"{strat} missing trades"
        assert hasattr(result, "strategy_config"), f"{strat} missing strategy_config"

def test_make_configs_12_distinct():
    """AssetLeader._make_configs returns 12 distinct configs summing to 1.0."""
    from engine.asset_leader import AssetLeader
    leader = AssetLeader("EURUSDm", None, None, None)
    configs = leader._make_configs()
    assert len(configs) == 12
    unique = [str(sorted(c.items())) for c in configs]
    assert len(set(unique)) == 12, f"only {len(set(unique))} unique"
    for i, c in enumerate(configs):
        total = sum(c.values())
        assert abs(total - 1.0) < 1e-9, f"config {i} sum={total}"


def test_forward_test_momentum_produces_trades():
    """run_forward_test dispatches to _backtest_momentum and returns >=1 trade."""
    # Build scripted price sequence: 30 rising then 15 falling
    rising = [1.10 + i * 0.001 for i in range(30)]   # 1.100 … 1.129
    falling = [1.130 - i * 0.001 for i in range(15)]  # 1.130 … 1.116
    prices = rising + falling

    call_count = [0]

    def get_price(_symbol):
        idx = min(call_count[0], len(prices) - 1)
        val = prices[idx]
        call_count[0] += 1
        return SimpleNamespace(mid=val, timestamp=1000 + call_count[0])

    fake_mt5 = MagicMock()
    fake_mt5.get_price = get_price  # plain function, not async

    sub = SubAgent("EURUSDm", make_cfg("momentum"), mt5_client=fake_mt5)

    # clock: 0.0, then 0.1*i for i in 1..399, then 9999 (crosses end_ts=10 after ~100)
    times = iter([0.0] + [0.1 * i for i in range(1, 400)] + [9999.0] * 50)

    loop_mock = MagicMock()
    loop_mock.time = lambda: next(times)

    async def run():
        with patch("engine.sub_agent.asyncio.sleep", new=AsyncMock()), \
             patch("engine.sub_agent.asyncio.get_running_loop", return_value=loop_mock):
            return await sub.run_forward_test(duration_seconds=10)

    result = asyncio.run(run())

    assert isinstance(result, ForwardTestResult)
    assert result.trade_count >= 1
    assert result.pnl != 0.0
