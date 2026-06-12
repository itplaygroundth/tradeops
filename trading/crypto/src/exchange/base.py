"""Abstract exchange feed interface + shared Tick dataclass."""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class Tick:
    symbol: str
    bid: float
    ask: float
    mid: float
    last: float
    timestamp: float


# Shared timeframe map. Subclasses translate to exchange-native intervals.
TIMEFRAMES = ("M1", "M5", "M15", "M30", "H1", "H4", "D1")


class ExchangeFeed(ABC):
    """Common interface every exchange adapter must implement."""

    @abstractmethod
    async def subscribe(self, pairs: list[str]) -> None: ...

    @abstractmethod
    async def get_price(self, symbol: str) -> Tick: ...

    @abstractmethod
    async def get_ohlcv(self, symbol: str, timeframe: str = "M15", count: int = 200) -> list[dict]: ...

    @abstractmethod
    async def place_order(self, symbol: str, side: str, qty: float, sl: float = 0, tp: float = 0, comment: str = "") -> dict: ...

    @abstractmethod
    async def get_positions(self) -> list[dict]: ...

    @abstractmethod
    async def get_recent_deals(self, hours: int = 24, limit: int = 200) -> list[dict]: ...

    @property
    @abstractmethod
    def name(self) -> str: ...
