import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from engine.position_dedup_guard import PositionDedupGuard


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
