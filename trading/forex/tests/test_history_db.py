import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from storage import history_db


def test_upsert_order_dedupes_by_deal_ticket(monkeypatch, tmp_path):
    db_path = tmp_path / "history.db"
    monkeypatch.setattr(history_db, "DB_PATH", db_path)

    entry = {
        "deal_ticket": 101,
        "timestamp": 1000,
        "agent": "MTAI-FX-XAU-001",
        "symbol": "XAUUSDm",
        "action": "SELL",
        "volume": 0.01,
        "price": 4500.0,
        "type": "closed",
        "status": "closed",
        "ticket": 555,
        "pnl": -3.0,
        "comment": "[sl 4500.00000]",
        "deal_entry": 1,
        "deal_reason": 4,
        "exit_reason": "SL",
        "magic": 20260101,
    }

    assert history_db.upsert_order(entry) is True
    updated = dict(entry)
    updated["pnl"] = 4.25
    updated["exit_reason"] = "TP"
    assert history_db.upsert_order(updated) is False

    result = history_db.query_orders(limit=10)

    assert result["total"] == 1
    row = result["items"][0]
    assert row["deal_ticket"] == 101
    assert row["pnl"] == 4.25
    assert row["exit_reason"] == "TP"
