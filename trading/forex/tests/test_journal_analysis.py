import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from storage.journal_analysis import analyze_journal


def test_analyze_journal_reports_expectancy_and_recommendations():
    rows = [
        {"lifecycle_status": "closed", "symbol": "EURUSDm", "agent": "A", "exit_reason": "TP", "net_pnl": 3.0},
        {"lifecycle_status": "closed", "symbol": "EURUSDm", "agent": "A", "exit_reason": "TP", "net_pnl": 2.0},
        {"lifecycle_status": "closed", "symbol": "EURUSDm", "agent": "A", "exit_reason": "SL", "net_pnl": -1.0},
        {"lifecycle_status": "closed", "symbol": "GBPUSDm", "agent": "B", "exit_reason": "SL", "net_pnl": -1.0},
        {"lifecycle_status": "closed", "symbol": "GBPUSDm", "agent": "B", "exit_reason": "SL", "net_pnl": -2.0},
        {"lifecycle_status": "closed", "symbol": "GBPUSDm", "agent": "B", "exit_reason": "SL", "net_pnl": -3.0},
    ]

    result = analyze_journal(rows, min_trades=3)

    assert result["total"]["trades"] == 6
    assert result["total"]["net_pnl"] == -2.0
    assert result["by_symbol"]["EURUSDm"]["expectancy"] > 0
    assert result["by_symbol"]["GBPUSDm"]["expectancy"] < 0
    assert any("reduce_or_block GBPUSDm" in item for item in result["recommendations"])
    assert any("prefer EURUSDm" in item for item in result["recommendations"])


def test_analyze_journal_collects_more_data_when_buckets_are_small():
    result = analyze_journal([
        {"lifecycle_status": "closed", "symbol": "EURUSDm", "net_pnl": -1.0},
    ], min_trades=3)

    assert result["recommendations"] == [
        "collect_more_data: no bucket has at least 3 decisive trades with clear edge"
    ]
