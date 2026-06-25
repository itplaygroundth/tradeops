import pytest

from exchange.base import Tick
from exchange.binance import BinanceFeed
from exchange.bybit import BybitFeed
from exchange.router import ExchangeRouter


def test_defaults():
    r = ExchangeRouter()
    assert r.exchange_name == "binance"
    assert r.paper_mode is True
    assert isinstance(r.active_feed, BinanceFeed)


def test_init_bybit():
    r = ExchangeRouter(exchange="bybit", paper_mode=False)
    assert r.exchange_name == "bybit"
    assert r.paper_mode is False
    assert isinstance(r.active_feed, BybitFeed)


@pytest.mark.asyncio
async def test_set_mode_rebuilds_feed_on_correct_network():
    r = ExchangeRouter(paper_mode=True)
    await r.set_mode("live")
    assert r.paper_mode is False
    assert r.active_feed.paper_mode is False
    assert r.network == "production"
    await r.set_mode("demo")
    assert r.paper_mode is False
    assert r.network == "testnet"
    await r.set_mode("paper")
    assert r.paper_mode is True
    assert r.active_feed.paper_mode is True


@pytest.mark.asyncio
async def test_switch_exchange():
    r = ExchangeRouter(exchange="binance", paper_mode=True)
    await r.switch_exchange("bybit")
    assert r.exchange_name == "bybit"
    assert isinstance(r.active_feed, BybitFeed)
    # mode preserved across switch
    assert r.active_feed.paper_mode is True
    await r.switch_exchange("binance")
    assert isinstance(r.active_feed, BinanceFeed)


@pytest.mark.asyncio
async def test_switch_exchange_invalid():
    r = ExchangeRouter()
    with pytest.raises(ValueError):
        await r.switch_exchange("kraken")


@pytest.mark.asyncio
async def test_paper_place_order_returns_sim():
    r = ExchangeRouter(exchange="binance", paper_mode=True)
    res = await r.place_order("BTCUSDT", "buy", 0.01)
    assert res["paper"] is True
    assert res["status"] == "filled"
    assert res["symbol"] == "BTCUSDT"
    assert res["side"] == "buy"
    assert res["qty"] == 0.01
    assert isinstance(res["ticket"], int)


def test_tick_callback_forwarded_to_feed():
    r = ExchangeRouter()
    received = []
    r.set_tick_callback(lambda *a: received.append(a))
    # feed should now hold the same callback
    r.active_feed._tick_cb("BTCUSDT", 1.0, 2.0, 3.0)
    assert received == [("BTCUSDT", 1.0, 2.0, 3.0)]


def test_tick_callback_survives_switch():
    import asyncio
    r = ExchangeRouter()
    received = []
    r.set_tick_callback(lambda *a: received.append(a))
    asyncio.run(r.switch_exchange("bybit"))
    r.active_feed._tick_cb("ETHUSDT", 1.0, 2.0, 3.0)
    assert received == [("ETHUSDT", 1.0, 2.0, 3.0)]


@pytest.mark.asyncio
async def test_get_ohlcv_delegates():
    r = ExchangeRouter(exchange="binance")
    candles = await r.get_ohlcv("BTCUSDT", timeframe="M15", count=3)
    assert len(candles) == 3
    assert isinstance(candles[0]["time"], int)


@pytest.mark.asyncio
async def test_get_price_delegates():
    r = ExchangeRouter(exchange="binance")
    tick = await r.get_price("BTCUSDT")
    assert isinstance(tick, Tick)
    assert tick.symbol == "BTCUSDT"
