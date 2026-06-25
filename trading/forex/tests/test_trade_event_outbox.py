import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from storage.trade_event_outbox import TradeEventOutbox


def test_emit_persists_trade_closed_event(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(TradeEventOutbox, "_run", lambda self: None)
    outbox = TradeEventOutbox("crypto-ai", tmp_path / "events.db")
    event_id = outbox.emit("trade.closed", {"symbol": "BTCUSDT", "pnl": 2.5})

    row = outbox._next()
    assert row[0] == event_id
    payload = json.loads(row[1])
    assert payload["event_type"] == "trade.closed"
    assert payload["engine_id"] == "crypto-ai"
    assert payload["trade"]["pnl"] == 2.5


def test_retry_is_persistent(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(TradeEventOutbox, "_run", lambda self: None)
    outbox = TradeEventOutbox("mtai", tmp_path / "events.db")
    event_id = outbox.emit("trade.closed", {"symbol": "XAUUSD"})
    outbox._mark_retry(event_id, 0, "offline")

    assert outbox.status()["pending"] == 1
