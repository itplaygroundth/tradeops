from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from math import sqrt
from statistics import mean, pstdev
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


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
        elif primary == "order_flow":
            trades, max_dd = self._backtest_order_flow(closes, candles)
        elif primary == "breakout_atr":
            trades, max_dd = self._backtest_breakout_atr(closes, candles)
        elif primary == "session_open":
            trades, max_dd = self._backtest_session_open(closes, candles)
        elif primary == "market_structure":
            trades, max_dd = self._backtest_market_structure(closes)
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

        Dispatches to the same _backtest_* helpers as run_backtest, feeding
        tick-derived synthetic OHLCV candles.
        """
        if self.mt5 is None:
            await asyncio.sleep(min(1, duration_seconds))
            return ForwardTestResult(0.0, 0.0, 0, 0.0)

        _OHLCV_STRATEGIES = {"order_flow", "breakout_atr", "session_open"}

        primary = max(self.strategy_config.items(), key=lambda kv: kv[1])[0]

        if primary in _OHLCV_STRATEGIES:
            logger.warning(
                "forward_test: tick-derived OHLCV approximate for %s on %s",
                primary,
                self.symbol,
            )

        def _to_price(tick) -> float:
            return getattr(tick, "mid", None) or getattr(tick, "price", None) or float(tick)

        end_ts = asyncio.get_running_loop().time() + duration_seconds

        try:
            first_tick = await maybe_await(self.mt5.get_price(self.symbol))
        except Exception:
            await asyncio.sleep(min(1, duration_seconds))
            return ForwardTestResult(0.0, 0.0, 0, 0.0)

        first_mid = _to_price(first_tick)
        closes: List[float] = [first_mid]
        candle_series: List[dict] = [{
            "open": first_mid, "high": first_mid, "low": first_mid,
            "close": first_mid, "volume": 1,
            "timestamp": getattr(first_tick, "timestamp", None) or len(closes),
        }]

        while asyncio.get_running_loop().time() < end_ts:
            try:
                tick = await maybe_await(self.mt5.get_price(self.symbol))
            except Exception:
                await asyncio.sleep(1)
                continue
            mid = _to_price(tick)
            closes.append(mid)
            candle_series.append({
                "open": mid, "high": mid, "low": mid, "close": mid, "volume": 1,
                "timestamp": getattr(tick, "timestamp", None) or len(closes),
            })
            await asyncio.sleep(1)

        if primary == "momentum":
            trades_list, max_dd = self._backtest_momentum(closes)
        elif primary == "mean_reversion":
            trades_list, max_dd = self._backtest_mean_reversion(closes)
        elif primary == "market_structure":
            trades_list, max_dd = self._backtest_market_structure(closes)
        elif primary == "order_flow":
            trades_list, max_dd = self._backtest_order_flow(closes, candle_series)
        elif primary == "breakout_atr":
            trades_list, max_dd = self._backtest_breakout_atr(closes, candle_series)
        elif primary == "session_open":
            trades_list, max_dd = self._backtest_session_open(closes, candle_series)
        else:
            trades_list, max_dd = [], 0.0

        pnl = sum(trades_list)
        trade_count = len(trades_list)
        pnl_pct = pnl
        return ForwardTestResult(pnl, max_dd, trade_count, pnl_pct)

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

    def _backtest_order_flow(self, closes, candles):
        """CVD divergence: sum(sign(close-open)*volume). Signal when CVD diverges from price momentum."""
        trades = []
        window = 20
        in_pos = False
        entry = 0.0
        direction = 0

        for i in range(window, len(candles)):
            slice_c = candles[i - window: i]
            cvd = sum((1 if c["close"] > c["open"] else -1) * c.get("volume", 1) for c in slice_c)
            mom = (closes[i] - closes[i - window]) / (closes[i - window] or 1e-10) * 100.0
            price = closes[i]

            if not in_pos:
                if mom > 0.3 and cvd < 0:
                    in_pos, direction, entry = True, -1, price
                elif mom < -0.3 and cvd > 0:
                    in_pos, direction, entry = True, 1, price
            else:
                rev_mom = (closes[i] - closes[max(0, i - 5)]) / (closes[max(0, i - 5)] or 1e-10) * 100.0
                if (direction == 1 and rev_mom < -0.1) or (direction == -1 and rev_mom > 0.1):
                    ret = direction * (price - entry) / entry * 100.0
                    trades.append(ret)
                    in_pos = False

        if in_pos:
            trades.append(direction * (closes[-1] - entry) / entry * 100.0)
        return trades, 0.0

    def _backtest_breakout_atr(self, closes, candles):
        """Breakout above 20-bar high or below 20-bar low, with ATR filter."""
        trades = []
        window = 20
        atr_window = 14
        in_pos = False
        entry = 0.0
        direction = 0

        for i in range(window, len(candles)):
            highs = [c["high"] for c in candles[i - window: i]]
            lows = [c["low"] for c in candles[i - window: i]]
            hi20 = max(highs)
            lo20 = min(lows)
            price = closes[i]

            atr_bars = candles[max(0, i - atr_window): i]
            atr = mean([c["high"] - c["low"] for c in atr_bars]) if atr_bars else 0.0
            atr_pct = atr / price * 100.0 if price else 0.0

            if not in_pos and atr_pct < 0.6:
                if price > hi20:
                    in_pos, direction, entry = True, 1, price
                elif price < lo20:
                    in_pos, direction, entry = True, -1, price
            elif in_pos:
                sl = atr * 2
                pnl_abs = direction * (price - entry)
                if pnl_abs < -sl or (direction == 1 and price < lo20) or (direction == -1 and price > hi20):
                    trades.append(direction * (price - entry) / entry * 100.0)
                    in_pos = False

        if in_pos:
            trades.append(direction * (closes[-1] - entry) / entry * 100.0)
        return trades, 0.0

    def _backtest_session_open(self, closes, candles):
        """Signal in first 30 bars of session (proxy for London 07:00 open momentum)."""
        trades = []
        window = 5
        in_pos = False
        entry = 0.0
        direction = 0

        for i in range(window, len(candles)):
            ts = candles[i].get("timestamp", i)
            # NOTE: ts is a Unix timestamp proxy; int(ts or i) guards against None
            bar_in_session = int(ts or i) % 480
            if bar_in_session > 30:
                continue

            price = closes[i]
            mom = (closes[i] - closes[i - window]) / (closes[i - window] or 1e-10) * 100.0

            if not in_pos:
                if mom > 0.2:
                    in_pos, direction, entry = True, 1, price
                elif mom < -0.2:
                    in_pos, direction, entry = True, -1, price
            else:
                if bar_in_session > 20:
                    trades.append(direction * (price - entry) / entry * 100.0)
                    in_pos = False

        if in_pos:
            trades.append(direction * (closes[-1] - entry) / entry * 100.0)
        return trades, 0.0

    def _backtest_market_structure(self, closes):
        """Break of Structure: higher high = bullish BoS, lower low = bearish BoS."""
        trades = []
        swing_window = 10
        in_pos = False
        entry = 0.0
        direction = 0
        prev_hh = None
        prev_ll = None

        for i in range(swing_window * 2, len(closes)):
            window_slice = closes[i - swing_window: i]
            hh = max(window_slice)
            ll = min(window_slice)
            price = closes[i]

            if prev_hh is not None and prev_ll is not None:
                if not in_pos:
                    if price > prev_hh:
                        in_pos, direction, entry = True, 1, price
                    elif price < prev_ll:
                        in_pos, direction, entry = True, -1, price
                else:
                    if direction == 1 and price < ll:
                        trades.append((price - entry) / entry * 100.0)
                        in_pos = False
                    elif direction == -1 and price > hh:
                        trades.append(-(price - entry) / entry * 100.0)
                        in_pos = False

            prev_hh = hh
            prev_ll = ll

        if in_pos:
            trades.append(direction * (closes[-1] - entry) / entry * 100.0)
        return trades, 0.0


async def maybe_await(x):
    if asyncio.iscoroutine(x):
        return await x
    return x
