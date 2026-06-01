"""Bybit spot exchange feed (REST + WebSocket publicTrade stream)."""
import asyncio
import json
import random
import time

import aiohttp

from exchange.base import ExchangeFeed, Tick

_REST = "https://api.bybit.com"
_WS = "wss://stream.bybit.com/v5/public/spot"

_TF_MAP = {
    "M1": "1",
    "M5": "5",
    "M15": "15",
    "M30": "30",
    "H1": "60",
    "H4": "240",
    "D1": "D",
}


class BybitFeed(ExchangeFeed):
    def __init__(self, paper_mode: bool = True):
        self.paper_mode = paper_mode
        self._pairs: list[str] = []
        self._tick_cb = None
        self._ws_task: asyncio.Task | None = None
        self._session: aiohttp.ClientSession | None = None

    @property
    def name(self) -> str:
        return "bybit"

    def set_tick_callback(self, cb) -> None:
        self._tick_cb = cb

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    # ---- REST ----------------------------------------------------------
    async def get_ohlcv(self, symbol: str, timeframe: str = "M15", count: int = 200) -> list[dict]:
        interval = _TF_MAP.get(timeframe, "15")
        url = f"{_REST}/v5/market/kline"
        params = {"category": "spot", "symbol": symbol.upper(), "interval": interval, "limit": count}
        session = await self._get_session()
        async with session.get(url, params=params) as resp:
            resp.raise_for_status()
            data = await resp.json()
        rows = data["result"]["list"]
        out = []
        for r in rows:
            out.append({
                "time": int(r[0]) // 1000,
                "open": float(r[1]),
                "high": float(r[2]),
                "low": float(r[3]),
                "close": float(r[4]),
                "volume": float(r[5]),
            })
        # Bybit returns newest-first → reverse to ascending time
        out.reverse()
        return out

    async def get_price(self, symbol: str) -> Tick:
        url = f"{_REST}/v5/market/tickers"
        session = await self._get_session()
        async with session.get(url, params={"category": "spot", "symbol": symbol.upper()}) as resp:
            resp.raise_for_status()
            data = await resp.json()
        d = data["result"]["list"][0]
        bid = float(d["bid1Price"])
        ask = float(d["ask1Price"])
        last = float(d["lastPrice"])
        mid = (bid + ask) / 2
        return Tick(symbol.upper(), bid, ask, mid, last, time.time())

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
        raise NotImplementedError("Bybit live order placement not implemented")

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
                if not self._pairs:
                    await asyncio.sleep(1)
                    continue
                session = await self._get_session()
                async with session.ws_connect(_WS, heartbeat=20) as ws:
                    args = [f"publicTrade.{p}" for p in self._pairs]
                    await ws.send_str(json.dumps({"op": "subscribe", "args": args}))
                    async for msg in ws:
                        if msg.type != aiohttp.WSMsgType.TEXT:
                            continue
                        await self._handle_ws(msg.json())
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(3)

    async def _handle_ws(self, payload: dict) -> None:
        topic = payload.get("topic", "")
        if not topic.startswith("publicTrade."):
            return
        for trade in payload.get("data") or []:
            sym = trade.get("s")
            price = trade.get("p")
            qty = trade.get("v")
            ts_ms = trade.get("T")
            if sym is None or price is None:
                continue
            if self._tick_cb is not None:
                res = self._tick_cb(sym, float(price), float(qty or 0), (ts_ms or 0) / 1000.0)
                if asyncio.iscoroutine(res):
                    await res

    async def close(self) -> None:
        if self._ws_task:
            self._ws_task.cancel()
        if self._session and not self._session.closed:
            await self._session.close()
