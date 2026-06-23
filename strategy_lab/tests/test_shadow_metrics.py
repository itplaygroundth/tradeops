import json

from strategy_lab.shadow_metrics import summarize_shadow_signals


def test_shadow_metrics_summarize_outcomes(tmp_path):
    signals = tmp_path / "signals.jsonl"
    rows = [
        {"strategy_name": "alpha", "action": "LONG", "theoretical_pnl_pct": 0.5},
        {"strategy_name": "alpha", "action": "LONG", "theoretical_pnl_pct": -0.2},
        {"strategy_name": "beta", "action": "HOLD"},
    ]
    signals.write_text("\n".join(json.dumps(row) for row in rows) + "\n")

    metrics = summarize_shadow_signals(signals).to_dict()

    assert metrics["signals"] == 3
    assert metrics["actionable"] == 2
    assert metrics["outcomes"] == 2
    assert metrics["wins"] == 1
    assert metrics["losses"] == 1
    assert metrics["win_rate"] == 0.5
    assert metrics["expectancy_pct"] == 0.15
    assert metrics["profit_factor"] == 2.5
    assert metrics["by_strategy"]["alpha"]["total_pnl_pct"] == 0.3


def test_shadow_metrics_empty_file_is_safe(tmp_path):
    metrics = summarize_shadow_signals(tmp_path / "missing.jsonl").to_dict()

    assert metrics["signals"] == 0
    assert metrics["profit_factor"] == 0.0

