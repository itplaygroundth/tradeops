import pytest
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

# Add src to python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from engine.signals import ForexSignalEngine, is_good_session
import engine.signals as signals_mod
from engine.forex_macro import ForexMacroSignal, get_us_eastern_time

def test_technical_signal():
    signal_engine = ForexSignalEngine()
    
    # Mock is_good_session to return True for EURUSD during testing
    # otherwise it might fail if run in a closed session
    old_is_good = signals_mod.is_good_session
    signals_mod.is_good_session = lambda sym: True

    try:
        # Feed 50 bars of EURUSD-like data
        base = 1.0850
        for i in range(50):
            price = base + (i % 10 - 5) * 0.0001
            signal_engine.record_tick("EURUSD", price, volume=1000, timestamp=time.time() + i)
        
        signal = signal_engine.technical_signal("EURUSD")
        assert signal["action"] in ("LONG", "SHORT", "HOLD")
        assert 0 <= signal["confidence"] <= 100
        assert "reason" in signal
    finally:
        signals_mod.is_good_session = old_is_good

def test_session_filter():
    # NZDUSD is only good in ASIA. If the test is run during London/NY time, it should return HOLD.
    # We can test is_good_session directly by mocking datetime.
    from unittest.mock import patch
    
    # Mock datetime to Asia hour (e.g. 4:00 UTC)
    mock_asia = datetime(2026, 5, 28, 4, 0, tzinfo=timezone.utc)
    with patch('engine.signals.datetime') as mock_date:
        mock_date.now.return_value = mock_asia
        assert is_good_session("NZDUSD") is True
        assert is_good_session("USDCAD") is False  # USDCAD is only NY (13-21 UTC)

    # Mock datetime to London hour (e.g. 10:00 UTC)
    mock_london = datetime(2026, 5, 28, 10, 0, tzinfo=timezone.utc)
    with patch('engine.signals.datetime') as mock_date:
        mock_date.now.return_value = mock_london
        assert is_good_session("NZDUSD") is False
        assert is_good_session("EURUSD") is True

    # Mock datetime to Overlap hour (e.g. 14:00 UTC)
    mock_overlap = datetime(2026, 5, 28, 14, 0, tzinfo=timezone.utc)
    with patch('engine.signals.datetime') as mock_date:
        mock_date.now.return_value = mock_overlap
        assert is_good_session("USDCAD") is True  # Overlap includes NY
        assert is_good_session("EURUSD") is True
        assert is_good_session("NZDUSD") is False

def test_dst_aware_eastern_time():
    # In June (DST active), UTC is 4 hours ahead of ET.
    dt_june_utc = datetime(2026, 6, 1, 12, 30, tzinfo=timezone.utc)
    dt_june_est = get_us_eastern_time(dt_june_utc)
    assert dt_june_est.hour == 8
    assert dt_june_est.minute == 30
    
    # In December (Standard time), UTC is 5 hours ahead of ET.
    dt_dec_utc = datetime(2026, 12, 1, 13, 30, tzinfo=timezone.utc)
    dt_dec_est = get_us_eastern_time(dt_dec_utc)
    assert dt_dec_est.hour == 8
    assert dt_dec_est.minute == 30

def test_macro_avoid_trading():
    macro = ForexMacroSignal()
    
    # 8:30 AM Eastern Time in June (DST) -> 12:30 UTC. First Friday is June 5, 2026.
    mock_nfp_time = datetime(2026, 6, 5, 12, 30, tzinfo=timezone.utc)
    avoid, reason = macro.should_avoid_trading("EURUSD", now_utc=mock_nfp_time)
    assert avoid is True
    assert "NFP" in reason

    # Outside the NFP window (e.g. 9:00 AM Eastern Time) -> 13:00 UTC
    mock_normal_time = datetime(2026, 6, 5, 13, 0, tzinfo=timezone.utc)
    avoid, reason = macro.should_avoid_trading("EURUSD", now_utc=mock_normal_time)
    assert avoid is False


def _seed_prices(engine, symbol, prices):
    base = time.time()
    for i, price in enumerate(prices):
        engine.record_tick(symbol, price, volume=1000, timestamp=base + i)


def test_mean_reversion_long_short_and_trend_block():
    long_engine = ForexSignalEngine()
    _seed_prices(long_engine, "EURUSDm", [1.1000] * 35 + [1.0998,1.0995,1.0992,1.0989,1.0986,1.0983,1.0980,1.0977,1.0974,1.0971,1.0968,1.0965,1.0962,1.0959,1.0962,1.0964,1.0965,1.0966,1.0967,1.0968])
    long_sig = long_engine.mean_reversion_signal("EURUSDm", regime="RANGING")
    assert long_sig["action"] == "LONG"

    short_engine = ForexSignalEngine()
    _seed_prices(short_engine, "EURUSDm", [1.1000] * 35 + [1.1002,1.1005,1.1008,1.1011,1.1014,1.1017,1.1020,1.1023,1.1026,1.1029,1.1032,1.1035,1.1038,1.1041,1.1038,1.1036,1.1035,1.1034,1.1033,1.1032])
    short_sig = short_engine.mean_reversion_signal("EURUSDm", regime="RANGING")
    assert short_sig["action"] == "SHORT"

    trend_engine = ForexSignalEngine()
    _seed_prices(trend_engine, "EURUSDm", [1.1000 + i * 0.0005 for i in range(70)])
    trend_sig = trend_engine.mean_reversion_signal("EURUSDm", regime="TREND_UP")
    assert trend_sig["action"] == "HOLD"
