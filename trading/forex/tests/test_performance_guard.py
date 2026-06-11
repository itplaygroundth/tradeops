import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from engine.performance_guard import PerformanceGuard


def closed(symbol, agent, pnl, ts):
    return {
        "symbol": symbol,
        "agent": agent,
        "lifecycle_status": "CLOSED",
        "net_pnl": pnl,
        "exit_time_utc": f"2026-06-02T00:{ts:02d}:00Z",
    }


def test_performance_guard_pauses_symbol_and_agent_on_recent_loss_streak(monkeypatch):
    guard = PerformanceGuard(symbol_loss_limit=3, agent_loss_limit=2, cooldown_seconds=3600)
    rows = [
        closed("XAUUSDm", "FX-XAU-011", -10, 1),
        closed("XAUUSDm", "FX-XAU-011", -11, 2),
        closed("XAUUSDm", "FX-XAU-019", -12, 3),
    ]
    monkeypatch.setattr(guard, "_load_journal", lambda: rows)

    decision = guard.evaluate("XAUUSDm", "FX-XAU-011", now=1780359000)

    assert decision.allowed is False
    assert "XAUUSDm loss streak" in decision.reason
    summary = guard.summary()
    assert summary["paused_symbols"]["XAUUSDm"]["loss_streak"] == 3
    assert summary["paused_agents"]["FX-XAU-011"]["loss_streak"] == 2


def test_performance_guard_allows_after_win_breaks_streak(monkeypatch):
    guard = PerformanceGuard(symbol_loss_limit=3, agent_loss_limit=2, cooldown_seconds=3600)
    rows = [
        closed("XAUUSDm", "FX-XAU-011", -10, 1),
        closed("XAUUSDm", "FX-XAU-011", -11, 2),
        closed("XAUUSDm", "FX-XAU-011", 5, 3),
    ]
    monkeypatch.setattr(guard, "_load_journal", lambda: rows)

    decision = guard.evaluate("XAUUSDm", "FX-XAU-011", now=1780359000)

    assert decision.allowed is True
    assert guard.summary()["paused_symbols"] == {}


def test_performance_guard_blocks_symbol_with_bad_expectancy(monkeypatch):
    import engine.performance_guard as perf_mod

    monkeypatch.setattr(perf_mod, "EXPECTANCY_SYMBOL_GUARD_ENABLED", True)
    monkeypatch.setattr(perf_mod, "EXPECTANCY_SYMBOL_MIN_TRADES", 3)
    monkeypatch.setattr(perf_mod, "EXPECTANCY_SYMBOL_BLOCK_THRESHOLD", -0.25)
    monkeypatch.setattr(perf_mod, "MANUAL_PAUSED_SYMBOLS", set())

    guard = PerformanceGuard(symbol_loss_limit=10, agent_loss_limit=10, cooldown_seconds=3600)
    rows = [
        closed("AUDUSDm", "FX-AUD-001", -2, 1),
        closed("AUDUSDm", "FX-AUD-001", -1, 2),
        closed("AUDUSDm", "FX-AUD-002", 0.25, 3),
    ]
    monkeypatch.setattr(guard, "_load_journal", lambda: rows)

    decision = guard.evaluate("AUDUSDm", "FX-AUD-001", now=1780359000)

    assert decision.allowed is False
    assert "expectancy" in decision.reason
    assert guard.summary()["expectancy_blocked_symbols"]["AUDUSDm"]["trades"] == 3


def test_manual_paused_symbol_blocks_entries(monkeypatch):
    import engine.performance_guard as perf_mod

    monkeypatch.setattr(perf_mod, "MANUAL_PAUSED_SYMBOLS", {"AUDUSDm"})

    guard = PerformanceGuard(symbol_loss_limit=10, agent_loss_limit=10, cooldown_seconds=3600)
    monkeypatch.setattr(guard, "_load_journal", lambda: [])

    decision = guard.evaluate("AUDUSDm", "FX-AUD-001", now=1780359000)

    assert decision.allowed is False
    assert "manually paused" in decision.reason
    assert guard.evaluate("NZDUSDm", "FX-NZD-001", now=1780359000).allowed is True
    assert guard.summary()["manual_paused_symbols"] == ["AUDUSDm"]


def test_expectancy_block_expires_after_cooldown(monkeypatch):
    """Bad expectancy must not be a permanent ban: once the cooldown since the
    last trade elapses, the symbol is allowed a probation trade so its
    expectancy can refresh. Otherwise blocked symbols can never recover."""
    import engine.performance_guard as perf_mod

    monkeypatch.setattr(perf_mod, "EXPECTANCY_SYMBOL_GUARD_ENABLED", True)
    monkeypatch.setattr(perf_mod, "EXPECTANCY_SYMBOL_MIN_TRADES", 3)
    monkeypatch.setattr(perf_mod, "EXPECTANCY_SYMBOL_BLOCK_THRESHOLD", -0.25)
    monkeypatch.setattr(perf_mod, "EXPECTANCY_SYMBOL_COOLDOWN_SECONDS", 3600)
    monkeypatch.setattr(perf_mod, "MANUAL_PAUSED_SYMBOLS", set())

    guard = PerformanceGuard(symbol_loss_limit=10, agent_loss_limit=10, cooldown_seconds=3600)
    # last trade at 2026-06-02T00:03:00Z -> ts 1780358580
    rows = [
        closed("AUDUSDm", "FX-AUD-001", -2, 1),
        closed("AUDUSDm", "FX-AUD-001", -1, 2),
        closed("AUDUSDm", "FX-AUD-002", 0.25, 3),
    ]
    monkeypatch.setattr(guard, "_load_journal", lambda: rows)

    last_ts = 1780358580
    # within cooldown -> still blocked
    assert guard.evaluate("AUDUSDm", "FX-AUD-001", now=last_ts + 60).allowed is False
    # past cooldown -> probation allowed
    decision = guard.evaluate("AUDUSDm", "FX-AUD-001", now=last_ts + 3601)
    assert decision.allowed is True
    assert guard.summary()["expectancy_blocked_symbols"] == {}
