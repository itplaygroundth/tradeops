"""Binance spot exchange feed (REST + WebSocket aggTrade stream)."""
import asyncio
import random
import time

import aiohttp

from exchange.base import ExchangeFeed, Tick

_REST = "https://api.binance.com"
_WS = "wss://stream.binance.com:9443/stream"

_TF_MAP = {
    "M1": "1m",
    "M5": "5m",
    "M15": "15m",
    "M30": "30m",
    "H1": "1h",
    "H4": "4h",
    "D1": "1d",
}

_TF_ALIASES = {
    "1m": "M1",
    "5m": "M5",
    "15m": "M15",
    "30m": "M30",
    "1h": "H1",
    "4h": "H4",
    "1d": "D1",
}


def normalize_timeframe(timeframe: str) -> str:
    raw = str(timeframe or "M15").strip()
    return _TF_ALIASES.get(raw.lower(), raw.upper())


class BinanceFeed(ExchangeFeed):
    def __init__(self, paper_mode: bool = True):
        self.paper_mode = paper_mode
        self._pairs: list[str] = []
        self._tick_cb = None
        self._ws_task: asyncio.Task | None = None
        self._session: aiohttp.ClientSession | None = None

    @property
    def name(self) -> str:
        return "binance"

    def set_tick_callback(self, cb) -> None:
        self._tick_cb = cb

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    # ---- REST ----------------------------------------------------------
    async def get_ohlcv(self, symbol: str, timeframe: str = "M15", count: int = 200) -> list[dict]:
        interval = _TF_MAP.get(normalize_timeframe(timeframe), "15m")
        url = f"{_REST}/api/v3/klines"
        params = {"symbol": symbol.upper(), "interval": interval, "limit": count}
        session = await self._get_session()
        async with session.get(url, params=params) as resp:
            resp.raise_for_status()
            rows = await resp.json()
        out = []
        for r in rows:
            out.append({
                "time": int(r[0]) // 1000,
                "open": float(r[1]),
                "high": float(r[2]),
                "low": float(r[3]),
                "close": float(r[4]),
                "volume": float(r[5]),
                # field [9] = taker buy base-asset volume (buy aggressor volume)
                "taker_buy": float(r[9]),
            })
        return out

    async def get_price(self, symbol: str) -> Tick:
        url = f"{_REST}/api/v3/ticker/bookTicker"
        session = await self._get_session()
        async with session.get(url, params={"symbol": symbol.upper()}) as resp:
            resp.raise_for_status()
            d = await resp.json()
        bid = float(d["bidPrice"])
        ask = float(d["askPrice"])
        mid = (bid + ask) / 2
        return Tick(symbol.upper(), bid, ask, mid, mid, time.time())

    # ---- Orders --------------------------------------------------------
    async def place_order(self, symbol: str, side: str, qty: float, sl: float = 0, tp: float = 0, comment: str = "") -> dict:
        if self.paper_mode:
            tick = await self.get_price(symbol)
            price = tick.ask if side.lower() == "buy" else tick.bid
            return {
                "ticket": random.randint(10_000_000, 99_999_999),
                "symbol": symbol.upper(),
                "side": side.lower(),
                "qty": qty,
                "price": price,
                "sl": sl,
                "tp": tp,
                "status": "filled",
                "paper": True,
            }
        # Live trading not implemented — requires signed API keys.
        raise NotImplementedError("Binance live order placement not implemented")

    async def get_positions(self) -> list[dict]:
        return []

    async def get_recent_deals(self, hours: int = 24, limit: int = 200) -> list[dict]:
        return []

    # ---- WebSocket -----------------------------------------------------
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
                url = f"{_WS}?streams={streams}"
                session = await self._get_session()
                async with session.ws_connect(url, heartbeat=30) as ws:
                    async for msg in ws:
                        if msg.type != aiohttp.WSMsgType.TEXT:
                            continue
                        await self._handle_ws(msg.json())
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(3)

    async def _handle_ws(self, payload: dict) -> None:
        data = payload.get("data") or {}
        sym = data.get("s")
        price = data.get("p")
        qty = data.get("q")
        ts_ms = data.get("T")
        if sym is None or price is None:
            return
        # aggTrade "m" = buyer is market maker -> the SELLER was the aggressor.
        is_buy = not data.get("m", False)
        if self._tick_cb is not None:
            res = self._tick_cb(sym, float(price), float(qty or 0), (ts_ms or 0) / 1000.0, is_buy)
            if asyncio.iscoroutine(res):
                await res

    async def close(self) -> None:
        if self._ws_task:
            self._ws_task.cancel()
        if self._session and not self._session.closed:
            await self._session.close()
