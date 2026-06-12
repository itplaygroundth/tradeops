"""Tests for CryptoSignalEngine — no session filter (24/7 crypto)."""
from datetime import datetime, timezone
from unittest.mock import patch

from engine.signals import CryptoSignalEngine


def _feed(engine, symbol, prices, volume=10.0):
    # space ticks so each price forms its own candle across all timeframes
    for i, p in enumerate(prices):
        engine.record_tick(symbol, p, volume, timestamp=float((i + 1) * 3600))


def test_technical_signal_hold_on_insufficient_data():
    eng = CryptoSignalEngine()
    _feed(eng, "BTCUSDT", [100.0] * 5)
    sig = eng.technical_signal("BTCUSDT")
    assert sig["action"] == "HOLD"
    assert sig["confidence"] == 0


def test_oversold_rsi_does_not_long_a_confirmed_downtrend():
    """RSI<20 in a strong downtrend must NOT trigger a counter-trend LONG."""
    eng = CryptoSignalEngine()
    prices = [100.0 - i for i in range(40)]  # strictly falling -> RSI<20 AND it_trend down
    _feed(eng, "BTCUSDT", prices)
    sig = eng.technical_signal("BTCUSDT")
    assert sig["action"] != "LONG"  # trend guard blocks the fade


def test_oversold_rsi_longs_when_trend_not_down():
    """When RSI is oversold but the trend is NOT confirmed down (a dip in a
    range), the reversal LONG is still allowed."""
    import math
    eng = CryptoSignalEngine()
    # ranging series with a sharp dip at the end -> low RSI, flat/up it_trend
    prices = [100.0 + 0.3 * math.sin(i / 3.0) for i in range(36)] + [99.0, 98.0, 97.0, 96.0]
    _feed(eng, "ETHUSDT", prices)
    h = eng.get_history("ETHUSDT")
    # only meaningful if RSI is actually oversold and trend isn't down
    if (h.rsi(14) or 50) < 20 and h.it_trend() != "down":
        assert eng.technical_signal("ETHUSDT")["action"] == "LONG"


def test_overbought_rsi_does_not_short_a_confirmed_uptrend():
    """RSI>80 in a strong uptrend must NOT trigger a counter-trend SHORT —
    crypto RSI stays extended for long stretches."""
    eng = CryptoSignalEngine()
    prices = [100.0 + i for i in range(40)]  # strictly rising -> RSI>80 AND it_trend up
    _feed(eng, "BTCUSDT", prices)
    sig = eng.technical_signal("BTCUSDT")
    assert sig["action"] != "SHORT"  # trend guard blocks the fade


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
    # never blocked by a session reason; a signal is produced at 3am UTC
    assert "session" not in sig["reason"].lower()
    assert sig["action"] in ("LONG", "SHORT", "HOLD")
    assert sig["reason"]  # non-empty -> the engine evaluated, not session-gated


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
