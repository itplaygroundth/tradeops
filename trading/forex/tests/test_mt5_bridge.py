import pytest
import sys
from pathlib import Path

# Add src to python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from mt5_bridge.pip_calc import calculate_lot_size, get_pip_size, get_contract_size

def test_pip_calc_usd_quote():
    # EURUSD: Quote is USD
    # balance = 1000, risk = 1% ($10), SL = 20 pips (0.0020)
    # pip_value = 0.0020 * 100,000 = $200 risk per lot
    # lot = 10 / 200 = 0.05
    lot = calculate_lot_size(
        account_balance=1000.0,
        risk_pct=0.01,
        sl_price_distance=0.0020,
        symbol="EURUSD"
    )
    assert lot == 0.05

def test_pip_calc_gold():
    # XAUUSD: Quote is USD, contract size = 100
    # balance = 1000, risk = 1% ($10), SL = 200 pips ($2.0)
    # risk per lot = 2.0 * 100 = $200 per lot
    # lot = 10 / 200 = 0.05
    lot = calculate_lot_size(
        account_balance=1000.0,
        risk_pct=0.01,
        sl_price_distance=2.0,
        symbol="XAUUSD"
    )
    assert lot == 0.05

def test_pip_calc_usd_base():
    # USDJPY: Quote is JPY, base is USD.
    # balance = 1000, risk = 1% ($10), SL = 20 pips (0.20)
    # price = 150.0
    # risk in JPY per lot = 0.20 * 100,000 = 20,000 JPY
    # converted to USD using mock get_price: 20,000 / 150.0 = $133.33 per lot
    # lot = 10 / 133.33 = 0.075 -> rounds to 0.08
    def mock_get_price(sym):
        if sym == "USDJPY":
            return 150.0
        return None

    lot = calculate_lot_size(
        account_balance=1000.0,
        risk_pct=0.01,
        sl_price_distance=0.20,
        symbol="USDJPY",
        get_price_func=mock_get_price
    )
    assert lot == 0.07

def test_pip_calc_cross_pair():
    # EURGBP: Quote is GBP.
    # balance = 1000, risk = 1% ($10), SL = 20 pips (0.0020)
    # price of GBPUSD is mock 1.25
    # risk in GBP per lot = 0.0020 * 100,000 = 200 GBP
    # converted to USD: 200 * 1.25 = $250 per lot
    # lot = 10 / 250 = 0.04
    def mock_get_price(sym):
        if sym == "GBPUSD":
            return 1.25
        return None

    lot = calculate_lot_size(
        account_balance=1000.0,
        risk_pct=0.01,
        sl_price_distance=0.0020,
        symbol="EURGBP",
        get_price_func=mock_get_price
    )
    assert lot == 0.04
