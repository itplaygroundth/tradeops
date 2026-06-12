import csv
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from storage.trading_journal import (
    INSTITUTIONAL_JOURNAL_FIELDS,
    build_institutional_journal,
    journal_to_csv,
    journal_to_json,
)


def test_institutional_journal_pairs_lifecycle_rows():
    rows = [
        {
            "timestamp": 1000,
            "agent": "Agent-1",
            "symbol": "GBPUSDm",
            "action": "SELL",
            "volume": 0.02,
            "price": 1.34639,
            "sl": 1.3488,
            "tp": 1.3406,
            "type": "live",
            "status": "placed",
            "ticket": 2016903870,
            "pnl": 0,
            "comment": "MTAI-Agent-1",
        },
        {
            "timestamp": 1300,
            "agent": "Agent-1",
            "symbol": "GBPUSDm",
            "action": "SELL",
            "volume": 0.02,
            "price": 1.34339,
            "sl": 0,
            "tp": 0,
            "type": "closed",
            "status": "closed",
            "ticket": 2016903870,
            "pnl": 6.0,
            "comment": "MTAI-close",
        },
    ]

    journal = build_institutional_journal(rows, account={"login": 123, "currency": "USD"})

    assert len(journal) == 1
    trade = journal[0]
    assert list(trade.keys()) == INSTITUTIONAL_JOURNAL_FIELDS
    assert trade["trade_id"] == "MT5-2016903870"
    assert trade["account_login"] == 123
    assert trade["asset_class"] == "FX"
    assert trade["side"] == "SELL"
    assert trade["lifecycle_status"] == "CLOSED"
    assert trade["entry_time_utc"] == "1970-01-01T00:16:40Z"
    assert trade["exit_time_utc"] == "1970-01-01T00:21:40Z"
    assert trade["holding_seconds"] == 300
    assert trade["initial_risk_price"] == 0.00241
    assert trade["net_pnl"] == 6.0
    assert trade["r_multiple"] > 1.0


def test_journal_csv_and_json_exports_are_stable():
    rows = build_institutional_journal([
        {
            "timestamp": 1000,
            "agent": "GoldBot",
            "symbol": "XAUUSDm",
            "action": "BUY",
            "volume": 0.01,
            "price": 4491.3,
            "sl": 4479.5,
            "tp": 4522.1,
            "type": "live",
            "status": "placed",
            "ticket": 77,
            "pnl": 0,
        }
    ])

    csv_text = journal_to_csv(rows)
    parsed = list(csv.DictReader(io.StringIO(csv_text)))
    assert parsed[0]["trade_id"] == "MT5-77"
    assert parsed[0]["asset_class"] == "METAL"
    assert parsed[0]["lifecycle_status"] == "PLACED"
    assert parsed[0]["contract_size"] == "100"

    payload = json.loads(journal_to_json(rows))
    assert payload["standard"] == "institutional_trade_journal_v1"
    assert payload["rows"][0]["symbol"] == "XAUUSDm"


def test_journal_uses_mt5_deal_entry_codes_for_exit_rows():
    rows = [
        {
            "timestamp": 1000,
            "agent": "XauAgent",
            "symbol": "XAUUSDm",
            "action": "BUY",
            "volume": 0.01,
            "price": 4500.0,
            "sl": 4488.0,
            "tp": 4524.0,
            "type": "live",
            "status": "placed",
            "ticket": 99,
            "pnl": 0,
            "deal_entry": 0,
        },
        {
            "timestamp": 1060,
            "agent": "XauAgent",
            "symbol": "XAUUSDm",
            "action": "BUY",
            "volume": 0.01,
            "price": 4488.0,
            "type": "live",
            "status": "placed",
            "ticket": 99,
            "pnl": -12.0,
            "deal_entry": 1,
            "deal_reason": 4,
            "comment": "[sl 4488.00000]",
        },
    ]

    journal = build_institutional_journal(rows)

    assert journal[0]["lifecycle_status"] == "CLOSED"
    assert journal[0]["net_pnl"] == -12.0
    assert journal[0]["exit_reason"] == "SL"
    assert journal[0]["exit_price"] == 4488.0
