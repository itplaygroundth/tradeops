"""
RegimeService — cached Markov regime per symbol for the crypto engine.

Wraps markov_regime.detect_regime() with a TTL cache so agent_manager
fetches D1 candles at most once per REGIME_REFRESH_SECONDS per symbol.
"""
import asyncio
import logging
import os
import time
from typing import Callable, Dict, Optional, Tuple

from engine.markov_regime import detect_regime

logger = logging.getLogger(__name__)

REGIME_REFRESH_SECONDS = int(os.getenv("REGIME_REFRESH_SECONDS", "3600"))
_FALLBACK = ("RANGING", {})


class RegimeService:
    def __init__(self, fetch_ohlcv: Callable):
        """
        fetch_ohlcv(symbol, timeframe, count) → list[dict] — may be sync or async.
        Typically: router.get_ohlcv
        """
        self._fetch = fetch_ohlcv
        # {symbol: (regime, trans_prob, fetched_at)}
        self._cache: Dict[str, Tuple[str, dict, float]] = {}

    async def get(self, symbol: str) -> Tuple[str, dict]:
        """Return (regime, trans_prob) for symbol, using cache if fresh."""
        cached = self._cache.get(symbol)
        if cached and time.time() - cached[2] < REGIME_REFRESH_SECONDS:
            return cached[0], cached[1]

        if self._fetch is None:
            return _FALLBACK

        try:
            result = self._fetch(symbol, "D1", 60)
            if asyncio.iscoroutine(result):
                candles = await result
            else:
                candles = result
            regime, trans_prob = detect_regime(candles or [])
            self._cache[symbol] = (regime, trans_prob, time.time())
            logger.info("RegimeService %s → %s", symbol, regime)
            return regime, trans_prob
        except Exception:
            logger.exception("RegimeService fetch failed for %s; using cached/fallback", symbol)
            if cached:
                return cached[0], cached[1]
            return _FALLBACK

    def summary(self) -> dict:
        return {
            sym: {"regime": v[0], "age_s": round(time.time() - v[2])}
            for sym, v in self._cache.items()
        }
