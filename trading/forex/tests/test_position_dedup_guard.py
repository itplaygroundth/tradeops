import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import storage.history_db as history_db_module
from engine.position_dedup_guard import PositionDedupGuard
from storage.history_db import init_db, insert_order, last_open_ts_by_symbol


def test_position_dedup_blocks_same_symbol_position():
    guard = PositionDedupGuard(max_per_symbol=1, max_per_symbol_side=1, cooldown_seconds=0)
    positions = [{"ticket": 1, "symbol": "XAUUSDm", "type": "SELL", "magic": 20260101}]

    decision = guard.evaluate("XAUUSDm", "SELL", positions, now=1000)

    assert decision.allowed is False
    assert "already has 1 managed position" in decision.reason


def test_position_dedup_blocks_hedge_when_disabled():
    guard = PositionDedupGuard(max_per_symbol=2, max_per_symbol_side=1, cooldown_seconds=0, allow_hedge=False)
    positions = [{"ticket": 1, "symbol": "GBPUSDm", "type": "SELL", "magic": 20260101}]

    decision = guard.evaluate("GBPUSDm", "BUY", positions, now=1000)

    assert decision.allowed is False
    assert "hedge disabled" in decision.reason


def test_position_dedup_ignores_unmanaged_positions_and_records_cooldown():
    guard = PositionDedupGuard(max_per_symbol=1, max_per_symbol_side=1, cooldown_seconds=900)
    positions = [{"ticket": 1, "symbol": "AUDUSDm", "type": "SELL", "magic": 0}]

    assert guard.evaluate("AUDUSDm", "SELL", positions, now=1000).allowed is True

    guard.record_open("AUDUSDm", now=1000)
    decision = guard.evaluate("AUDUSDm", "SELL", [], now=1300)

    assert decision.allowed is False
    assert decision.cooldown_remaining_seconds == 600


def test_dedup_db_fallback_enforces_cooldown():
    guard = PositionDedupGuard(
        max_per_symbol=1,
        max_per_symbol_side=1,
        cooldown_seconds=900,
        db_lookup=lambda: {"EURUSDm": 1000.0 - 100},
    )
    decision = guard.evaluate("EURUSDm", "BUY", [], now=1000.0)
    assert decision.allowed is False
    assert "cooldown" in decision.reason
    assert decision.cooldown_remaining_seconds == 800


def test_dedup_db_fallback_expired_allows():
    guard = PositionDedupGuard(
        max_per_symbol=1,
        max_per_symbol_side=1,
        cooldown_seconds=900,
        db_lookup=lambda: {"EURUSDm": 1000.0 - 1000},
    )
    decision = guard.evaluate("EURUSDm", "BUY", [], now=1000.0)
    assert decision.allowed is True


def test_dedup_inmemory_takes_max_with_db():
    guard = PositionDedupGuard(
        max_per_symbol=1,
        max_per_symbol_side=1,
        cooldown_seconds=900,
        db_lookup=lambda: {"EURUSDm": 100.0},
    )
    guard.record_open("EURUSDm", now=1000.0)
    decision = guard.evaluate("EURUSDm", "BUY", [], now=1300.0)
    assert decision.allowed is False
    assert decision.cooldown_remaining_seconds == 600


def test_dedup_no_db_lookup_unchanged():
    guard = PositionDedupGuard(max_per_symbol=1, max_per_symbol_side=1, cooldown_seconds=900)
    decision = guard.evaluate("EURUSDm", "BUY", [], now=1000.0)
    assert decision.allowed is True


def test_dedup_db_lookup_cached_within_ttl():
    calls = {"n": 0}
    def lookup():
        calls["n"] += 1
        return {"EURUSDm": 100.0}
    guard = PositionDedupGuard(
        max_per_symbol=1, max_per_symbol_side=1, cooldown_seconds=900,
        db_lookup=lookup, db_cache_ttl=10.0,
    )
    guard.evaluate("EURUSDm", "BUY", [], now=1000.0)
    guard.evaluate("XAUUSDm", "BUY", [], now=1005.0)  # within TTL -> cached
    assert calls["n"] == 1
    guard.evaluate("EURUSDm", "BUY", [], now=1011.0)  # past TTL -> refresh
    assert calls["n"] == 2


def test_last_open_ts_by_symbol_reads_live_entry(tmp_path, monkeypatch):
    monkeypatch.setattr(history_db_module, "DB_PATH", tmp_path / "history.db")
    init_db()
    ts = 1748812345.0
    insert_order({
        "timestamp": ts,
        "symbol": "EURUSDm",
        "action": "BUY",
        "type": "live",
        "status": "placed",
        "agent": "test_agent",
        "volume": 0.01,
        "price": 1.1000,
        "sl": 0.0,
        "tp": 0.0,
        "deal_ticket": 99991,
    })
    result = last_open_ts_by_symbol()
    assert result["EURUSDm"] == ts
