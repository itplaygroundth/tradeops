from __future__ import annotations

import asyncio
from dataclasses import dataclass
from math import sqrt
from statistics import mean, pstdev
from typing import Any, Dict, List, Optional


@dataclass
class BacktestResult:
    sharpe: float
    pnl: float
    pnl_pct: float
    win_rate: float
    max_drawdown: float
    trades: int
    strategy_config: Dict[str, Any]


@dataclass
class ForwardTestResult:
    pnl: float
    max_drawdown: float
    trade_count: int
    pnl_pct: float


class SubAgent:
    """Lightweight SubAgent skeleton.

    - Chooses a primary strategy by picking the largest weight in `strategy_config`.
    - `run_backtest` implements a minimal bar-by-bar simulator for demo purposes.
    """

    def __init__(self, symbol: str, strategy_config: Dict[str, float], mt5_client: Optional[Any] = None):
        self.symbol = symbol
        self.strategy_config = strategy_config
        self.mt5 = mt5_client

    async def run_backtest(self, candles: List[Dict[str, Any]]) -> BacktestResult:
        """Run a simple backtest over `candles` (list of OHLCV dicts).

        This is intentionally minimal: it selects a primary strategy (max weight)
        and runs a basic SMA momentum or mean-reversion simulation.
        """
        if not candles:
            return BacktestResult(0.0, 0.0, 0.0, 0.0, 0.0, 0, self.strategy_config)

        # pick primary strategy
        primary = max(self.strategy_config.items(), key=lambda kv: kv[1])[0]

        closes = [c["close"] for c in candles]

        trades = []  # list of pnl percentages per trade
        max_dd = 0.0

        if primary == "momentum":
            trades, max_dd = self._backtest_momentum(closes)
        elif primary == "mean_reversion":
            trades, max_dd = self._backtest_mean_reversion(closes)
        else:
            # fallback: no trades
            trades = []

        pnl = sum(trades)
        trades_count = len(trades)
        win_rate = (sum(1 for t in trades if t > 0) / trades_count) if trades_count else 0.0
        pnl_pct = pnl

        # daily returns approximated by splitting series into days (naive)
        daily_returns = trades if trades else [0.0]
        mu = mean(daily_returns)
        sigma = pstdev(daily_returns) if len(daily_returns) > 1 else 0.0
        sharpe = (mu / sigma * sqrt(252)) if sigma > 0 else 0.0

        return BacktestResult(sharpe, pnl, pnl_pct, win_rate, max_dd, trades_count, self.strategy_config)

    async def run_forward_test(self, duration_seconds: int = 900) -> ForwardTestResult:
        """Paper-trade on live prices for `duration_seconds`.

        Skeleton implementation: if `mt5` client provided, attempt to observe prices,
        otherwise sleep and return zeros.
        """
        if self.mt5 is None:
            await asyncio.sleep(min(1, duration_seconds))
            return ForwardTestResult(0.0, 0.0, 0, 0.0)

        end_ts = asyncio.get_event_loop().time() + duration_seconds
        pnl = 0.0
        trades = 0
        max_dd = 0.0

        # naive watcher: poll price every second (mt5 client should expose `get_price`)
        try:
            prev_price = await maybe_await(self.mt5.get_price(self.symbol))
        except Exception:
            await asyncio.sleep(min(1, duration_seconds))
            return ForwardTestResult(0.0, 0.0, 0, 0.0)

        while asyncio.get_event_loop().time() < end_ts:
            try:
                price = await maybe_await(self.mt5.get_price(self.symbol))
            except Exception:
                await asyncio.sleep(1)
                continue
            # no real trading logic here; measure tiny drift as pnl
            pnl += (price - prev_price) / prev_price * 100.0
            prev_price = price
            await asyncio.sleep(1)

        return ForwardTestResult(pnl, max_dd, trades, pnl)

    def _backtest_momentum(self, closes: List[float]):
        short_w = 5
        long_w = 20
        trades = []
        in_pos = False
        entry = 0.0
        peak = 0.0

        for i in range(len(closes)):
            if i < long_w:
                continue
            short = mean(closes[i - short_w + 1: i + 1])
            long = mean(closes[i - long_w + 1: i + 1])
            price = closes[i]
            if not in_pos and short > long:
                in_pos = True
                entry = price
                peak = price
            elif in_pos:
                peak = max(peak, price)
                # exit on short < long
                if short < long:
                    ret = (price - entry) / entry * 100.0
                    trades.append(ret)
                    in_pos = False
        # close open position
        if in_pos:
            ret = (closes[-1] - entry) / entry * 100.0
            trades.append(ret)

        max_dd = 0.0
        return trades, max_dd

    def _backtest_mean_reversion(self, closes: List[float]):
        window = 20
        trades = []
        in_pos = False
        entry = 0.0

        for i in range(len(closes)):
            if i < window:
                continue
            avg = mean(closes[i - window + 1: i + 1])
            price = closes[i]
            dev = (price - avg) / avg
            if not in_pos and dev < -0.005:  # price below mean -> buy
                in_pos = True
                entry = price
            elif in_pos and dev > 0.0:
                ret = (price - entry) / entry * 100.0
                trades.append(ret)
                in_pos = False

        if in_pos:
            ret = (closes[-1] - entry) / entry * 100.0
            trades.append(ret)

        max_dd = 0.0
        return trades, max_dd


async def maybe_await(x):
    if asyncio.iscoroutine(x):
        return await x
    return x
