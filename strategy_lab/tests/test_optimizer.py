from strategy_lab.optimizer import optimize_crypto_strategy, parameter_grid
from strategy_lab.schema import validate_strategy_proposal


def _proposal():
    return validate_strategy_proposal({
        "name": "btc_eth_trend_pullback_v1",
        "market": "crypto",
        "symbols": ["BTCUSDT", "ETHUSDT"],
        "timeframes": {"entry": "M15", "confirm": "H1", "regime": "H4"},
        "type": "trend_following",
        "entry_rules": [{"action": "LONG", "when": "fast_sma_above_slow_sma"}],
        "exit_rules": [{"action": "HOLD", "when": "fast_sma_below_slow_sma"}],
        "risk_rules": {"risk_pct": 0.005},
        "parameters": {"fee_bps": 1, "slippage_bps": 1},
    })


def _candles():
    prices = []
    price = 100.0
    for _ in range(10):
        for _ in range(8):
            price -= 0.7
            prices.append(price)
        for _ in range(12):
            price += 1.0
            prices.append(price)
        for _ in range(6):
            price -= 0.8
            prices.append(price)
    return [
        {"open": p - 0.2, "high": p + 0.4, "low": p - 0.4, "close": p, "volume": 1000, "time": idx}
        for idx, p in enumerate(prices)
    ]


def test_parameter_grid_builds_combinations():
    rows = parameter_grid({"a": [1, 2], "b": ["x", "y"]})

    assert rows == [
        {"a": 1, "b": "x"},
        {"a": 1, "b": "y"},
        {"a": 2, "b": "x"},
        {"a": 2, "b": "y"},
    ]


def test_optimize_crypto_strategy_ranks_candidates():
    grid = {
        "fast_sma": [3, 5],
        "slow_sma": [8, 13],
        "max_entry_rsi": [72],
        "max_hold_bars": [6, 10],
    }

    result = optimize_crypto_strategy(_proposal(), "BTCUSDT", _candles(), grid=grid, top_n=3)

    assert result.tested == 8
    assert len(result.top) == 3
    assert result.best is not None
    assert "parameters" in result.best
    assert result.top[0]["score"] >= result.top[-1]["score"]
