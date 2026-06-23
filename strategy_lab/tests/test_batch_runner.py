from pathlib import Path

from strategy_lab.batch_runner import run_batch_optimize


def _proposal(path: Path):
    path.write_text("""{
      "name": "unit_batch_strategy",
      "version": 1,
      "market": "crypto",
      "symbols": ["BTCUSDT"],
      "timeframes": {"entry": "M15", "confirm": "H1", "regime": "H4"},
      "type": "trend_following",
      "entry_rules": [{"action": "LONG", "when": "unit"}],
      "exit_rules": [{"action": "HOLD", "when": "unit"}],
      "risk_rules": {"risk_pct": 0.005},
      "parameters": {"fast_sma": 3, "slow_sma": 8, "max_hold_bars": 6, "fee_bps": 1, "slippage_bps": 1},
      "status": "draft"
    }""")


def _candles():
    prices = []
    price = 100.0
    for _ in range(8):
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


def test_run_batch_optimize_writes_reports(tmp_path):
    proposal_path = tmp_path / "strategy.json"
    _proposal(proposal_path)

    def fake_fetcher(symbol, timeframe="M15", count=500, network="production"):
        assert symbol == "BTCUSDT"
        return _candles()

    report = run_batch_optimize(
        str(proposal_path),
        reports_dir=tmp_path / "reports",
        registry_path=tmp_path / "registry.json",
        fetcher=fake_fetcher,
    )

    assert report.proposals == 1
    assert report.runs == 1
    assert report.items[0]["report_path"].endswith("_optimize.json")
    assert Path(report.items[0]["report_path"]).exists()
