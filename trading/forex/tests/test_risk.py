import pytest
import sys
from pathlib import Path

# Add src to python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from engine.risk_guardian import ForexRiskGuardian, AccountRiskMonitor
from engine.dynamic_risk import get_risk_params

def test_risk_guardian_allow():
    guardian = ForexRiskGuardian()
    
    # Normal trade: 15 pips SL, 35 pips TP, R:R is 2.33 (> 2.0). 1% of 1000 balance = $10 risk.
    # EURUSD pip size = 0.0001. 15 pips distance = 0.0015.
    # risk per lot = 0.0015 * 100,000 = $150 per lot.
    # lot = 10 / 150 = 0.066 -> rounds to 0.07.
    res = guardian.validate(
        symbol="EURUSD",
        action="BUY",
        entry_price=1.0850,
        sl_pips=15,
        tp_pips=35,
        account_balance=1000.0,
        account_equity=1000.0,
        current_day=28,
    )
    assert res.allowed is True
    assert res.lot_size == 0.07
    assert round(res.sl_price, 4) == 1.0835
    assert round(res.tp_price, 4) == 1.0885


def test_risk_guardian_allows_when_cent_account_margin_buffer_is_enough():
    guardian = ForexRiskGuardian()

    res = guardian.validate(
        symbol="EURUSD",
        action="BUY",
        entry_price=1.0850,
        sl_pips=15,
        tp_pips=35,
        account_balance=1000.0,
        account_equity=1000.0,
        current_day=28,
        account_currency="USC",
        account_margin_free=1000.0,
        account_leverage=2000,
    )

    assert res.allowed is True
    assert res.lot_size == 0.01


def test_risk_guardian_caps_lot_to_remaining_daily_profit_target():
    guardian = ForexRiskGuardian()

    res = guardian.validate(
        symbol="EURUSD",
        action="BUY",
        entry_price=1.0850,
        sl_pips=15,
        tp_pips=35,
        account_balance=1000.0,
        account_equity=1000.0,
        current_day=28,
        target_profit_remaining=20.0,
    )

    assert res.allowed is True
    # Risk lot would be 0.07, but $20 / (35 pips * $10 per pip per lot)
    # is ~0.057 lots, rounded to 0.06.
    assert res.lot_size == 0.06
    assert res.risk_amount == pytest.approx(9.0)


def test_risk_guardian_target_lot_does_not_exceed_risk_lot():
    guardian = ForexRiskGuardian()

    res = guardian.validate(
        symbol="EURUSD",
        action="BUY",
        entry_price=1.0850,
        sl_pips=15,
        tp_pips=35,
        account_balance=1000.0,
        account_equity=1000.0,
        current_day=28,
        target_profit_remaining=1000.0,
    )

    assert res.allowed is True
    assert res.lot_size == 0.07


def test_risk_guardian_applies_adaptive_lot_multiplier():
    guardian = ForexRiskGuardian()

    res = guardian.validate(
        symbol="EURUSD",
        action="BUY",
        entry_price=1.0850,
        sl_pips=15,
        tp_pips=35,
        account_balance=1000.0,
        account_equity=1000.0,
        current_day=28,
        risk_multiplier=0.5,
    )

    assert res.allowed is True
    assert res.lot_size == 0.04


def test_risk_guardian_blocks_when_adaptive_multiplier_zero():
    guardian = ForexRiskGuardian()

    res = guardian.validate(
        symbol="EURUSD",
        action="BUY",
        entry_price=1.0850,
        sl_pips=15,
        tp_pips=35,
        account_balance=1000.0,
        account_equity=1000.0,
        current_day=28,
        risk_multiplier=0.0,
    )

    assert res.allowed is False
    assert "adaptive guard" in res.reason.lower()


def test_risk_guardian_rejects_when_required_margin_exceeds_buffer():
    guardian = ForexRiskGuardian()

    res = guardian.validate(
        symbol="EURUSD",
        action="BUY",
        entry_price=1.0850,
        sl_pips=15,
        tp_pips=35,
        account_balance=1000.0,
        account_equity=1000.0,
        current_day=28,
        account_margin_free=100.0,
        account_leverage=20,
    )

    assert res.allowed is False
    assert "margin" in res.reason.lower()


def test_risk_guardian_reject_rr():
    guardian = ForexRiskGuardian()
    
    # R:R too low (TP = 15, SL = 15 -> R:R = 1.0 < 2.0)
    res = guardian.validate(
        symbol="EURUSD",
        action="BUY",
        entry_price=1.0850,
        sl_pips=15,
        tp_pips=15,
        account_balance=1000.0,
        account_equity=1000.0,
        current_day=28,
    )
    assert res.allowed is False
    assert "R:R" in res.reason

def test_risk_guardian_reject_drawdown():
    guardian = ForexRiskGuardian()
    
    # Equity = 940 (6% loss, threshold is 5% loss)
    res = guardian.validate(
        symbol="EURUSD",
        action="BUY",
        entry_price=1.0850,
        sl_pips=15,
        tp_pips=35,
        account_balance=1000.0,
        account_equity=940.0,
        current_day=28,
    )
    assert res.allowed is False
    assert "drawdown" in res.reason.lower()

def test_risk_guardian_max_positions():
    guardian = ForexRiskGuardian()
    
    # Open 3 positions
    guardian.on_position_opened()
    guardian.on_position_opened()
    guardian.on_position_opened()
    
    # 4th position should be rejected
    res = guardian.validate(
        symbol="EURUSD",
        action="BUY",
        entry_price=1.0850,
        sl_pips=15,
        tp_pips=35,
        account_balance=1000.0,
        account_equity=1000.0,
        current_day=28,
    )
    assert res.allowed is False
    assert "positions open" in res.reason

def test_dynamic_risk():
    # EURUSD default: sl=15, tp=30, risk=0.01
    # TRENDING mult: sl=0.9, tp=1.3, risk=1.2
    # expected: sl = 15*0.9 = 13.5 -> round to 14, tp = 30*1.3 = 39, risk = 0.01 * 1.2 = 0.012
    p = get_risk_params("EURUSD", "TRENDING")
    assert p.sl_pips == 14
    assert p.tp_pips == 39
    assert p.risk_pct == pytest.approx(0.012)
    
    # SIDEWAYS mult: sl=1.1, tp=0.8, risk=0.7
    # expected: sl = 15*1.1 = 16.5 -> round to 16 (round-to-even) or 17. Python round(16.5) is 16.
    p = get_risk_params("EURUSD", "SIDEWAYS")
    assert p.sl_pips in (16, 17)
    assert p.tp_pips == 24
    assert p.risk_pct == pytest.approx(0.007)


def test_account_risk_monitor_pauses_and_persists(tmp_path):
    state_file = tmp_path / "risk_state.json"
    monitor = AccountRiskMonitor(state_file=state_file, managed_magic=20260101)

    state = monitor.evaluate(
        {"balance": 1000.0, "equity": 1000.0, "margin": 0.0},
        [{"ticket": 1, "magic": 20260101, "profit": 0.0}],
        current_day=28,
        now=100.0,
    )
    assert state.mode == "ACTIVE"
    assert state.open_positions == 1

    state = monitor.evaluate(
        {"balance": 1000.0, "equity": 948.0, "margin": 10.0},
        [{"ticket": 1, "magic": 20260101, "profit": -52.0}, {"ticket": 2, "magic": 0, "profit": -10.0}],
        current_day=28,
        now=120.0,
    )
    assert state.mode == "PAUSED"
    assert state.blocks_entries is True
    assert state.open_positions == 1
    assert state.floating_pnl == -52.0

    reloaded = AccountRiskMonitor(state_file=state_file, managed_magic=20260101)
    assert reloaded._state["mode"] == "PAUSED"


def test_account_risk_monitor_hard_stop_requires_reset(tmp_path):
    monitor = AccountRiskMonitor(state_file=tmp_path / "risk_state.json", managed_magic=20260101)
    monitor.evaluate({"balance": 1000.0, "equity": 1000.0, "margin": 0.0}, [], current_day=28, now=100.0)

    state = monitor.evaluate({"balance": 1000.0, "equity": 920.0, "margin": 0.0}, [], current_day=28, now=140.0)
    assert state.mode == "HARD_STOP"
    assert state.requires_hard_stop is True

    next_day = monitor.evaluate({"balance": 1000.0, "equity": 1000.0, "margin": 0.0}, [], current_day=29, now=200.0)
    assert next_day.mode == "HARD_STOP"

    monitor.reset(equity=1000.0, current_day=29)
    assert monitor.current.mode == "ACTIVE"
