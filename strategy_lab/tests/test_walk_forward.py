from strategy_lab.schema import validate_strategy_proposal
from strategy_lab.walk_forward import build_walk_forward_splits, run_walk_forward


def _proposal():
    return validate_strategy_proposal({
        "name": "unit_mean_reversion",
        "market": "crypto",
        "symbols": ["BTCUSDT"],
        "timeframes": {"entry": "M15", "confirm": "H1", "regime": "H4"},
        "type": "mean_reversion",
        "entry_rules": [{"action": "LONG", "when": "unit"}],
        "exit_rules": [{"action": "HOLD", "when": "unit"}],
        "risk_rules": {"risk_pct": 0.003},
        "parameters": {
            "mean_window": 10,
            "entry_deviation_pct": 0.2,
            "exit_deviation_pct": -0.05,
            "max_hold_bars": 8,
            "fee_bps": 1,
            "slippage_bps": 1,
        },
    })


def _candles(length=180):
    prices = []
    price = 100.0
    for idx in range(length):
        phase = idx % 18
        if phase < 6:
            price -= 0.6
        elif phase < 12:
            price += 0.8
        else:
            price += 0.1
        prices.append(price)
    return [
        {"open": p - 0.2, "high": p + 0.4, "low": p - 0.4, "close": p, "volume": 1000, "time": idx}
        for idx, p in enumerate(prices)
    ]


def test_build_walk_forward_splits():
    splits = build_walk_forward_splits(_candles(100), train_size=40, test_size=20, step_size=20)

    assert splits == [(0, 40, 40, 60), (20, 60, 60, 80), (40, 80, 80, 100)]


def test_run_walk_forward_returns_window_reports():
    report = run_walk_forward(_proposal(), "BTCUSDT", _candles(), train_size=60, test_size=30, step_size=30)

    assert report.windows > 0
    assert len(report.window_reports) == report.windows
    assert isinstance(report.approved_for_forward_test, bool)
