"""Routes calls to the active exchange feed; handles mode + exchange switching."""
from exchange.base import ExchangeFeed, Tick
from exchange.binance import BinanceFeed
from exchange.bybit import BybitFeed

_FEEDS = {
    "binance": BinanceFeed,
    "bybit": BybitFeed,
}


class ExchangeRouter:
    def __init__(self, exchange: str = "binance", paper_mode: bool = True, mode: str = None):
        exchange = exchange.lower()
        if exchange not in _FEEDS:
            raise ValueError(f"Unknown exchange: {exchange}")
        self._exchange = exchange
        self._mode = mode or ("paper" if paper_mode else "live")
        self._paper_mode = self._mode == "paper"
        self._tick_cb = None
        self._feed: ExchangeFeed = self._build_feed(exchange)

    def _build_feed(self, exchange: str) -> ExchangeFeed:
        feed_cls = _FEEDS[exchange]
        if exchange == "binance":
            return feed_cls(paper_mode=self._paper_mode, mode=self._mode)
        return feed_cls(paper_mode=self._paper_mode)

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

    @property
    def live_trading_supported(self) -> bool:
        return bool(getattr(self._feed, "supports_live_trading", False))

    @property
    def network(self) -> str:
        return str(getattr(self._feed, "network", "paper" if self._paper_mode else "production"))

    @property
    def credential_status(self) -> str:
        return str(getattr(self._feed, "credential_status", "not_supported"))

    @property
    def supports_short(self) -> bool:
        return bool(getattr(self._feed, "supports_short", False))

    @property
    def uses_ticket_positions(self) -> bool:
        return bool(getattr(self._feed, "uses_ticket_positions", False))

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
        self._feed = self._build_feed(exchange)
        if self._tick_cb is not None:
            self._feed.set_tick_callback(self._tick_cb)

    async def set_mode(self, mode) -> None:
        if isinstance(mode, bool):
            mode = "paper" if mode else "live"
        if mode not in ("paper", "demo", "live"):
            raise ValueError(f"Unsupported mode: {mode}")
        old = self._feed
        try:
            await old.close()
        except Exception:
            pass
        self._mode = mode
        self._paper_mode = mode == "paper"
        self._feed = self._build_feed(self._exchange)
        if self._tick_cb is not None:
            self._feed.set_tick_callback(self._tick_cb)
        if getattr(old, "_pairs", None):
            await self._feed.subscribe(list(old._pairs))

    def set_tick_callback(self, cb) -> None:
        # cb signature: cb(symbol, price, volume, timestamp, is_buy)
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

    async def get_account(self) -> dict:
        getter = getattr(self._feed, "get_account", None)
        if getter is None:
            return {}
        return await getter()
