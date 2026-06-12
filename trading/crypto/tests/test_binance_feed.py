import pytest

from exchange.base import Tick
from exchange.binance import BinanceFeed, _TF_MAP, normalize_timeframe


def test_name():
    assert BinanceFeed().name == "binance"


def test_timeframe_map():
    assert _TF_MAP["M1"] == "1m"
    assert _TF_MAP["M5"] == "5m"
    assert _TF_MAP["M15"] == "15m"
    assert _TF_MAP["M30"] == "30m"
    assert _TF_MAP["H1"] == "1h"
    assert _TF_MAP["H4"] == "4h"
    assert _TF_MAP["D1"] == "1d"


def test_timeframe_aliases_from_ui():
    assert normalize_timeframe("1m") == "M1"
    assert normalize_timeframe("5m") == "M5"
    assert normalize_timeframe("15m") == "M15"
    assert normalize_timeframe("1h") == "H1"
    assert normalize_timeframe("4h") == "H4"
    assert normalize_timeframe("1d") == "D1"
    assert normalize_timeframe("h1") == "H1"


@pytest.mark.asyncio
async def test_get_ohlcv_real():
    feed = BinanceFeed()
    candles = await feed.get_ohlcv("BTCUSDT", timeframe="M15", count=5)
    assert isinstance(candles, list)
    assert len(candles) == 5
    c = candles[0]
    assert {"time", "open", "high", "low", "close", "volume"}.issubset(c.keys())
    assert isinstance(c["time"], int)
    # unix SECONDS not ms — sanity range (year ~2020+ and < year ~2100)
    assert 1_500_000_000 < c["time"] < 4_000_000_000
    assert c["high"] >= c["low"]
    assert isinstance(c["open"], float)
    # ascending time order
    assert candles[1]["time"] > candles[0]["time"]


@pytest.mark.asyncio
async def test_get_price_real():
    feed = BinanceFeed()
    tick = await feed.get_price("BTCUSDT")
    assert isinstance(tick, Tick)
    assert tick.symbol == "BTCUSDT"
    assert tick.ask >= tick.bid > 0
    assert tick.bid <= tick.mid <= tick.ask


@pytest.mark.asyncio
async def test_paper_place_order_no_network():
    # BinanceFeed in paper mode must not hit the exchange
    feed = BinanceFeed(paper_mode=True)
    res = await feed.place_order("BTCUSDT", "buy", 0.01)
    assert res["paper"] is True
    assert res["status"] == "filled"
    assert res["symbol"] == "BTCUSDT"
    assert res["side"] == "buy"
    assert res["qty"] == 0.01
    assert isinstance(res["ticket"], int)
