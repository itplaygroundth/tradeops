from strategy_lab.backtest import run_crypto_backtest
from strategy_lab.schema import validate_strategy_proposal


def _breakout_candles():
    prices = []
    price = 100.0
    for cycle in range(6):
        for _ in range(20):
            price += 0.05
            prices.append(price)
        for _ in range(6):
            price += 1.2
            prices.append(price)
        for _ in range(8):
            price -= 0.4
            prices.append(price)
    return [
        {"open": p - 0.2, "high": p + 0.6, "low": p - 0.6, "close": p, "volume": 1000, "time": idx}
        for idx, p in enumerate(prices)
    ]


def _base(name, strategy_type, parameters):
    return validate_strategy_proposal({
        "name": name,
        "market": "crypto",
        "symbols": ["BTCUSDT", "ETHUSDT"],
        "timeframes": {"entry": "M15", "confirm": "H1", "regime": "H4"},
        "type": strategy_type,
        "entry_rules": [{"action": "LONG", "when": "unit"}],
        "exit_rules": [{"action": "HOLD", "when": "unit"}],
        "risk_rules": {"risk_pct": 0.005},
        "parameters": parameters,
    })


def test_breakout_strategy_generates_backtest_trades():
    proposal = _base("unit_breakout", "breakout", {
        "fast_sma": 3,
        "slow_sma": 8,
        "breakout_lookback": 12,
        "min_atr_pct": 0.01,
        "max_atr_pct": 5.0,
        "max_entry_rsi": 95,
        "max_hold_bars": 6,
        "fee_bps": 1,
        "slippage_bps": 1,
    })

    report = run_crypto_backtest(proposal, "BTCUSDT", _breakout_candles())

    assert report.trades > 0
    assert report.strategy_name == "unit_breakout"


def test_mean_reversion_strategy_runs_without_crash():
    proposal = _base("unit_mean_reversion", "mean_reversion", {
        "mean_window": 10,
        "entry_deviation_pct": 0.2,
        "exit_deviation_pct": -0.05,
        "max_oversold_rsi": 45,
        "max_hold_bars": 8,
        "fee_bps": 1,
        "slippage_bps": 1,
    })

    report = run_crypto_backtest(proposal, "BTCUSDT", _breakout_candles())

    assert isinstance(report.trades, int)
