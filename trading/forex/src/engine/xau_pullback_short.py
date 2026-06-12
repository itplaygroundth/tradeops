import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


PULLBACK_ENTRY_ENABLED = str(os.getenv("PULLBACK_ENTRY_ENABLED", os.getenv("XAU_PULLBACK_ENABLED", "true"))).lower() in (
    "1",
    "true",
    "yes",
    "on",
)
PULLBACK_CACHE_SECONDS = int(os.getenv("PULLBACK_CACHE_SECONDS", os.getenv("XAU_PULLBACK_CACHE_SECONDS", "60")))
PULLBACK_MIN_CANDLES = int(os.getenv("PULLBACK_MIN_CANDLES", os.getenv("XAU_PULLBACK_MIN_CANDLES", "55")))
HIGH_VOL_BASKET_MAX = int(os.getenv("PULLBACK_HIGH_VOL_BASKET_MAX", "1"))
HIGH_VOL_CONFIDENCE_BONUS = int(os.getenv("PULLBACK_HIGH_VOL_CONFIDENCE_BONUS", "5"))


@dataclass(frozen=True)
class AssetPullbackPolicy:
    key: str
    primary_timeframe: str
    higher_timeframe: str
    ema_touch_pct: float
    max_extension_pct: float
    min_confidence: int
    basket_max_positions: int
    basket_cooldown_seconds: int
    high_vol_atr_pct: float


DEFAULT_POLICY = AssetPullbackPolicy(
    key="DEFAULT",
    primary_timeframe=os.getenv("PULLBACK_DEFAULT_PRIMARY_TF", "H1"),
    higher_timeframe=os.getenv("PULLBACK_DEFAULT_HIGHER_TF", "H4"),
    ema_touch_pct=float(os.getenv("PULLBACK_DEFAULT_EMA_TOUCH_PCT", "0.12")),
    max_extension_pct=float(os.getenv("PULLBACK_DEFAULT_MAX_EXTENSION_PCT", "0.18")),
    min_confidence=int(os.getenv("PULLBACK_DEFAULT_MIN_CONFIDENCE", "74")),
    basket_max_positions=int(os.getenv("PULLBACK_DEFAULT_BASKET_MAX", "1")),
    basket_cooldown_seconds=int(os.getenv("PULLBACK_DEFAULT_BASKET_COOLDOWN_SECONDS", "600")),
    high_vol_atr_pct=float(os.getenv("PULLBACK_DEFAULT_HIGH_VOL_ATR_PCT", "0.18")),
)


POLICIES: Dict[str, AssetPullbackPolicy] = {
    "XAU": AssetPullbackPolicy(
        key="XAU",
        primary_timeframe=os.getenv("XAU_PULLBACK_PRIMARY_TF", "H1"),
        higher_timeframe=os.getenv("XAU_PULLBACK_HIGHER_TF", "H4"),
        ema_touch_pct=float(os.getenv("XAU_PULLBACK_EMA_TOUCH_PCT", "0.35")),
        max_extension_pct=float(os.getenv("XAU_PULLBACK_MAX_EXTENSION_PCT", "0.45")),
        min_confidence=int(os.getenv("XAU_PULLBACK_MIN_CONFIDENCE", "72")),
        basket_max_positions=int(os.getenv("XAU_BASKET_MAX_POSITIONS", "3")),
        basket_cooldown_seconds=int(os.getenv("XAU_BASKET_COOLDOWN_SECONDS", "180")),
        high_vol_atr_pct=float(os.getenv("XAU_PULLBACK_HIGH_VOL_ATR_PCT", "0.75")),
    ),
    "EUR": AssetPullbackPolicy(
        key="EUR",
        primary_timeframe=os.getenv("EUR_PULLBACK_PRIMARY_TF", "M15"),
        higher_timeframe=os.getenv("EUR_PULLBACK_HIGHER_TF", "H1"),
        ema_touch_pct=float(os.getenv("EUR_PULLBACK_EMA_TOUCH_PCT", "0.08")),
        max_extension_pct=float(os.getenv("EUR_PULLBACK_MAX_EXTENSION_PCT", "0.12")),
        min_confidence=int(os.getenv("EUR_PULLBACK_MIN_CONFIDENCE", "74")),
        basket_max_positions=int(os.getenv("EUR_BASKET_MAX_POSITIONS", "1")),
        basket_cooldown_seconds=int(os.getenv("EUR_BASKET_COOLDOWN_SECONDS", "600")),
        high_vol_atr_pct=float(os.getenv("EUR_PULLBACK_HIGH_VOL_ATR_PCT", "0.12")),
    ),
    "GBP": AssetPullbackPolicy(
        key="GBP",
        primary_timeframe=os.getenv("GBP_PULLBACK_PRIMARY_TF", "M15"),
        higher_timeframe=os.getenv("GBP_PULLBACK_HIGHER_TF", "H1"),
        ema_touch_pct=float(os.getenv("GBP_PULLBACK_EMA_TOUCH_PCT", "0.10")),
        max_extension_pct=float(os.getenv("GBP_PULLBACK_MAX_EXTENSION_PCT", "0.15")),
        min_confidence=int(os.getenv("GBP_PULLBACK_MIN_CONFIDENCE", "75")),
        basket_max_positions=int(os.getenv("GBP_BASKET_MAX_POSITIONS", "1")),
        basket_cooldown_seconds=int(os.getenv("GBP_BASKET_COOLDOWN_SECONDS", "600")),
        high_vol_atr_pct=float(os.getenv("GBP_PULLBACK_HIGH_VOL_ATR_PCT", "0.14")),
    ),
    "JPY": AssetPullbackPolicy(
        key="JPY",
        primary_timeframe=os.getenv("JPY_PULLBACK_PRIMARY_TF", "H1"),
        higher_timeframe=os.getenv("JPY_PULLBACK_HIGHER_TF", "H4"),
        ema_touch_pct=float(os.getenv("JPY_PULLBACK_EMA_TOUCH_PCT", "0.12")),
        max_extension_pct=float(os.getenv("JPY_PULLBACK_MAX_EXTENSION_PCT", "0.18")),
        min_confidence=int(os.getenv("JPY_PULLBACK_MIN_CONFIDENCE", "75")),
        basket_max_positions=int(os.getenv("JPY_BASKET_MAX_POSITIONS", "1")),
        basket_cooldown_seconds=int(os.getenv("JPY_BASKET_COOLDOWN_SECONDS", "600")),
        high_vol_atr_pct=float(os.getenv("JPY_PULLBACK_HIGH_VOL_ATR_PCT", "0.16")),
    ),
    "NZD": AssetPullbackPolicy(
        key="NZD",
        primary_timeframe=os.getenv("NZD_PULLBACK_PRIMARY_TF", "H1"),
        higher_timeframe=os.getenv("NZD_PULLBACK_HIGHER_TF", "H4"),
        ema_touch_pct=float(os.getenv("NZD_PULLBACK_EMA_TOUCH_PCT", "0.10")),
        max_extension_pct=float(os.getenv("NZD_PULLBACK_MAX_EXTENSION_PCT", "0.14")),
        min_confidence=int(os.getenv("NZD_PULLBACK_MIN_CONFIDENCE", "78")),
        basket_max_positions=int(os.getenv("NZD_BASKET_MAX_POSITIONS", "1")),
        basket_cooldown_seconds=int(os.getenv("NZD_BASKET_COOLDOWN_SECONDS", "900")),
        high_vol_atr_pct=float(os.getenv("NZD_PULLBACK_HIGH_VOL_ATR_PCT", "0.12")),
    ),
}


@dataclass
class PullbackDecision:
    allowed: bool
    reason: str
    confidence: int = 0
    action: str = "HOLD"
    primary_trend: str = ""
    higher_trend: str = ""
    regime: str = ""
    volatility: str = "normal"
    atr_pct: float = 0.0
    policy_key: str = ""
    basket_max_positions: int = 1
    basket_cooldown_seconds: int = 900


def _symbol_key(symbol: str) -> str:
    upper = str(symbol or "").upper()
    if "XAU" in upper or "GOLD" in upper:
        return "XAU"
    if upper.startswith("EUR"):
        return "EUR"
    if upper.startswith("GBP"):
        return "GBP"
    if "JPY" in upper:
        return "JPY"
    if upper.startswith("NZD"):
        return "NZD"
    if upper.startswith("AUD"):
        return "AUD"
    return "DEFAULT"


def _policy_for(symbol: str) -> Optional[AssetPullbackPolicy]:
    key = _symbol_key(symbol)
    if key == "AUD":
        return None
    return POLICIES.get(key, DEFAULT_POLICY)


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


def _atr_pct(candles: List[Dict[str, Any]], period: int = 14) -> float:
    if len(candles) < period + 1:
        return 0.0
    ranges = []
    closes = []
    for candle in candles:
        high = _float(candle.get("high"))
        low = _float(candle.get("low"))
        close = _float(candle.get("close"))
        if None in (high, low, close):
            continue
        ranges.append(max(float(high) - float(low), 0.0))
        closes.append(float(close))
    if len(ranges) < period or not closes or closes[-1] == 0:
        return 0.0
    atr = sum(ranges[-period:]) / period
    return atr / closes[-1] * 100.0


def _trend(candles: List[Dict[str, Any]]) -> str:
    closes = [_float(c.get("close")) for c in candles]
    closes = [c for c in closes if c is not None]
    if len(closes) < PULLBACK_MIN_CANDLES:
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


def _rejection(candle: Dict[str, Any], trend: str, ema20: float) -> bool:
    latest_open = _float(candle.get("open"))
    latest_high = _float(candle.get("high"))
    latest_low = _float(candle.get("low"))
    latest_close = _float(candle.get("close"))
    if None in (latest_open, latest_high, latest_low, latest_close):
        return False

    latest_open = float(latest_open)
    latest_high = float(latest_high)
    latest_low = float(latest_low)
    latest_close = float(latest_close)
    candle_range = max(latest_high - latest_low, 0.0)
    body = abs(latest_open - latest_close)

    if trend == "down":
        upper_wick = latest_high - max(latest_open, latest_close)
        return latest_close < latest_open and (
            latest_close <= ema20
            or (body > 0 and upper_wick >= body * 0.6)
            or (candle_range > 0 and upper_wick / candle_range >= 0.35)
        )
    if trend == "up":
        lower_wick = min(latest_open, latest_close) - latest_low
        return latest_close > latest_open and (
            latest_close >= ema20
            or (body > 0 and lower_wick >= body * 0.6)
            or (candle_range > 0 and lower_wick / candle_range >= 0.35)
        )
    return False


class XauPullbackShortFilter:
    """Dynamic pullback/rejection entry filter for XAU and selected FX assets.

    The class name is kept for compatibility with the existing manager/UI wiring.
    """

    def __init__(self, enabled: bool = PULLBACK_ENTRY_ENABLED, cache_seconds: int = PULLBACK_CACHE_SECONDS):
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

    def supports(self, symbol: str) -> bool:
        return self.enabled and _policy_for(symbol) is not None

    async def evaluate(self, mt5: Any, symbol: str, price: float) -> PullbackDecision:
        policy = _policy_for(symbol)
        if not self.enabled or policy is None:
            return PullbackDecision(True, "Pullback filter inactive", policy_key=_symbol_key(symbol))
        try:
            primary = await self._candles(mt5, symbol, policy.primary_timeframe)
            higher = await self._candles(mt5, symbol, policy.higher_timeframe)
        except Exception as exc:
            decision = PullbackDecision(False, f"Pullback data unavailable: {exc}", policy_key=policy.key)
            self._record(symbol, decision)
            return decision

        decision = self._evaluate_candles(symbol, primary, higher, price, policy=policy)
        self._record(symbol, decision)
        return decision

    def _evaluate_candles(
        self,
        symbol: str,
        primary: List[Dict[str, Any]],
        higher: List[Dict[str, Any]],
        price: float,
        policy: Optional[AssetPullbackPolicy] = None,
    ) -> PullbackDecision:
        policy = policy or _policy_for(symbol) or DEFAULT_POLICY
        primary_trend = _trend(primary)
        higher_trend = _trend(higher)
        atr_pct = _atr_pct(primary)
        volatility = "high" if atr_pct >= policy.high_vol_atr_pct else "normal"
        if primary_trend not in ("up", "down") or primary_trend != higher_trend:
            return PullbackDecision(
                False,
                (
                    f"{policy.key} pullback waits for trend alignment "
                    f"{policy.primary_timeframe}:{primary_trend} {policy.higher_timeframe}:{higher_trend}"
                ),
                primary_trend=primary_trend,
                higher_trend=higher_trend,
                regime=primary_trend if primary_trend == higher_trend else "mixed",
                volatility=volatility,
                atr_pct=round(atr_pct, 4),
                policy_key=policy.key,
            )

        closes = [_float(c.get("close")) for c in primary]
        closes = [c for c in closes if c is not None]
        if len(closes) < PULLBACK_MIN_CANDLES or not primary:
            return PullbackDecision(False, "Pullback insufficient candles", primary_trend=primary_trend, higher_trend=higher_trend, policy_key=policy.key)

        ema20 = _ema(closes, 20)
        if ema20 is None:
            return PullbackDecision(False, "Pullback incomplete EMA data", primary_trend=primary_trend, higher_trend=higher_trend, policy_key=policy.key)

        latest = primary[-1]
        latest_high = _float(latest.get("high"))
        latest_low = _float(latest.get("low"))
        if None in (latest_high, latest_low):
            return PullbackDecision(False, "Pullback incomplete candle data", primary_trend=primary_trend, higher_trend=higher_trend, policy_key=policy.key)

        ema20_value = float(ema20)
        price = float(price or closes[-1])
        latest_high = float(latest_high)
        latest_low = float(latest_low)

        touch_price = latest_high if primary_trend == "down" else latest_low
        touch_pct = abs(touch_price - ema20_value) / ema20_value * 100.0
        if primary_trend == "down":
            close_extension_pct = max((ema20_value - price) / ema20_value * 100.0, 0.0)
            action = "SHORT"
        else:
            close_extension_pct = max((price - ema20_value) / ema20_value * 100.0, 0.0)
            action = "LONG"

        max_extension = policy.max_extension_pct * (0.75 if volatility == "high" else 1.0)
        if touch_pct > policy.ema_touch_pct:
            return PullbackDecision(
                False,
                f"{policy.key} pullback not near EMA20 touch={touch_pct:.2f}% > {policy.ema_touch_pct:.2f}%",
                primary_trend=primary_trend,
                higher_trend=higher_trend,
                regime=primary_trend,
                volatility=volatility,
                atr_pct=round(atr_pct, 4),
                policy_key=policy.key,
            )
        if close_extension_pct > max_extension:
            return PullbackDecision(
                False,
                f"{policy.key} pullback avoids chasing extension={close_extension_pct:.2f}% > {max_extension:.2f}%",
                primary_trend=primary_trend,
                higher_trend=higher_trend,
                regime=primary_trend,
                volatility=volatility,
                atr_pct=round(atr_pct, 4),
                policy_key=policy.key,
            )
        if not _rejection(latest, primary_trend, ema20_value):
            return PullbackDecision(
                False,
                f"{policy.key} pullback waiting for {'bullish' if primary_trend == 'up' else 'bearish'} rejection",
                primary_trend=primary_trend,
                higher_trend=higher_trend,
                regime=primary_trend,
                volatility=volatility,
                atr_pct=round(atr_pct, 4),
                policy_key=policy.key,
            )

        confidence = policy.min_confidence
        if close_extension_pct <= max_extension / 2:
            confidence += 3
        if volatility == "high":
            confidence += HIGH_VOL_CONFIDENCE_BONUS
        basket_max = max(1, policy.basket_max_positions)
        if volatility == "high":
            basket_max = min(basket_max, max(1, HIGH_VOL_BASKET_MAX))

        return PullbackDecision(
            True,
            (
                f"{policy.key} pullback {action.lower()}: {policy.primary_timeframe}/{policy.higher_timeframe} "
                f"{primary_trend}, EMA20 touch={touch_pct:.2f}%, extension={close_extension_pct:.2f}%, "
                f"atr={atr_pct:.2f}% {volatility}"
            ),
            confidence=min(95, confidence),
            action=action,
            primary_trend=primary_trend,
            higher_trend=higher_trend,
            regime=primary_trend,
            volatility=volatility,
            atr_pct=round(atr_pct, 4),
            policy_key=policy.key,
            basket_max_positions=basket_max,
            basket_cooldown_seconds=max(0, policy.basket_cooldown_seconds),
        )

    def _record(self, symbol: str, decision: PullbackDecision):
        self._last_summary[symbol] = {
            "allowed": decision.allowed,
            "reason": decision.reason,
            "confidence": decision.confidence,
            "action": decision.action,
            "primary_trend": decision.primary_trend,
            "higher_trend": decision.higher_trend,
            "regime": decision.regime,
            "volatility": decision.volatility,
            "atr_pct": decision.atr_pct,
            "policy_key": decision.policy_key,
            "basket_max_positions": decision.basket_max_positions,
            "basket_cooldown_seconds": decision.basket_cooldown_seconds,
            "updated_at": time.time(),
        }

    def summary(self) -> Dict[str, Any]:
        policies = {key: policy.__dict__ for key, policy in POLICIES.items()}
        policies["DEFAULT"] = DEFAULT_POLICY.__dict__
        return {
            "enabled": self.enabled,
            "mode": "dynamic_pullback_entry",
            "policies": policies,
            "latest": dict(self._last_summary),
        }
