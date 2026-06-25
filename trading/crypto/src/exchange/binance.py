"""Binance Spot feed with isolated paper, testnet demo, and production modes."""
import asyncio
from decimal import Decimal, ROUND_DOWN
import hashlib
import hmac
import os
import random
import time
from urllib.parse import urlencode

import aiohttp

from exchange.base import ExchangeFeed, Tick

NETWORKS = {
    "demo": {
        "rest": "https://testnet.binance.vision",
        "ws": "wss://stream.testnet.binance.vision/stream",
        "key_env": "BINANCE_TESTNET_API_KEY",
        "secret_env": "BINANCE_TESTNET_API_SECRET",
        "network": "testnet",
    },
    "live": {
        "rest": "https://api.binance.com",
        "ws": "wss://stream.binance.com:9443/stream",
        "key_env": "BINANCE_LIVE_API_KEY",
        "secret_env": "BINANCE_LIVE_API_SECRET",
        "network": "production",
    },
    "paper": {
        "rest": "https://api.binance.com",
        "ws": "wss://stream.binance.com:9443/stream",
        "key_env": "",
        "secret_env": "",
        "network": "paper",
    },
}

_TF_MAP = {
    "M1": "1m", "M5": "5m", "M15": "15m", "M30": "30m",
    "H1": "1h", "H4": "4h", "D1": "1d",
}
_TF_ALIASES = {
    "1m": "M1", "5m": "M5", "15m": "M15", "30m": "M30",
    "1h": "H1", "4h": "H4", "1d": "D1",
}


def normalize_timeframe(timeframe: str) -> str:
    raw = str(timeframe or "M15").strip()
    return _TF_ALIASES.get(raw.lower(), raw.upper())


class BinanceFeed(ExchangeFeed):
    def __init__(self, paper_mode: bool = True, mode: str = None):
        self.mode = mode or ("paper" if paper_mode else "live")
        if self.mode not in NETWORKS:
            raise ValueError(f"Unsupported Binance mode: {self.mode}")
        self.paper_mode = self.mode == "paper"
        cfg = NETWORKS[self.mode]
        self._rest = cfg["rest"]
        self._ws = cfg["ws"]
        self.network = cfg["network"]
        self._api_key = os.getenv(cfg["key_env"], "") if cfg["key_env"] else ""
        self._api_secret = os.getenv(cfg["secret_env"], "") if cfg["secret_env"] else ""
        self._pairs: list[str] = []
        self._tick_cb = None
        self._ws_task: asyncio.Task | None = None
        self._session: aiohttp.ClientSession | None = None
        self._symbol_filters: dict[str, dict] = {}
        self._time_offset_ms = 0

    @property
    def name(self) -> str:
        return "binance"

    @property
    def supports_live_trading(self) -> bool:
        return self.mode in ("demo", "live") and bool(self._api_key and self._api_secret)

    @property
    def supports_short(self) -> bool:
        return False

    @property
    def credential_status(self) -> str:
        if self.mode == "paper":
            return "not_required"
        return "configured" if self.supports_live_trading else "missing"

    def set_tick_callback(self, cb) -> None:
        self._tick_cb = cb

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _json_request(self, method: str, path: str, params=None, signed=False):
        params = dict(params or {})
        headers = {}
        if signed:
            if not self.supports_live_trading:
                raise RuntimeError(
                    f"Binance {self.network} credentials missing; configure "
                    f"{NETWORKS[self.mode]['key_env']} and {NETWORKS[self.mode]['secret_env']}"
                )
            params["timestamp"] = int(time.time() * 1000) + self._time_offset_ms
            params.setdefault("recvWindow", 5000)
            query = urlencode(params)
            params["signature"] = hmac.new(
                self._api_secret.encode(), query.encode(), hashlib.sha256
            ).hexdigest()
            headers["X-MBX-APIKEY"] = self._api_key
        session = await self._get_session()
        async with session.request(method, f"{self._rest}{path}", params=params, headers=headers) as resp:
            data = await resp.json(content_type=None)
            if resp.status >= 400:
                raise RuntimeError(f"Binance {self.network} HTTP {resp.status}: {data}")
            return data

    async def sync_time(self) -> None:
        data = await self._json_request("GET", "/api/v3/time")
        self._time_offset_ms = int(data["serverTime"]) - int(time.time() * 1000)

    async def get_ohlcv(self, symbol: str, timeframe: str = "M15", count: int = 200) -> list[dict]:
        interval = _TF_MAP.get(normalize_timeframe(timeframe), "15m")
        rows = await self._json_request("GET", "/api/v3/klines", {
            "symbol": symbol.upper(), "interval": interval, "limit": count,
        })
        return [{
            "time": int(r[0]) // 1000,
            "open": float(r[1]), "high": float(r[2]), "low": float(r[3]),
            "close": float(r[4]), "volume": float(r[5]), "taker_buy": float(r[9]),
        } for r in rows]

    async def get_price(self, symbol: str) -> Tick:
        d = await self._json_request("GET", "/api/v3/ticker/bookTicker", {"symbol": symbol.upper()})
        bid, ask = float(d["bidPrice"]), float(d["askPrice"])
        mid = (bid + ask) / 2
        return Tick(symbol.upper(), bid, ask, mid, mid, time.time())

    async def _filters(self, symbol: str) -> dict:
        symbol = symbol.upper()
        if symbol not in self._symbol_filters:
            data = await self._json_request("GET", "/api/v3/exchangeInfo", {"symbol": symbol})
            info = data["symbols"][0]
            filters = {item["filterType"]: item for item in info["filters"]}
            self._symbol_filters[symbol] = {
                "step_size": filters["LOT_SIZE"]["stepSize"],
                "min_qty": filters["LOT_SIZE"]["minQty"],
                "min_notional": (filters.get("NOTIONAL") or filters.get("MIN_NOTIONAL") or {}).get("minNotional", "0"),
            }
        return self._symbol_filters[symbol]

    async def normalize_quantity(self, symbol: str, qty: float, price: float) -> str:
        filters = await self._filters(symbol)
        step = Decimal(filters["step_size"])
        normalized = (Decimal(str(qty)) / step).to_integral_value(rounding=ROUND_DOWN) * step
        if normalized < Decimal(filters["min_qty"]):
            raise ValueError(f"{symbol} quantity below minQty")
        if normalized * Decimal(str(price)) < Decimal(filters["min_notional"]):
            raise ValueError(f"{symbol} order below minNotional")
        return format(normalized, "f")

    async def place_order(self, symbol: str, side: str, qty: float, sl: float = 0, tp: float = 0, comment: str = "") -> dict:
        if self.paper_mode:
            tick = await self.get_price(symbol)
            price = tick.ask if side.lower() == "buy" else tick.bid
            return {
                "ticket": random.randint(10_000_000, 99_999_999),
                "symbol": symbol.upper(), "side": side.lower(), "qty": qty,
                "price": price, "sl": sl, "tp": tp, "status": "filled",
                "paper": True, "network": self.network,
            }
        await self.sync_time()
        tick = await self.get_price(symbol)
        reference_price = tick.ask if side.lower() == "buy" else tick.bid
        quantity = await self.normalize_quantity(symbol, qty, reference_price)
        data = await self._json_request("POST", "/api/v3/order", {
            "symbol": symbol.upper(),
            "side": side.upper(),
            "type": "MARKET",
            "quantity": quantity,
            "newOrderRespType": "FULL",
        }, signed=True)
        executed_qty = float(data.get("executedQty") or quantity)
        quote_qty = float(data.get("cummulativeQuoteQty") or 0)
        fill_price = quote_qty / executed_qty if executed_qty > 0 and quote_qty > 0 else reference_price
        return {
            "ticket": data.get("orderId"),
            "symbol": data.get("symbol", symbol.upper()),
            "side": side.lower(),
            "qty": executed_qty,
            "price": fill_price,
            "sl": sl, "tp": tp,
            "status": str(data.get("status", "FILLED")).lower(),
            "paper": False,
            "network": self.network,
            "raw": data,
        }

    async def get_account(self) -> dict:
        await self.sync_time()
        data = await self._json_request("GET", "/api/v3/account", signed=True)
        balances = {
            row["asset"]: {"free": float(row["free"]), "locked": float(row["locked"])}
            for row in data.get("balances", [])
            if float(row["free"]) or float(row["locked"])
        }
        return {"balances": balances, "network": self.network, "can_trade": data.get("canTrade", False)}

    async def get_positions(self) -> list[dict]:
        if not self.supports_live_trading:
            return []
        account = await self.get_account()
        return [{"asset": asset, **values} for asset, values in account["balances"].items()]

    async def get_recent_deals(self, hours: int = 24, limit: int = 200) -> list[dict]:
        return []

    async def subscribe(self, pairs: list[str]) -> None:
        self._pairs = [p.upper() for p in pairs]
        if self._ws_task and not self._ws_task.done():
            self._ws_task.cancel()
        self._ws_task = asyncio.create_task(self._ws_loop())

    async def _ws_loop(self) -> None:
        while True:
            try:
                streams = "/".join(f"{p.lower()}@aggTrade" for p in self._pairs)
                if not streams:
                    await asyncio.sleep(1)
                    continue
                session = await self._get_session()
                async with session.ws_connect(f"{self._ws}?streams={streams}", heartbeat=30) as ws:
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            await self._handle_ws(msg.json())
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(3)

    async def _handle_ws(self, payload: dict) -> None:
        data = payload.get("data") or {}
        sym, price = data.get("s"), data.get("p")
        if sym is None or price is None:
            return
        if self._tick_cb is not None:
            result = self._tick_cb(
                sym, float(price), float(data.get("q") or 0),
                (data.get("T") or 0) / 1000.0, not data.get("m", False),
            )
            if asyncio.iscoroutine(result):
                await result

    async def close(self) -> None:
        if self._ws_task:
            self._ws_task.cancel()
        if self._session and not self._session.closed:
            await self._session.close()
