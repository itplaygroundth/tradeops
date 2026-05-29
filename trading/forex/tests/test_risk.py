import pytest
import sys
from pathlib import Path

# Add src to python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from engine.risk_guardian import ForexRiskGuardian
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
