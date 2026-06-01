"""
MT5 Feed — Real-time price stream from MT5 API Server.
Replaces Binance WebSocket in the crypto version.
"""
import asyncio
import json
import logging
import time
import websockets
from typing import Dict, Callable, List, Optional

logger = logging.getLogger("mt5_feed")

DEFAULT_SYMBOLS = [
    "EURUSDm",
    "GBPUSDm",
    "USDJPYm",
    "XAUUSDm",
    "USDCHFm",
    "AUDUSDm",
    "USDCADm",
    "NZDUSDm",
]

class MT5Feed:
    def __init__(self, ws_url: str, symbols: List[str] = None):
        self.ws_url = ws_url
        self.symbols = symbols or DEFAULT_SYMBOLS
        self._callbacks: List[Callable] = []
        self._running = False
        self._last_prices: Dict[str, dict] = {}

    def on_tick(self, callback: Callable):
        """Registers a callback for incoming tick data."""
        self._callbacks.append(callback)

    async def start(self):
        """Starts streaming prices from MT5 server."""
        self._running = True
        symbols_param = ",".join(self.symbols)
        url = f"{self.ws_url}?symbols={symbols_param}"
        logger.info(f"MT5Feed connecting to: {url}")

        while self._running:
            try:
                # ping_interval/ping_timeout detect half-open TCP (server stops
                # sending without FIN); without these the read hangs forever.
                async with websockets.connect(
                    url, ping_interval=20, ping_timeout=20, close_timeout=5
                ) as ws:
                    logger.info("MT5Feed connected successfully ✓")
                    while self._running:
                        # recv timeout guards against a silently stalled feed
                        try:
                            message = await asyncio.wait_for(ws.recv(), timeout=30)
                        except asyncio.TimeoutError:
                            logger.warning("MT5Feed: no tick for 30s — reconnecting")
                            break
                        prices = json.loads(message)
                        await self._process_tick(prices)
            except Exception as e:
                if self._running:
                    logger.warning(f"MT5Feed disconnected: {e} — retrying in 3 seconds")
                    await asyncio.sleep(3)
                else:
                    break

    async def _process_tick(self, prices: Dict[str, dict]):
        """Processes incoming tick data and routes to callbacks."""
        now = time.time()
        # Build uppercase→canonical map for broker that uppercases symbol names
        sym_map = {s.upper(): s for s in self.symbols}
        for raw_sym, data in prices.items():
            symbol = sym_map.get(raw_sym.upper(), raw_sym)
            if "error" in data or "bid" not in data:
                continue
            mid = (data["bid"] + data["ask"]) / 2
            tick = {
                "symbol": symbol,
                "price": mid,
                "bid": data["bid"],
                "ask": data["ask"],
                "volume": 1.0,  # Placeholder for MT5 tick volume
                "timestamp": data.get("time", now),
            }
            self._last_prices[symbol] = tick
            for cb in self._callbacks:
                try:
                    await cb(tick)
                except Exception as e:
                    logger.error(f"Tick callback error: {e}")

    def get_last_price(self, symbol: str) -> Optional[float]:
        tick = self._last_prices.get(symbol)
        return tick["price"] if tick else None

    async def stop(self):
        self._running = False
