"""Routes calls to the active exchange feed; handles mode + exchange switching."""
from exchange.base import ExchangeFeed, Tick
from exchange.binance import BinanceFeed
from exchange.bybit import BybitFeed

_FEEDS = {
    "binance": BinanceFeed,
    "bybit": BybitFeed,
}


class ExchangeRouter:
    def __init__(self, exchange: str = "binance", paper_mode: bool = True):
        exchange = exchange.lower()
        if exchange not in _FEEDS:
            raise ValueError(f"Unknown exchange: {exchange}")
        self._exchange = exchange
        self._paper_mode = paper_mode
        self._tick_cb = None
        self._feed: ExchangeFeed = _FEEDS[exchange](paper_mode=paper_mode)

    # ---- properties ----------------------------------------------------
    @property
    def active_feed(self) -> ExchangeFeed:
        return self._feed

    @property
    def exchange_name(self) -> str:
        return self._exchange

    @property
    def paper_mode(self) -> bool:
        return self._paper_mode

    # ---- control -------------------------------------------------------
    async def switch_exchange(self, exchange: str) -> None:
        exchange = exchange.lower()
        if exchange not in _FEEDS:
            raise ValueError(f"Unknown exchange: {exchange}")
        if exchange == self._exchange:
            return
        old = self._feed
        try:
            close = getattr(old, "close", None)
            if close is not None:
                await close()
        except Exception:
            pass
        self._exchange = exchange
        self._feed = _FEEDS[exchange](paper_mode=self._paper_mode)
        if self._tick_cb is not None:
            self._feed.set_tick_callback(self._tick_cb)

    def set_mode(self, paper: bool) -> None:
        self._paper_mode = paper
        self._feed.paper_mode = paper

    def set_tick_callback(self, cb) -> None:
        # cb signature: cb(symbol, price, volume, timestamp)
        self._tick_cb = cb
        self._feed.set_tick_callback(cb)

    # ---- delegation ----------------------------------------------------
    async def subscribe(self, pairs: list[str]) -> None:
        return await self._feed.subscribe(pairs)

    async def get_price(self, symbol: str) -> Tick:
        return await self._feed.get_price(symbol)

    async def get_ohlcv(self, symbol: str, timeframe: str = "M15", count: int = 200) -> list[dict]:
        return await self._feed.get_ohlcv(symbol, timeframe=timeframe, count=count)

    async def place_order(self, symbol, side, qty, sl=0, tp=0, comment="") -> dict:
        return await self._feed.place_order(symbol, side, qty, sl=sl, tp=tp, comment=comment)

    async def get_positions(self) -> list[dict]:
        return await self._feed.get_positions()

    async def get_recent_deals(self, hours=24, limit=200) -> list[dict]:
        return await self._feed.get_recent_deals(hours=hours, limit=limit)
