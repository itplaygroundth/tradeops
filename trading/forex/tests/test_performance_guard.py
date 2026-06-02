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
