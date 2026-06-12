import sys
from pathlib import Path
import time
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from engine.signals import ForexSignalEngine, is_good_session
import engine.signals as signals_mod


def test_new_signals_basic():
    se = ForexSignalEngine()
    # feed simple history
    base = 1.2000
    for i in range(40):
        price = base + ((i % 5) - 2) * 0.0002
        se.record_tick("EURUSD", price, volume=1000, timestamp=time.time() + i)

    of = se.order_flow_signal("EURUSD")
    ba = se.breakout_atr_signal("EURUSD")
    ms = se.market_structure_signal("EURUSD")

    assert isinstance(of, dict) and "action" in of and "confidence" in of
    assert isinstance(ba, dict) and "action" in ba and "confidence" in ba
    assert isinstance(ms, dict) and "action" in ms and "confidence" in ms


def test_session_open_signal_time_based(monkeypatch):
    se = ForexSignalEngine()
    # feed short history
    base = 0.7000
    for i in range(10):
        se.record_tick("AUDUSD", base + i * 0.0001, volume=500, timestamp=time.time() + i)

    # mock UTC time to 07:10 (London open)
    mock_dt = datetime(2026, 5, 28, 7, 10, tzinfo=timezone.utc)
    monkeypatch.setattr(signals_mod, "datetime", type("D", (), {"now": staticmethod(lambda tz=None: mock_dt), "timezone": timezone}))

    s = se.session_open_signal("AUDUSD")
    assert isinstance(s, dict) and "action" in s and "confidence" in s
