import hashlib
import hmac
from urllib.parse import urlencode

import pytest

from exchange.base import Tick
from exchange.binance import BinanceFeed, NETWORKS, _TF_MAP, normalize_timeframe


def test_name():
    assert BinanceFeed().name == "binance"


def test_demo_and_live_use_isolated_networks_and_credentials(monkeypatch):
    monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "test-key")
    monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "test-secret")
    monkeypatch.setenv("BINANCE_LIVE_API_KEY", "live-key")
    monkeypatch.setenv("BINANCE_LIVE_API_SECRET", "live-secret")

    demo = BinanceFeed(mode="demo")
    live = BinanceFeed(mode="live")

    assert demo.network == "testnet"
    assert demo._rest == "https://testnet.binance.vision"
    assert demo._api_key == "test-key"
    assert live.network == "production"
    assert live._rest == "https://api.binance.com"
    assert live._api_key == "live-key"


def test_demo_without_testnet_credentials_is_signal_only(monkeypatch):
    monkeypatch.delenv("BINANCE_TESTNET_API_KEY", raising=False)
    monkeypatch.delenv("BINANCE_TESTNET_API_SECRET", raising=False)
    feed = BinanceFeed(mode="demo")
    assert feed.supports_live_trading is False
    assert feed.credential_status == "missing"
    assert feed.supports_short is False


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


@pytest.mark.asyncio
async def test_signed_request_uses_hmac_and_network_key(monkeypatch):
    monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "test-key")
    monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "test-secret")
    feed = BinanceFeed(mode="demo")
    captured = {}

    class Response:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def json(self, content_type=None):
            return {"ok": True}

    class Session:
        closed = False

        def request(self, method, url, params=None, headers=None):
            captured.update(method=method, url=url, params=params, headers=headers)
            return Response()

    feed._session = Session()
    monkeypatch.setattr("exchange.binance.time.time", lambda: 1000.0)
    await feed._json_request("GET", "/api/v3/account", {"recvWindow": 5000}, signed=True)

    unsigned = {"recvWindow": 5000, "timestamp": 1_000_000}
    expected = hmac.new(
        b"test-secret", urlencode(unsigned).encode(), hashlib.sha256
    ).hexdigest()
    assert captured["url"].startswith(NETWORKS["demo"]["rest"])
    assert captured["headers"]["X-MBX-APIKEY"] == "test-key"
    assert captured["params"]["signature"] == expected


@pytest.mark.asyncio
async def test_quantity_is_floored_to_exchange_step(monkeypatch):
    feed = BinanceFeed()

    async def filters(symbol):
        return {"step_size": "0.00100000", "min_qty": "0.001", "min_notional": "5"}

    monkeypatch.setattr(feed, "_filters", filters)
    assert await feed.normalize_quantity("BTCUSDT", 0.01299, 1000) == "0.01200000"
