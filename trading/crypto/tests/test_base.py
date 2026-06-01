import asyncio
import inspect

import pytest

from exchange.base import Tick, ExchangeFeed


def test_tick_fields():
    t = Tick(symbol="BTCUSDT", bid=1.0, ask=2.0, mid=1.5, last=1.4, timestamp=123.0)
    assert t.symbol == "BTCUSDT"
    assert t.bid == 1.0
    assert t.ask == 2.0
    assert t.mid == 1.5
    assert t.last == 1.4
    assert t.timestamp == 123.0


def test_exchangefeed_is_abstract():
    with pytest.raises(TypeError):
        ExchangeFeed()


def test_dummy_subclass_instantiates():
    class DummyFeed(ExchangeFeed):
        async def subscribe(self, pairs):
            return None

        async def get_price(self, symbol):
            return Tick(symbol, 1, 2, 1.5, 1.4, 0.0)

        async def get_ohlcv(self, symbol, timeframe="M15", count=200):
            return []

        async def place_order(self, symbol, side, qty, sl=0, tp=0):
            return {}

        async def get_positions(self):
            return []

        async def get_recent_deals(self, hours=24, limit=200):
            return []

        @property
        def name(self):
            return "dummy"

    f = DummyFeed()
    assert f.name == "dummy"
    tick = asyncio.run(f.get_price("BTCUSDT"))
    assert tick.symbol == "BTCUSDT"


def test_interface_methods_exist():
    for m in ("subscribe", "get_price", "get_ohlcv", "place_order",
              "get_positions", "get_recent_deals"):
        assert inspect.iscoroutinefunction(getattr(ExchangeFeed, m))
