import asyncio
import json
import socket
import threading
import time
import urllib.request

import pytest

import run as runmod
from exchange.router import ExchangeRouter


class MockManager:
    """Stand-in for CryptoAgentManager so run.py server can be tested."""
    def __init__(self, router):
        self.router = router
        self._account_balance = 10000.0
        self._account_equity = 10500.0
        self._pairs = ["BTCUSDT", "ETHUSDT"]

    @property
    def pairs(self):
        return self._pairs

    def add_pair(self, symbol):
        symbol = symbol.upper()
        if symbol not in self._pairs:
            self._pairs.append(symbol)

    def remove_pair(self, symbol):
        symbol = symbol.upper()
        if symbol in self._pairs:
            self._pairs.remove(symbol)

    def to_state_dict(self):
        return {"summary": {}, "agents": [], "prices": {}, "order_history": []}

    def get_open_positions(self):
        return []

    async def on_tick(self, symbol, price, volume, timestamp):
        return None


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _get(url):
    req = urllib.request.urlopen(url, timeout=5)
    body = req.read().decode()
    cors = req.headers.get("Access-Control-Allow-Origin")
    return req.status, json.loads(body), cors


def _send(url, method, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    resp = urllib.request.urlopen(req, timeout=5)
    return resp.status, json.loads(resp.read().decode())


@pytest.fixture
def server(tmp_path):
    port = _free_port()
    router = ExchangeRouter(exchange="binance", paper_mode=True)
    manager = MockManager(router)

    loop = asyncio.new_event_loop()
    ready = threading.Event()
    httpd_holder = {}

    def run_loop():
        asyncio.set_event_loop(loop)
        httpd = runmod.build_server("127.0.0.1", port, router, manager,
                                    str(tmp_path), loop)
        httpd_holder["httpd"] = httpd
        ready.set()
        loop.run_forever()

    t = threading.Thread(target=run_loop, daemon=True)
    t.start()
    ready.wait(5)
    st = threading.Thread(target=httpd_holder["httpd"].serve_forever, daemon=True)
    st.start()
    time.sleep(0.2)
    base = f"http://127.0.0.1:{port}"
    yield base, router, manager
    httpd_holder["httpd"].shutdown()
    loop.call_soon_threadsafe(loop.stop)


def test_api_mode_get(server):
    base, router, manager = server
    status, body, cors = _get(f"{base}/api/mode")
    assert status == 200
    assert body["mode"] == "paper"
    assert "balance" in body["account"]
    assert body["account"]["balance"] == 10000.0
    assert cors == "*"


def test_api_mode_post(server):
    base, router, manager = server
    status, body = _send(f"{base}/api/mode", "POST", {"mode": "live"})
    assert status == 200
    assert body["mode"] == "live"
    assert router.paper_mode is False


def test_api_exchange_get_and_post(server):
    base, router, manager = server
    status, body, cors = _get(f"{base}/api/exchange")
    assert status == 200
    assert body["exchange"] == "binance"
    status, body = _send(f"{base}/api/exchange", "POST", {"exchange": "bybit"})
    assert status == 200
    assert body["exchange"] == "bybit"
    assert router.exchange_name == "bybit"


def test_api_pairs_crud(server):
    base, router, manager = server
    status, body, _ = _get(f"{base}/api/pairs")
    assert "BTCUSDT" in body["pairs"]
    _send(f"{base}/api/pairs", "POST", {"symbol": "SOLUSDT"})
    assert "SOLUSDT" in manager.pairs
    _send(f"{base}/api/pairs", "DELETE", {"symbol": "SOLUSDT"})
    assert "SOLUSDT" not in manager.pairs


def test_api_account(server):
    base, router, manager = server
    status, body, cors = _get(f"{base}/api/account")
    assert status == 200
    assert body["balance"] == 10000.0
    assert body["equity"] == 10500.0
    assert cors == "*"


def test_api_positions(server):
    base, router, manager = server
    status, body, _ = _get(f"{base}/api/positions")
    assert status == 200
    assert body["positions"] == []


def test_live_state_json(server):
    base, router, manager = server
    status, body, cors = _get(f"{base}/live_state.json")
    assert status == 200
    assert set(body.keys()) == {"summary", "agents", "prices", "order_history"}
    assert cors == "*"


def test_api_ohlcv(server):
    base, router, manager = server
    status, body, cors = _get(f"{base}/api/ohlcv/BTCUSDT?timeframe=M15&count=3")
    assert status == 200
    assert len(body) == 3
    assert set(body[0].keys()) >= {"time", "open", "high", "low", "close", "volume"}
    assert cors == "*"
