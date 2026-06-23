from __future__ import annotations

from dataclasses import dataclass, asdict
from math import sqrt
from statistics import mean, pstdev
from typing import Any, Dict, List

from .schema import StrategyProposal


@dataclass
class Trade:
    side: str
    entry_index: int
    exit_index: int
    entry_price: float
    exit_price: float
    pnl_pct: float
    reason: str


@dataclass
class BacktestReport:
    strategy_name: str
    symbol: str
    timeframe: str
    trades: int
    win_rate: float
    total_pnl_pct: float
    expectancy_pct: float
    profit_factor: float
    max_drawdown_pct: float
    sharpe: float
    approved_for_forward_test: bool
    gate_reasons: List[str]
    trade_log: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _close(candle: Dict[str, Any]) -> float:
    return float(candle["close"])


def _sma(values: List[float], window: int) -> float:
    return sum(values[-window:]) / window


def _rsi(values: List[float], period: int = 14) -> float:
    if len(values) < period + 1:
        return 50.0
    gains = 0.0
    losses = 0.0
    recent = values[-(period + 1):]
    for prev, cur in zip(recent, recent[1:]):
        delta = cur - prev
        if delta >= 0:
            gains += delta
        else:
            losses += abs(delta)
    if losses == 0:
        return 100.0
    rs = (gains / period) / (losses / period)
    return 100 - (100 / (1 + rs))


def run_crypto_backtest(proposal: StrategyProposal, symbol: str, candles: List[Dict[str, Any]]) -> BacktestReport:
    if proposal.market != "crypto":
        raise ValueError("run_crypto_backtest only accepts crypto proposals")
    if symbol not in proposal.symbols:
        raise ValueError(f"{symbol} is not in proposal symbols")
    closes = [_close(candle) for candle in candles]
    timeframe = proposal.timeframes.get("entry", "M15")
    params = proposal.parameters
    fee_bps = float(params.get("fee_bps", 10.0))
    slippage_bps = float(params.get("slippage_bps", 2.0))
    fast = int(params.get("fast_sma", 9))
    slow = int(params.get("slow_sma", 21))
    hold_bars = int(params.get("max_hold_bars", 12))
    min_bars = max(slow + 2, 30)

    trades: List[Trade] = []
    in_position = False
    entry_price = 0.0
    entry_index = 0

    for idx in range(min_bars, len(closes)):
        history = closes[: idx + 1]
        price = history[-1]
        fast_sma = _sma(history, fast)
        slow_sma = _sma(history, slow)
        rsi = _rsi(history)
        if not in_position and _entry_signal(proposal.strategy_type, history, candles[: idx + 1], params):
                in_position = True
                entry_price = price
                entry_index = idx
        elif in_position:
            exit_signal = _exit_signal(proposal.strategy_type, history, candles[: idx + 1], params) or idx - entry_index >= hold_bars
            if exit_signal:
                gross = (price - entry_price) / entry_price * 100
                cost = (fee_bps + slippage_bps) * 2 / 100
                pnl = gross - cost
                trades.append(Trade("LONG", entry_index, idx, entry_price, price, pnl, "exit_signal"))
                in_position = False

    if in_position and closes:
        price = closes[-1]
        gross = (price - entry_price) / entry_price * 100
        cost = (fee_bps + slippage_bps) * 2 / 100
        trades.append(Trade("LONG", entry_index, len(closes) - 1, entry_price, price, gross - cost, "final_close"))

    return _build_report(proposal.name, symbol, timeframe, trades)


def _entry_signal(strategy_type: str, closes: List[float], candles: List[Dict[str, Any]], params: Dict[str, Any]) -> bool:
    price = closes[-1]
    fast = int(params.get("fast_sma", 9))
    slow = int(params.get("slow_sma", 21))
    fast_sma = _sma(closes, fast)
    slow_sma = _sma(closes, slow)
    rsi = _rsi(closes)
    if strategy_type in ("trend_following", "market_structure"):
        return fast_sma > slow_sma and rsi < float(params.get("max_entry_rsi", 72))
    if strategy_type == "breakout":
        lookback = int(params.get("breakout_lookback", 20))
        if len(closes) <= lookback:
            return False
        resistance = max(closes[-lookback - 1:-1])
        atr_pct = _atr_percent(candles, int(params.get("atr_period", 14)))
        return (
            price > resistance
            and atr_pct >= float(params.get("min_atr_pct", 0.05))
            and atr_pct <= float(params.get("max_atr_pct", 2.5))
            and rsi < float(params.get("max_entry_rsi", 78))
        )
    if strategy_type == "mean_reversion":
        window = int(params.get("mean_window", 20))
        if len(closes) < window:
            return False
        mean_price = _sma(closes, window)
        deviation = (price - mean_price) / mean_price * 100 if mean_price else 0.0
        return deviation <= -float(params.get("entry_deviation_pct", 0.6)) and rsi <= float(params.get("max_oversold_rsi", 35))
    return False


def _exit_signal(strategy_type: str, closes: List[float], candles: List[Dict[str, Any]], params: Dict[str, Any]) -> bool:
    price = closes[-1]
    fast = int(params.get("fast_sma", 9))
    slow = int(params.get("slow_sma", 21))
    if strategy_type in ("trend_following", "market_structure", "breakout"):
        return _sma(closes, fast) < _sma(closes, slow)
    if strategy_type == "mean_reversion":
        window = int(params.get("mean_window", 20))
        if len(closes) < window:
            return False
        mean_price = _sma(closes, window)
        deviation = (price - mean_price) / mean_price * 100 if mean_price else 0.0
        return deviation >= float(params.get("exit_deviation_pct", 0.0))
    return False


def _atr_percent(candles: List[Dict[str, Any]], period: int = 14) -> float:
    if len(candles) < period + 1:
        return 0.0
    trs = []
    for idx in range(len(candles) - period, len(candles)):
        candle = candles[idx]
        prev_close = float(candles[idx - 1]["close"])
        high = float(candle["high"])
        low = float(candle["low"])
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    last = float(candles[-1]["close"])
    return (sum(trs) / len(trs)) / last * 100 if last and trs else 0.0


def _build_report(strategy_name: str, symbol: str, timeframe: str, trades: List[Trade]) -> BacktestReport:
    pnls = [trade.pnl_pct for trade in trades]
    wins = [pnl for pnl in pnls if pnl > 0]
    losses = [pnl for pnl in pnls if pnl <= 0]
    total = sum(pnls)
    profit_factor = (sum(wins) / abs(sum(losses))) if losses and abs(sum(losses)) > 0 else (999.0 if wins else 0.0)
    expectancy = mean(pnls) if pnls else 0.0
    win_rate = (len(wins) / len(pnls)) if pnls else 0.0
    max_dd = _max_drawdown(pnls)
    sharpe = _sharpe(pnls)
    gate_reasons = []
    if len(pnls) < 5:
        gate_reasons.append("not enough trades")
    if expectancy <= 0:
        gate_reasons.append("expectancy is not positive")
    if profit_factor < 1.15:
        gate_reasons.append("profit factor below 1.15")
    if max_dd > 8.0:
        gate_reasons.append("max drawdown above 8%")
    approved = not gate_reasons
    return BacktestReport(
        strategy_name=strategy_name,
        symbol=symbol,
        timeframe=timeframe,
        trades=len(pnls),
        win_rate=round(win_rate, 4),
        total_pnl_pct=round(total, 4),
        expectancy_pct=round(expectancy, 4),
        profit_factor=round(profit_factor, 4),
        max_drawdown_pct=round(max_dd, 4),
        sharpe=round(sharpe, 4),
        approved_for_forward_test=approved,
        gate_reasons=gate_reasons,
        trade_log=[asdict(trade) for trade in trades],
    )


def _max_drawdown(pnls: List[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for pnl in pnls:
        equity += pnl
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return max_dd


def _sharpe(pnls: List[float]) -> float:
    if len(pnls) < 2:
        return 0.0
    sigma = pstdev(pnls)
    if sigma == 0:
        return 0.0
    return mean(pnls) / sigma * sqrt(252)
