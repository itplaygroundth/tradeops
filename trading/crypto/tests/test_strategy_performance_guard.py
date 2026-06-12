from engine.strategy_performance_guard import StrategyPerformanceGuard


def test_blocks_after_loss_streak_during_cooldown():
    guard = StrategyPerformanceGuard(
        enabled=True,
        min_trades=3,
        loss_streak=2,
        min_expectancy=-10,
        cooldown_seconds=60,
    )
    guard.record("grid_scalp", -1.0, now=100)
    guard.record("grid_scalp", -2.0, now=110)

    decision = guard.evaluate("grid_scalp", now=120)

    assert decision.allowed is False
    assert "loss streak" in decision.reason
    assert decision.cooldown_remaining_seconds == 50


def test_allows_after_cooldown_expires():
    guard = StrategyPerformanceGuard(
        enabled=True,
        min_trades=3,
        loss_streak=2,
        min_expectancy=-10,
        cooldown_seconds=60,
    )
    guard.record("grid_scalp", -1.0, now=100)
    guard.record("grid_scalp", -2.0, now=110)

    assert guard.evaluate("grid_scalp", now=171).allowed is True


def test_blocks_negative_expectancy_after_min_trades():
    guard = StrategyPerformanceGuard(
        enabled=True,
        min_trades=3,
        loss_streak=5,
        min_expectancy=-0.1,
        cooldown_seconds=60,
    )
    guard.record("momentum", 1.0, now=100)
    guard.record("momentum", -2.0, now=110)
    guard.record("momentum", -1.0, now=120)

    decision = guard.evaluate("momentum", now=130)

    assert decision.allowed is False
    assert "expectancy" in decision.reason


def test_summary_reports_strategy_state():
    guard = StrategyPerformanceGuard(enabled=True, cooldown_seconds=60)
    guard.record("momentum", -1.5, now=100)

    summary = guard.summary(now=110)

    assert summary["enabled"] is True
    assert summary["guard_mode"] == "NORMAL"
    assert summary["strategies"]["momentum"]["trades"] == 1
    assert summary["strategies"]["momentum"]["total_pnl"] == -1.5


def test_default_block_is_four_hour_scale():
    guard = StrategyPerformanceGuard()
    assert guard.loss_streak == 3
    assert guard.cooldown_seconds == 14400


def test_two_losses_are_caution_not_blocked_by_default():
    guard = StrategyPerformanceGuard(enabled=True, min_trades=3, min_expectancy=-10, cooldown_seconds=60)
    guard.record("market_structure", -1.0, now=100)
    guard.record("market_structure", -1.0, now=110)

    assert guard.guard_mode(now=120) == "CAUTION"
    assert guard.evaluate("market_structure", now=120).allowed is True


def test_three_losses_enter_defense_and_block_strategy():
    guard = StrategyPerformanceGuard(enabled=True, min_trades=3, min_expectancy=-10, cooldown_seconds=60)
    guard.record("market_structure", -1.0, now=100)
    guard.record("market_structure", -1.0, now=110)
    guard.record("market_structure", -1.0, now=120)

    assert guard.guard_mode(now=130) == "DEFENSE"
    assert guard.evaluate("market_structure", now=130).allowed is False
