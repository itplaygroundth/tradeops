import sys
import calendar
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from engine.weekend_reopen_guard import WeekendReopenGuard


def utc_ts(year, month, day, hour, minute=0):
    return calendar.timegm((year, month, day, hour, minute, 0, 0, 0, 0))


def test_weekend_reopen_guard_blocks_after_long_quiet_window(tmp_path):
    guard = WeekendReopenGuard(state_file=tmp_path / "guard.json", gap_seconds=3600, block_seconds=900)
    guard.evaluate_symbol("XAUUSDm", bid=4310.0, ask=4310.3, positions=[], now=1000)

    decision = guard.evaluate_symbol(
        "XAUUSDm",
        bid=4328.0,
        ask=4329.0,
        positions=[{"ticket": 1, "symbol": "XAUUSDm", "type": "SELL", "price_open": 4317.0}],
        now=1000 + 7200,
    )

    assert decision.status == "guarded"
    assert decision.block_entries_until == 1000 + 7200 + 900
    assert decision.adverse_gap == 12.0
    blocked, reason = guard.blocks_entries("XAUUSDm", now=1000 + 7201)
    assert blocked is True
    assert "weekend reopen guard" in reason


def test_weekend_reopen_guard_does_not_auto_close_by_default(tmp_path):
    guard = WeekendReopenGuard(
        state_file=tmp_path / "guard.json",
        gap_seconds=10,
        block_seconds=900,
        auto_close=False,
    )
    guard.evaluate_symbol("XAUUSDm", bid=4310.0, ask=4310.3, positions=[], now=100)

    decision = guard.evaluate_symbol(
        "XAUUSDm",
        bid=4330.0,
        ask=4331.0,
        positions=[{"ticket": 55, "symbol": "XAUUSDm", "type": "SELL", "price_open": 4317.0}],
        now=200,
    )

    assert decision.close_tickets == []


def test_weekend_reopen_guard_can_auto_close_when_enabled(tmp_path):
    guard = WeekendReopenGuard(
        state_file=tmp_path / "guard.json",
        gap_seconds=10,
        block_seconds=900,
        auto_close=True,
    )
    guard.evaluate_symbol("XAUUSDm", bid=4310.0, ask=4310.3, positions=[], now=100)

    decision = guard.evaluate_symbol(
        "XAUUSDm",
        bid=4330.0,
        ask=4331.0,
        positions=[{"ticket": 55, "symbol": "XAUUSDm", "type": "SELL", "price_open": 4317.0}],
        now=200,
    )

    assert decision.close_tickets == [55]


def test_weekend_reopen_guard_blocks_wide_spread_without_quiet_window(tmp_path):
    guard = WeekendReopenGuard(state_file=tmp_path / "guard.json", gap_seconds=3600, block_seconds=900)
    decision = guard.evaluate_symbol("EURUSDm", bid=1.1, ask=1.101, positions=[], now=100)

    assert decision.status == "guarded"
    assert "spread" in decision.reason


def test_weekend_reopen_guard_uses_market_timestamp_for_quiet_window(tmp_path):
    guard = WeekendReopenGuard(state_file=tmp_path / "guard.json", gap_seconds=3600, block_seconds=900)
    guard.evaluate_symbol("XAUUSDm", bid=4310.0, ask=4310.3, positions=[], now=100, market_ts=1000)

    decision = guard.evaluate_symbol(
        "XAUUSDm",
        bid=4312.0,
        ask=4312.3,
        positions=[],
        now=110,
        market_ts=1000 + 7200,
    )

    assert decision.status == "guarded"
    assert decision.age_seconds == 7200


def test_pre_weekend_close_returns_managed_tickets_and_blocks_entries(tmp_path):
    guard = WeekendReopenGuard(
        state_file=tmp_path / "guard.json",
        pre_close_weekday_utc=4,
        pre_close_after_utc="18:00",
        pre_close_reopen_weekday_utc=0,
        pre_close_reopen_after_utc="01:00",
    )
    now = utc_ts(2026, 6, 12, 18, 30)  # Friday after cutoff

    decision = guard.evaluate_pre_close(
        positions=[
            {"ticket": 101, "symbol": "GBPUSDm"},
            {"ticket": 102, "symbol": "XAUUSDm"},
        ],
        now=now,
    )

    assert decision.status == "closing"
    assert decision.close_tickets == [101, 102]
    assert decision.block_entries_until == utc_ts(2026, 6, 15, 1, 0)
    blocked, reason = guard.blocks_entries("GBPUSDm", now=now + 60)
    assert blocked is True
    assert "pre-weekend close guard" in reason


def test_pre_weekend_close_blocks_entries_even_when_flat(tmp_path):
    guard = WeekendReopenGuard(
        state_file=tmp_path / "guard.json",
        pre_close_weekday_utc=4,
        pre_close_after_utc="18:00",
        pre_close_reopen_weekday_utc=0,
        pre_close_reopen_after_utc="01:00",
    )
    now = utc_ts(2026, 6, 12, 18, 30)

    decision = guard.evaluate_pre_close(positions=[], now=now)

    assert decision.status == "blocking"
    assert decision.close_tickets == []
    blocked, _ = guard.blocks_entries("EURUSDm", now=now + 60)
    assert blocked is True


def test_pre_weekend_close_noop_before_cutoff(tmp_path):
    guard = WeekendReopenGuard(
        state_file=tmp_path / "guard.json",
        pre_close_weekday_utc=4,
        pre_close_after_utc="18:00",
    )

    decision = guard.evaluate_pre_close(
        positions=[{"ticket": 101, "symbol": "GBPUSDm"}],
        now=utc_ts(2026, 6, 12, 17, 59),
    )

    assert decision.status == "ok"
    assert decision.close_tickets == []
