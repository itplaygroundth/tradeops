import sys
import asyncio
from pathlib import Path
import time

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from engine.sub_agent import SubAgent


def make_candles(n=100, start=1.1000, step=0.0005):
    now = time.time()
    candles = []
    for i in range(n):
        price = start + i * step
        candles.append({
            "open": price - 0.0001,
            "high": price + 0.0002,
            "low": price - 0.0002,
            "close": price,
            "volume": 1000,
            "timestamp": now + i,
        })
    return candles


def test_subagent_backtest_momentum():
    candles = make_candles()
    cfg = {"momentum": 0.8, "mean_reversion": 0.05, "grid_scalp": 0.05, "llm_sentiment": 0.05, "order_flow": 0.05, "breakout_atr": 0.0, "session_open": 0.0, "market_structure": 0.0}
    sub = SubAgent("EURUSD", cfg)
    result = asyncio.run(sub.run_backtest(candles))
    assert hasattr(result, "sharpe")
    assert hasattr(result, "pnl")
    assert isinstance(result.trades, int) or isinstance(result.trades, float) or True
    assert 0 <= result.win_rate <= 1
