import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


MTF_FILTER_ENABLED = str(os.getenv("MTF_FILTER_ENABLED", "true")).lower() in ("1", "true", "yes", "on")
MTF_CACHE_SECONDS = int(os.getenv("MTF_CACHE_SECONDS", "300"))
MTF_MIN_CANDLES = int(os.getenv("MTF_MIN_CANDLES", "55"))

SYMBOL_PRIMARY_TF = {
    "XAU": os.getenv("MTF_XAU_PRIMARY", "H1"),
    "GBP": os.getenv("MTF_GBP_PRIMARY", "M15"),
    "EUR": os.getenv("MTF_EUR_PRIMARY", "M15"),
    "AUD": os.getenv("MTF_AUD_PRIMARY", "H1"),
    "NZD": os.getenv("MTF_NZD_PRIMARY", "H4"),
    "JPY": os.getenv("MTF_JPY_PRIMARY", "H1"),
    "DEFAULT": os.getenv("MTF_DEFAULT_PRIMARY", "H1"),
}


@dataclass
class TimeframeDecision:
    allowed: bool
    reason: str
    primary_timeframe: str = ""
    higher_timeframe: str = ""
    primary_trend: str = ""
    higher_trend: str = ""
    confidence_adjustment: int = 0


def _symbol_key(symbol: str) -> str:
    upper = symbol.upper()
    if "XAU" in upper or "GOLD" in upper:
        return "XAU"
    if upper.startswith("GBP"):
        return "GBP"
    if upper.startswith("EUR"):
        return "EUR"
    if upper.startswith("AUD"):
        return "AUD"
    if upper.startswith("NZD"):
        return "NZD"
    if "JPY" in upper:
        return "JPY"
    return "DEFAULT"


def _higher_tf(primary: str) -> str:
    return {
        "M1": "M15",
        "M5": "M15",
        "M15": "H1",
        "M30": "H1",
        "H1": "H4",
        "H4": "D1",
    }.get(primary, "H4")


def _close(candle: Dict[str, Any]) -> Optional[float]:
    try:
        return float(candle.get("close"))
    except Exception:
        return None


def _trend(candles: List[Dict[str, Any]]) -> str:
    closes = [_close(c) for c in candles]
    closes = [c for c in closes if c is not None]
    if len(closes) < MTF_MIN_CANDLES:
        return "unknown"
    sma20 = sum(closes[-20:]) / 20
    sma50 = sum(closes[-50:]) / 50
    current = closes[-1]
    old = closes[-10]
    momentum_pct = ((current - old) / old) * 100 if old else 0.0
    if current > sma20 > sma50 and momentum_pct > 0:
        return "up"
    if current < sma20 < sma50 and momentum_pct < 0:
        return "down"
    return "range"


def _matches(action: str, trend: str) -> bool:
    action = str(action or "").upper()
    if trend == "up":
        return action == "BUY"
    if trend == "down":
        return action == "SELL"
    return False


class MultiTimeframeFilter:
    """Confirms entry direction against candle timeframes instead of tick noise alone."""

    def __init__(self, cache_seconds: int = MTF_CACHE_SECONDS, enabled: bool = MTF_FILTER_ENABLED):
        self.cache_seconds = cache_seconds
        self.enabled = enabled
        self._cache: Dict[tuple, tuple[float, List[Dict[str, Any]]]] = {}
        self._last_summary: Dict[str, Any] = {}

    def primary_timeframe(self, symbol: str, dna_timeframe: str = "") -> str:
        symbol_key = _symbol_key(symbol)
        if symbol_key == "XAU":
            return SYMBOL_PRIMARY_TF["XAU"]
        if dna_timeframe in ("M15", "H1", "H4"):
            return dna_timeframe
        return SYMBOL_PRIMARY_TF.get(symbol_key, SYMBOL_PRIMARY_TF["DEFAULT"])

    async def _candles(self, mt5: Any, symbol: str, timeframe: str, count: int = 80) -> List[Dict[str, Any]]:
        key = (symbol, timeframe, count)
        now = time.time()
        cached = self._cache.get(key)
        if cached and now - cached[0] < self.cache_seconds:
            return cached[1]
        candles = await mt5.get_ohlcv(symbol, timeframe=timeframe, count=count)
        if not isinstance(candles, list):
            candles = []
        self._cache[key] = (now, candles)
        return candles

    async def evaluate(self, mt5: Any, symbol: str, action: str, dna_timeframe: str = "") -> TimeframeDecision:
        if not self.enabled:
            return TimeframeDecision(True, "MTF filter disabled")

        primary = self.primary_timeframe(symbol, dna_timeframe)
        higher = _higher_tf(primary)

        try:
            primary_candles = await self._candles(mt5, symbol, primary)
            higher_candles = await self._candles(mt5, symbol, higher)
        except Exception as e:
            return TimeframeDecision(False, f"MTF data unavailable: {e}", primary, higher)

        primary_trend = _trend(primary_candles)
        higher_trend = _trend(higher_candles)
        self._last_summary[symbol] = {
            "primary_timeframe": primary,
            "higher_timeframe": higher,
            "primary_trend": primary_trend,
            "higher_trend": higher_trend,
            "updated_at": time.time(),
        }

        if primary_trend == "unknown" or higher_trend == "unknown":
            return TimeframeDecision(False, "MTF insufficient candle data", primary, higher, primary_trend, higher_trend)

        # XAU is stricter: do not trade against higher timeframe and avoid range unless primary agrees clearly.
        strict = _symbol_key(symbol) == "XAU"
        primary_match = _matches(action, primary_trend)
        higher_match = _matches(action, higher_trend)

        if primary_match and higher_match:
            return TimeframeDecision(True, "MTF aligned", primary, higher, primary_trend, higher_trend, confidence_adjustment=5)
        if primary_match and higher_trend == "range" and not strict:
            return TimeframeDecision(True, "MTF primary aligned; higher range", primary, higher, primary_trend, higher_trend, confidence_adjustment=0)
        if primary_trend == "range":
            return TimeframeDecision(False, f"MTF primary {primary} is range", primary, higher, primary_trend, higher_trend)
        if higher_trend not in ("range", primary_trend):
            return TimeframeDecision(False, f"MTF conflict {primary}:{primary_trend} vs {higher}:{higher_trend}", primary, higher, primary_trend, higher_trend)
        return TimeframeDecision(False, f"MTF rejects {action} against {primary}:{primary_trend}", primary, higher, primary_trend, higher_trend)

    def summary(self) -> Dict[str, Any]:
        return dict(self._last_summary)
