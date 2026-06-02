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
