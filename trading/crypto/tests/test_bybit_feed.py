import pytest

from exchange.base import Tick
from exchange.bybit import BybitFeed, _TF_MAP, normalize_timeframe


def test_name():
    assert BybitFeed().name == "bybit"


def test_timeframe_map():
    assert _TF_MAP["M1"] == "1"
    assert _TF_MAP["M5"] == "5"
    assert _TF_MAP["M15"] == "15"
    assert _TF_MAP["M30"] == "30"
    assert _TF_MAP["H1"] == "60"
    assert _TF_MAP["H4"] == "240"
    assert _TF_MAP["D1"] == "D"


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
    feed = BybitFeed()
    candles = await feed.get_ohlcv("BTCUSDT", timeframe="M15", count=5)
    assert isinstance(candles, list)
    assert len(candles) == 5
    c = candles[0]
    assert {"time", "open", "high", "low", "close", "volume"}.issubset(c.keys())
    assert isinstance(c["time"], int)
    assert 1_500_000_000 < c["time"] < 4_000_000_000
    # Bybit returns newest-first; we reverse → ascending
    assert candles[1]["time"] > candles[0]["time"]
    assert c["high"] >= c["low"]


@pytest.mark.asyncio
async def test_get_price_real():
    feed = BybitFeed()
    tick = await feed.get_price("BTCUSDT")
    assert isinstance(tick, Tick)
    assert tick.symbol == "BTCUSDT"
    assert tick.ask >= tick.bid > 0


@pytest.mark.asyncio
async def test_paper_place_order():
    feed = BybitFeed(paper_mode=True)
    res = await feed.place_order("BTCUSDT", "sell", 0.02)
    assert res["paper"] is True
    assert res["status"] == "filled"
    assert res["side"] == "sell"
    assert res["qty"] == 0.02
