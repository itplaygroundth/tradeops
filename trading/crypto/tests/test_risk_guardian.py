"""Tests for CryptoRiskGuardian — USDT %-based risk, not pips."""
import pytest

from engine.risk_guardian import (
    CryptoRiskGuardian, RiskResult,
    MAX_RISK_PCT, MAX_CONCURRENT_POSITIONS, DAILY_DRAWDOWN_LIMIT,
)


def test_position_sizing_math():
    rg = CryptoRiskGuardian()
    res = rg.validate(
        symbol="BTCUSDT", action="BUY", entry_price=50000.0,
        sl_pct=0.02, tp_pct=0.04,
        account_balance=1000.0, account_equity=1000.0, current_day=1,
    )
    assert res.allowed
    # risk_amount = 1000 * 0.01 = 10 USDT
    assert res.risk_amount == pytest.approx(10.0)
    # notional = risk_amount / sl_pct = 10 / 0.02 = 500 USDT
    # qty = notional / price = 500 / 50000 = 0.01
    assert res.qty == pytest.approx(0.01, rel=1e-6)
    assert res.notional == pytest.approx(500.0, rel=1e-6)
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
        rg.on_position_opened()
    res = rg.validate(
        symbol="BTCUSDT", action="BUY", entry_price=50000.0,
        sl_pct=0.02, tp_pct=0.04,
        account_balance=1000.0, account_equity=1000.0, current_day=1,
    )
    assert not res.allowed
    assert "position" in res.reason.lower()


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


def test_invalid_sl_blocked():
    rg = CryptoRiskGuardian()
    res = rg.validate("BTCUSDT", "BUY", 50000.0, 0.0, 0.04, 1000.0, 1000.0, current_day=1)
    assert not res.allowed


def test_auto_tp_when_zero():
    rg = CryptoRiskGuardian()
    res = rg.validate("BTCUSDT", "BUY", 100.0, 0.02, 0.0, 1000.0, 1000.0, current_day=1)
    assert res.allowed
    # auto TP = sl * MIN_RR (2.0) => 0.04
    assert res.tp_price == pytest.approx(100.0 * 1.04)
