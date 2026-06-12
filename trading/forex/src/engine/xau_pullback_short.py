import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


XAU_PULLBACK_ENABLED = str(os.getenv("XAU_PULLBACK_ENABLED", "true")).lower() in ("1", "true", "yes", "on")
XAU_PULLBACK_CACHE_SECONDS = int(os.getenv("XAU_PULLBACK_CACHE_SECONDS", "60"))
XAU_PULLBACK_MIN_CANDLES = int(os.getenv("XAU_PULLBACK_MIN_CANDLES", "55"))
XAU_PULLBACK_PRIMARY_TF = os.getenv("XAU_PULLBACK_PRIMARY_TF", "H1")
XAU_PULLBACK_HIGHER_TF = os.getenv("XAU_PULLBACK_HIGHER_TF", "H4")
XAU_PULLBACK_EMA_TOUCH_PCT = float(os.getenv("XAU_PULLBACK_EMA_TOUCH_PCT", "0.35"))
XAU_PULLBACK_MAX_EXTENSION_PCT = float(os.getenv("XAU_PULLBACK_MAX_EXTENSION_PCT", "0.45"))
XAU_PULLBACK_MIN_CONFIDENCE = int(os.getenv("XAU_PULLBACK_MIN_CONFIDENCE", "72"))
XAU_BASKET_MAX_POSITIONS = int(os.getenv("XAU_BASKET_MAX_POSITIONS", "3"))
XAU_BASKET_COOLDOWN_SECONDS = int(os.getenv("XAU_BASKET_COOLDOWN_SECONDS", "180"))


@dataclass
class PullbackDecision:
    allowed: bool
    reason: str
    confidence: int = 0
    action: str = "HOLD"
    primary_trend: str = ""
    higher_trend: str = ""
    basket_max_positions: int = 1
    basket_cooldown_seconds: int = 900


def _is_xau(symbol: str) -> bool:
    upper = str(symbol or "").upper()
    return "XAU" in upper or "GOLD" in upper


def _float(value: Any) -> Optional[float]:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except Exception:
        return None


def _ema(values: List[float], period: int) -> Optional[float]:
    if len(values) < period:
        return None
    alpha = 2.0 / (period + 1.0)
    ema = sum(values[:period]) / period
    for value in values[period:]:
        ema = value * alpha + ema * (1.0 - alpha)
    return ema


def _trend(candles: List[Dict[str, Any]]) -> str:
    closes = [_float(c.get("close")) for c in candles]
    closes = [c for c in closes if c is not None]
    if len(closes) < XAU_PULLBACK_MIN_CANDLES:
        return "unknown"
    ema20 = _ema(closes, 20)
    ema50 = _ema(closes, 50)
    if ema20 is None or ema50 is None:
        return "unknown"
    current = closes[-1]
    old = closes[-10]
    momentum_pct = ((current - old) / old) * 100.0 if old else 0.0
    if current < ema20 < ema50 and momentum_pct < 0:
        return "down"
    if current > ema20 > ema50 and momentum_pct > 0:
        return "up"
    return "range"


class XauPullbackShortFilter:
    """Detects XAU downtrend pullback/rejection shorts and blocks chase entries."""

    def __init__(self, enabled: bool = XAU_PULLBACK_ENABLED, cache_seconds: int = XAU_PULLBACK_CACHE_SECONDS):
        self.enabled = enabled
        self.cache_seconds = cache_seconds
        self._cache: Dict[tuple, tuple[float, List[Dict[str, Any]]]] = {}
        self._last_summary: Dict[str, Any] = {}

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

    async def evaluate(self, mt5: Any, symbol: str, price: float) -> PullbackDecision:
        if not self.enabled or not _is_xau(symbol):
            return PullbackDecision(True, "XAU pullback filter inactive")
        try:
            primary = await self._candles(mt5, symbol, XAU_PULLBACK_PRIMARY_TF)
            higher = await self._candles(mt5, symbol, XAU_PULLBACK_HIGHER_TF)
        except Exception as exc:
            decision = PullbackDecision(False, f"XAU pullback data unavailable: {exc}")
            self._record(symbol, decision)
            return decision

        decision = self._evaluate_candles(symbol, primary, higher, price)
        self._record(symbol, decision)
        return decision

    def _evaluate_candles(
        self,
        symbol: str,
        primary: List[Dict[str, Any]],
        higher: List[Dict[str, Any]],
        price: float,
    ) -> PullbackDecision:
        primary_trend = _trend(primary)
        higher_trend = _trend(higher)
        if primary_trend != "down" or higher_trend != "down":
            return PullbackDecision(
                False,
                f"XAU pullback waits for downtrend alignment {XAU_PULLBACK_PRIMARY_TF}:{primary_trend} {XAU_PULLBACK_HIGHER_TF}:{higher_trend}",
                primary_trend=primary_trend,
                higher_trend=higher_trend,
            )

        closes = [_float(c.get("close")) for c in primary]
        closes = [c for c in closes if c is not None]
        if len(closes) < XAU_PULLBACK_MIN_CANDLES or not primary:
            return PullbackDecision(False, "XAU pullback insufficient candles", primary_trend=primary_trend, higher_trend=higher_trend)

        ema20 = _ema(closes, 20)
        ema50 = _ema(closes, 50)
        latest = primary[-1]
        latest_open = _float(latest.get("open"))
        latest_high = _float(latest.get("high"))
        latest_low = _float(latest.get("low"))
        latest_close = _float(latest.get("close"))
        if None in (ema20, ema50, latest_open, latest_high, latest_low, latest_close):
            return PullbackDecision(False, "XAU pullback incomplete candle data", primary_trend=primary_trend, higher_trend=higher_trend)

        ema20_value = float(ema20)
        latest_open = float(latest_open)
        latest_high = float(latest_high)
        latest_low = float(latest_low)
        latest_close = float(latest_close)
        price = float(price or latest_close)

        touch_pct = abs(latest_high - ema20_value) / ema20_value * 100.0
        close_extension_pct = max((ema20_value - price) / ema20_value * 100.0, 0.0)
        candle_range = max(latest_high - latest_low, 0.0)
        body = abs(latest_open - latest_close)
        upper_wick = latest_high - max(latest_open, latest_close)
        bearish_close = latest_close < latest_open
        rejection = bearish_close and (
            latest_close <= ema20_value
            or (body > 0 and upper_wick >= body * 0.6)
            or (candle_range > 0 and upper_wick / candle_range >= 0.35)
        )

        if touch_pct > XAU_PULLBACK_EMA_TOUCH_PCT:
            return PullbackDecision(
                False,
                f"XAU pullback not near EMA20 touch={touch_pct:.2f}% > {XAU_PULLBACK_EMA_TOUCH_PCT:.2f}%",
                primary_trend=primary_trend,
                higher_trend=higher_trend,
            )
        if close_extension_pct > XAU_PULLBACK_MAX_EXTENSION_PCT:
            return PullbackDecision(
                False,
                f"XAU pullback avoids chasing extension={close_extension_pct:.2f}% > {XAU_PULLBACK_MAX_EXTENSION_PCT:.2f}%",
                primary_trend=primary_trend,
                higher_trend=higher_trend,
            )
        if not rejection:
            return PullbackDecision(
                False,
                "XAU pullback waiting for bearish rejection",
                primary_trend=primary_trend,
                higher_trend=higher_trend,
            )

        confidence = XAU_PULLBACK_MIN_CONFIDENCE
        if latest_close < ema20_value and latest_close < latest_open:
            confidence += 5
        if close_extension_pct <= XAU_PULLBACK_MAX_EXTENSION_PCT / 2:
            confidence += 3
        return PullbackDecision(
            True,
            (
                f"XAU pullback short: H1/H4 down, EMA20 touch={touch_pct:.2f}%, "
                f"extension={close_extension_pct:.2f}%, rejection"
            ),
            confidence=min(90, confidence),
            action="SHORT",
            primary_trend=primary_trend,
            higher_trend=higher_trend,
            basket_max_positions=max(1, XAU_BASKET_MAX_POSITIONS),
            basket_cooldown_seconds=max(0, XAU_BASKET_COOLDOWN_SECONDS),
        )

    def _record(self, symbol: str, decision: PullbackDecision):
        self._last_summary[symbol] = {
            "allowed": decision.allowed,
            "reason": decision.reason,
            "confidence": decision.confidence,
            "action": decision.action,
            "primary_trend": decision.primary_trend,
            "higher_trend": decision.higher_trend,
            "basket_max_positions": decision.basket_max_positions,
            "basket_cooldown_seconds": decision.basket_cooldown_seconds,
            "updated_at": time.time(),
        }

    def summary(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "policy": {
                "primary_timeframe": XAU_PULLBACK_PRIMARY_TF,
                "higher_timeframe": XAU_PULLBACK_HIGHER_TF,
                "ema_touch_pct": XAU_PULLBACK_EMA_TOUCH_PCT,
                "max_extension_pct": XAU_PULLBACK_MAX_EXTENSION_PCT,
                "min_confidence": XAU_PULLBACK_MIN_CONFIDENCE,
                "basket_max_positions": XAU_BASKET_MAX_POSITIONS,
                "basket_cooldown_seconds": XAU_BASKET_COOLDOWN_SECONDS,
            },
            "latest": dict(self._last_summary),
        }
