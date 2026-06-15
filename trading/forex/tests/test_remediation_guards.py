import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from engine.strategy_performance_guard import StrategyPerformanceGuard
from engine.regime_entry_filter import RegimeEntryFilter, RegimeFilterDecision


def test_strategy_performance_guard_blocks_on_zero_expectancy():
    """Strategy with expectancy <= 0 should be blocked after min_trades."""
    guard = StrategyPerformanceGuard(
        enabled=True,
        min_trades=3,
        loss_streak=5,
        min_expectancy=0.0,  # tightened from -0.10
        cooldown_seconds=3600,
        history_limit=50,
    )

    # 3 losing trades -> expectancy = -1.0 (below 0.0)
    guard.record("momentum", -10.0)
    guard.record("momentum", -5.0)
    guard.record("momentum", -8.0)

    decision = guard.evaluate("momentum")
    assert decision.allowed is False
    assert "expectancy" in decision.reason
    assert decision.cooldown_remaining_seconds > 0


def test_strategy_performance_guard_allows_positive_expectancy():
    """Strategy with expectancy > 0 should be allowed."""
    guard = StrategyPerformanceGuard(
        enabled=True,
        min_trades=3,
        loss_streak=5,
        min_expectancy=0.0,
        cooldown_seconds=3600,
        history_limit=50,
    )

    # 2 wins, 1 loss -> net positive expectancy
    guard.record("momentum", 10.0)
    guard.record("momentum", 5.0)
    guard.record("momentum", -8.0)

    decision = guard.evaluate("momentum")
    assert decision.allowed is True


def test_strategy_performance_guard_loss_streak_threshold():
    """Loss streak of 2 should block (tightened from 3)."""
    guard = StrategyPerformanceGuard(
        enabled=True,
        min_trades=10,
        loss_streak=2,  # tightened from 3
        min_expectancy=0.0,
        cooldown_seconds=3600,
        history_limit=50,
    )

    guard.record("grid_scalp", -5.0)
    guard.record("grid_scalp", -3.0)

    decision = guard.evaluate("grid_scalp")
    assert decision.allowed is False
    assert "loss streak" in decision.reason


def test_strategy_performance_guard_loss_streak_broken_by_win():
    """A win should reset the loss streak."""
    guard = StrategyPerformanceGuard(
        enabled=True,
        min_trades=10,
        loss_streak=2,
        min_expectancy=0.0,
        cooldown_seconds=3600,
        history_limit=50,
    )

    guard.record("mean_reversion", -5.0)
    guard.record("mean_reversion", 2.0)  # win breaks streak
    guard.record("mean_reversion", -3.0)  # only 1 in a row now

    decision = guard.evaluate("mean_reversion")
    assert decision.allowed is True


def test_regime_entry_filter_blocks_xauusd_in_trending():
    """XAUUSDm should be blocked in TRENDING_UP/DOWN regimes."""
    filter = RegimeEntryFilter(enabled=True)

    # TRENDING_UP
    decision = filter.evaluate("XAUUSDm", "TRENDING_UP")
    assert decision.allowed is False
    assert "TRENDING_UP" in decision.reason

    # TRENDING_DOWN
    decision = filter.evaluate("XAUUSDm", "TRENDING_DOWN")
    assert decision.allowed is False
    assert "TRENDING_DOWN" in decision.reason

    # RANGING should be allowed
    decision = filter.evaluate("XAUUSDm", "RANGING")
    assert decision.allowed is True


def test_regime_entry_filter_allows_other_symbols():
    """Other symbols should not be blocked by default."""
    filter = RegimeEntryFilter(enabled=True)

    decision = filter.evaluate("EURUSDm", "TRENDING_UP")
    assert decision.allowed is True

    decision = filter.evaluate("GBPUSDm", "TRENDING_DOWN")
    assert decision.allowed is True


def test_regime_entry_filter_disabled_allows_all():
    """Disabled filter should allow all entries."""
    filter = RegimeEntryFilter(enabled=False)

    decision = filter.evaluate("XAUUSDm", "TRENDING_UP")
    assert decision.allowed is True


def test_regime_entry_filter_case_insensitive():
    """Symbol and regime matching should be case-insensitive."""
    filter = RegimeEntryFilter(enabled=True)

    decision = filter.evaluate("xauusdm", "trending_up")
    assert decision.allowed is False

    decision = filter.evaluate("XauUsDm", "TrEnDiNg_DoWn")
    assert decision.allowed is False


def test_regime_entry_filter_custom_blocked():
    """Custom blocked pairs should work."""
    filter = RegimeEntryFilter(
        enabled=True,
        blocked={"EURUSDm": ["RANGING"]},
    )

    decision = filter.evaluate("EURUSDm", "RANGING")
    assert decision.allowed is False

    decision = filter.evaluate("EURUSDm", "TRENDING_UP")
    assert decision.allowed is True


def test_regime_entry_filter_summary():
    """Summary should reflect configuration."""
    filter = RegimeEntryFilter(enabled=True, blocked={"XAUUSDm": ["TRENDING_UP"]})
    summary = filter.summary()

    assert summary["enabled"] is True
    assert "XAUUSDM" in summary["blocked_pairs"]
    assert "TRENDING_UP" in summary["blocked_pairs"]["XAUUSDM"]


def test_strategy_performance_guard_summary_format():
    """Summary should include all strategy stats."""
    guard = StrategyPerformanceGuard(
        enabled=True,
        min_trades=3,
        loss_streak=2,
        min_expectancy=0.0,
        cooldown_seconds=3600,
        history_limit=50,
    )

    guard.record("momentum", -5.0)
    guard.record("momentum", -3.0)

    summary = guard.summary()
    assert summary["enabled"] is True
    assert "momentum" in summary["strategies"]
    strat = summary["strategies"]["momentum"]
    assert strat["trades"] == 2
    assert strat["losses"] == 2
    assert strat["expectancy"] < 0
    assert strat["allowed"] is False


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
