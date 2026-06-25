"""Tests for CryptoRiskGuardian — USDT %-based risk, not pips."""
import pytest

from engine.risk_guardian import (
    CryptoRiskGuardian, RiskResult,
    MAX_RISK_PCT, MAX_CONCURRENT_POSITIONS, DAILY_DRAWDOWN_LIMIT,
    DAILY_PROFIT_TARGET_USDT, DAILY_REALIZED_LOSS_LIMIT_USDT,
)


def test_mads_caution_policy_scales_crypto_risk_and_exposure():
    guardian = CryptoRiskGuardian()
    guardian.set_external_policy("CAUTION", 0.5, 1)
    result = guardian.validate(
        symbol="BTCUSDT", action="BUY", entry_price=50000.0,
        sl_pct=0.02, tp_pct=0.04,
        account_balance=1000.0, account_equity=1000.0, current_day=1,
    )
    assert result.allowed
    assert result.notional == pytest.approx(25.0)
    assert result.risk_amount == pytest.approx(0.5)


def test_mads_hard_stop_blocks_crypto_entries():
    guardian = CryptoRiskGuardian()
    guardian.set_external_policy("HARD_STOP", 0, 0)
    result = guardian.validate(
        symbol="BTCUSDT", action="BUY", entry_price=50000.0,
        sl_pct=0.02, tp_pct=0.04,
        account_balance=1000.0, account_equity=1000.0, current_day=1,
    )
    assert not result.allowed
    assert "MADS defensive policy HARD_STOP" in result.reason


def test_position_sizing_math():
    rg = CryptoRiskGuardian()
    res = rg.validate(
        symbol="BTCUSDT", action="BUY", entry_price=50000.0,
        sl_pct=0.02, tp_pct=0.04,
        account_balance=1000.0, account_equity=1000.0, current_day=1,
    )
    assert res.allowed
    # risk_amount = 1000 * 0.01 = 10 USDT
    assert res.risk_amount == pytest.approx(1.0)
    # The 5% notional cap limits a 1,000 USDT account to 50 USDT exposure.
    assert res.qty == pytest.approx(0.001, rel=1e-6)
    assert res.notional == pytest.approx(50.0, rel=1e-6)
    # SL/TP prices
    assert res.sl_price == pytest.approx(50000.0 * (1 - 0.02))
    assert res.tp_price == pytest.approx(50000.0 * (1 + 0.04))


def test_sell_sl_tp_prices_inverted():
    rg = CryptoRiskGuardian()
    res = rg.validate(
        symbol="ETHUSDT", action="SELL", entry_price=2000.0,
        sl_pct=0.02, tp_pct=0.05,
        account_balance=1000.0, account_equity=1000.0, current_day=1,
    )
    assert res.allowed
    assert res.sl_price == pytest.approx(2000.0 * (1 + 0.02))
    assert res.tp_price == pytest.approx(2000.0 * (1 - 0.05))


def test_max_concurrent_block():
    rg = CryptoRiskGuardian()
    for _ in range(MAX_CONCURRENT_POSITIONS):
        rg.on_position_opened("BTCUSDT")
    res = rg.validate(
        symbol="BTCUSDT", action="BUY", entry_price=50000.0,
        sl_pct=0.02, tp_pct=0.04,
        account_balance=1000.0, account_equity=1000.0, current_day=1,
    )
    assert not res.allowed
    assert "position" in res.reason.lower()


def test_max_concurrent_is_per_pair():
    """The cap is per-pair: filling BTCUSDT must not block ETHUSDT."""
    rg = CryptoRiskGuardian()
    for _ in range(MAX_CONCURRENT_POSITIONS):
        rg.on_position_opened("BTCUSDT")
    # BTCUSDT is full -> blocked
    btc = rg.validate("BTCUSDT", "BUY", 50000.0, 0.02, 0.04, 1000.0, 1000.0, current_day=1)
    assert not btc.allowed
    # ETHUSDT is empty -> allowed
    eth = rg.validate("ETHUSDT", "BUY", 2000.0, 0.02, 0.04, 1000.0, 1000.0, current_day=1)
    assert eth.allowed


def test_position_close_decrements_correct_pair():
    rg = CryptoRiskGuardian()
    for _ in range(MAX_CONCURRENT_POSITIONS):
        rg.on_position_opened("BTCUSDT")
    rg.on_position_closed("BTCUSDT", 0.0)
    # one slot freed on BTCUSDT
    res = rg.validate("BTCUSDT", "BUY", 50000.0, 0.02, 0.04, 1000.0, 1000.0, current_day=1)
    assert res.allowed


def test_daily_drawdown_block():
    rg = CryptoRiskGuardian()
    # equity below balance*(1-limit) => blocked
    eq = 1000.0 * (1 - DAILY_DRAWDOWN_LIMIT) - 1
    res = rg.validate(
        symbol="BTCUSDT", action="BUY", entry_price=50000.0,
        sl_pct=0.02, tp_pct=0.04,
        account_balance=1000.0, account_equity=eq, current_day=1,
    )
    assert not res.allowed
    assert "drawdown" in res.reason.lower()
    # stays paused even after equity recovers (circuit breaker)
    res2 = rg.validate(
        symbol="BTCUSDT", action="BUY", entry_price=50000.0,
        sl_pct=0.02, tp_pct=0.04,
        account_balance=1000.0, account_equity=1000.0, current_day=1,
    )
    assert not res2.allowed


def test_daily_reset_clears_pause():
    rg = CryptoRiskGuardian()
    eq = 1000.0 * (1 - DAILY_DRAWDOWN_LIMIT) - 1
    rg.validate("BTCUSDT", "BUY", 50000.0, 0.02, 0.04, 1000.0, eq, current_day=1)
    # new day resets the breaker
    res = rg.validate("BTCUSDT", "BUY", 50000.0, 0.02, 0.04, 1000.0, 1000.0, current_day=2)
    assert res.allowed


def test_daily_realized_loss_breaker():
    """Accumulated realized losses >= DAILY_DRAWDOWN_LIMIT of the day-start
    balance must halt new entries. Production wiring sets equity == balance,
    so the equity check never fires; only the realized-loss breaker can catch
    a day that bled out through closed losing trades."""
    rg = CryptoRiskGuardian()
    # first validate of the day snapshots the day-start balance (1000)
    first = rg.validate("BTCUSDT", "BUY", 50000.0, 0.02, 0.04, 1000.0, 1000.0, current_day=1)
    assert first.allowed
    # realized losses close totalling 55 USDT >= 5% of 1000 (=50)
    rg.on_position_closed("BTCUSDT", -30.0)
    rg.on_position_closed("BTCUSDT", -25.0)
    # equity reported == balance (the production case) -> equity check is inert
    res = rg.validate("BTCUSDT", "BUY", 50000.0, 0.02, 0.04, 945.0, 945.0, current_day=1)
    assert not res.allowed
    assert "loss" in res.reason.lower()
    # stays paused for the rest of the day (circuit breaker)
    res2 = rg.validate("BTCUSDT", "BUY", 50000.0, 0.02, 0.04, 945.0, 945.0, current_day=1)
    assert not res2.allowed
    # new day clears it
    res3 = rg.validate("BTCUSDT", "BUY", 50000.0, 0.02, 0.04, 945.0, 945.0, current_day=2)
    assert res3.allowed


def test_daily_profit_target_blocks_new_entries_until_next_day():
    rg = CryptoRiskGuardian()
    first = rg.validate("BTCUSDT", "BUY", 50000.0, 0.02, 0.04, 1000.0, 1000.0, current_day=1)
    assert first.allowed

    rg.on_position_closed("BTCUSDT", DAILY_PROFIT_TARGET_USDT - 1)
    still_open = rg.validate("ETHUSDT", "BUY", 2000.0, 0.02, 0.04, 1019.0, 1019.0, current_day=1)
    assert still_open.allowed

    rg.on_position_closed("ETHUSDT", 1.0)
    res = rg.validate("SOLUSDT", "BUY", 100.0, 0.02, 0.04, 1020.0, 1020.0, current_day=1)
    assert not res.allowed
    assert "profit target" in res.reason.lower()

    next_day = rg.validate("SOLUSDT", "BUY", 100.0, 0.02, 0.04, 1020.0, 1020.0, current_day=2)
    assert next_day.allowed


def test_daily_fixed_realized_loss_limit_blocks_entries():
    rg = CryptoRiskGuardian()
    first = rg.validate("BTCUSDT", "BUY", 50000.0, 0.02, 0.04, 1000.0, 1000.0, current_day=1)
    assert first.allowed

    rg.on_position_closed("BTCUSDT", -DAILY_REALIZED_LOSS_LIMIT_USDT)
    res = rg.validate("ETHUSDT", "BUY", 2000.0, 0.02, 0.04, 980.0, 980.0, current_day=1)

    assert not res.allowed
    assert "$20.00" in res.reason


def test_invalid_sl_blocked():
    rg = CryptoRiskGuardian()
    res = rg.validate("BTCUSDT", "BUY", 50000.0, 0.0, 0.04, 1000.0, 1000.0, current_day=1)
    assert not res.allowed


def test_auto_tp_when_zero():
    rg = CryptoRiskGuardian()
    res = rg.validate("BTCUSDT", "BUY", 100.0, 0.02, 0.0, 1000.0, 1000.0, current_day=1)
    assert res.allowed
    # auto TP = sl * MIN_RR (1.3) => 0.026
    assert res.tp_price == pytest.approx(100.0 * 1.026)
