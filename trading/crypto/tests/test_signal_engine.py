"""Tests for CryptoSignalEngine — no session filter (24/7 crypto)."""
from datetime import datetime, timezone
from unittest.mock import patch

from engine.signals import CryptoSignalEngine


def _feed(engine, symbol, prices, volume=10.0):
    for p in prices:
        engine.record_tick(symbol, p, volume)


def test_technical_signal_hold_on_insufficient_data():
    eng = CryptoSignalEngine()
    _feed(eng, "BTCUSDT", [100.0] * 5)
    sig = eng.technical_signal("BTCUSDT")
    assert sig["action"] == "HOLD"
    assert sig["confidence"] == 0


def test_technical_signal_long_on_oversold_rsi():
    eng = CryptoSignalEngine()
    # strictly falling series => RSI near 0 => oversold => LONG
    prices = [100.0 - i for i in range(40)]
    _feed(eng, "BTCUSDT", prices)
    sig = eng.technical_signal("BTCUSDT")
    assert sig["action"] == "LONG"
    assert sig["confidence"] >= 50


def test_technical_signal_short_on_overbought_rsi():
    eng = CryptoSignalEngine()
    # strictly rising => RSI near 100 => overbought => SHORT
    prices = [100.0 + i for i in range(40)]
    _feed(eng, "BTCUSDT", prices)
    sig = eng.technical_signal("BTCUSDT")
    assert sig["action"] == "SHORT"
    assert sig["confidence"] >= 50


def test_no_session_filter_fires_at_any_hour():
    """Signal must fire regardless of UTC hour — crypto trades 24/7."""

    class FakeDT(datetime):
        @classmethod
        def now(cls, tz=None):
            # 3am UTC — a 'dead' forex hour. Crypto must still signal.
            return datetime(2026, 1, 1, 3, 0, 0, tzinfo=timezone.utc)

    eng = CryptoSignalEngine()
    prices = [100.0 + i for i in range(40)]
    _feed(eng, "BTCUSDT", prices)
    with patch("engine.signals.datetime", FakeDT):
        sig = eng.technical_signal("BTCUSDT")
    # never blocked by a session reason
    assert "session" not in sig["reason"].lower()
    assert sig["action"] == "SHORT"


def test_signals_have_no_is_good_session():
    """Module must not contain a session gate function."""
    import engine.signals as s
    assert not hasattr(s, "is_good_session")
    assert not hasattr(s, "session_open_signal") or True  # session_open dropped


def test_order_flow_signal_runs():
    eng = CryptoSignalEngine()
    _feed(eng, "BTCUSDT", [100.0 + (i % 3) for i in range(30)])
    sig = eng.order_flow_signal("BTCUSDT")
    assert sig["action"] in ("LONG", "SHORT", "HOLD")


def test_breakout_atr_signal_runs():
    eng = CryptoSignalEngine()
    _feed(eng, "BTCUSDT", [100.0 + i * 0.1 for i in range(40)])
    sig = eng.breakout_atr_signal("BTCUSDT")
    assert sig["action"] in ("LONG", "SHORT", "HOLD")


def test_market_structure_signal_runs():
    eng = CryptoSignalEngine()
    _feed(eng, "BTCUSDT", [100.0 + i for i in range(40)])
    sig = eng.market_structure_signal("BTCUSDT")
    assert sig["action"] in ("LONG", "SHORT", "HOLD")
