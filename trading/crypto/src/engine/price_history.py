"""
PriceHistory class for technical analysis.
Ported directly from Siam-Synapse/ai-trading-live.
"""
import math
from collections import deque
from typing import Tuple, Optional

class PriceHistory:
    """Rolling price history for technical analysis."""

    def __init__(self, maxlen: int = 100, bucket_seconds: int = 0):
        # bucket_seconds == 0 -> legacy raw-tick mode. > 0 -> OHLC candle mode,
        # where ticks aggregate into time buckets and self.prices holds candle
        # CLOSES so the close-based indicators keep working unchanged.
        self.bucket_seconds = bucket_seconds
        self.prices: deque = deque(maxlen=maxlen)   # candle closes (or raw ticks)
        self.volumes: deque = deque(maxlen=maxlen)  # candle volume (or raw tick vol)
        self.timestamps: deque = deque(maxlen=maxlen)
        self.opens: deque = deque(maxlen=maxlen)
        self.highs: deque = deque(maxlen=maxlen)
        self.lows: deque = deque(maxlen=maxlen)
        # aggressor-side volume per candle (true CVD, from the is_buy flag)
        self.buy_vols: deque = deque(maxlen=maxlen)
        self.sell_vols: deque = deque(maxlen=maxlen)
        self._cur_bucket: Optional[int] = None  # bucket index of in-progress candle

    def add(self, price: float, volume: float = 0, timestamp: float = 0, is_buy: bool = True):
        buy = volume if is_buy else 0.0
        sell = 0.0 if is_buy else volume
        if self.bucket_seconds <= 0:
            # legacy raw-tick mode: 1 tick = 1 data point
            self.prices.append(price)
            self.volumes.append(volume)
            self.timestamps.append(timestamp)
            self.opens.append(price)
            self.highs.append(price)
            self.lows.append(price)
            self.buy_vols.append(buy)
            self.sell_vols.append(sell)
            return

        bucket = int(timestamp // self.bucket_seconds)
        if self._cur_bucket is None or bucket > self._cur_bucket:
            # open a new in-progress candle (the previous one is already
            # finalized in the deques — we only ever mutate the tail in place)
            self._cur_bucket = bucket
            self.opens.append(price)
            self.highs.append(price)
            self.lows.append(price)
            self.prices.append(price)
            self.volumes.append(volume)
            self.timestamps.append(timestamp)
            self.buy_vols.append(buy)
            self.sell_vols.append(sell)
        else:
            # same bucket -> update the in-progress candle tail
            self.highs[-1] = max(self.highs[-1], price)
            self.lows[-1] = min(self.lows[-1], price)
            self.prices[-1] = price            # close = last price
            self.volumes[-1] += volume
            self.timestamps[-1] = timestamp
            self.buy_vols[-1] += buy
            self.sell_vols[-1] += sell

    def seed_candle(self, open_: float, high: float, low: float,
                    close: float, volume: float = 0.0, timestamp: float = 0.0,
                    buy_vol: Optional[float] = None, sell_vol: Optional[float] = None):
        """Append a fully-formed historical candle (warmup backfill).

        buy_vol/sell_vol come from kline taker-buy volume when available;
        otherwise the candle volume is split 50/50 (no aggressor info).
        """
        if buy_vol is None or sell_vol is None:
            buy_vol = volume / 2.0
            sell_vol = volume / 2.0
        self.opens.append(open_)
        self.highs.append(high)
        self.lows.append(low)
        self.prices.append(close)
        self.volumes.append(volume)
        self.timestamps.append(timestamp)
        self.buy_vols.append(buy_vol)
        self.sell_vols.append(sell_vol)
        # mark this bucket consumed so the next live tick opens a fresh candle
        if self.bucket_seconds > 0 and timestamp:
            self._cur_bucket = int(timestamp // self.bucket_seconds)

    def cvd(self, n: int = 30) -> float:
        """Cumulative Volume Delta over the last n candles: buy - sell volume."""
        buys = list(self.buy_vols)[-n:]
        sells = list(self.sell_vols)[-n:]
        return sum(buys) - sum(sells)

    @property
    def count(self) -> int:
        return len(self.prices)

    @property
    def current(self) -> Optional[float]:
        return self.prices[-1] if self.prices else None

    def sma(self, period: int) -> Optional[float]:
        """Simple Moving Average."""
        if len(self.prices) < period:
            return None
        return sum(list(self.prices)[-period:]) / period

    def ema(self, period: int) -> Optional[float]:
        """Exponential Moving Average."""
        if len(self.prices) < period:
            return None
        prices = list(self.prices)
        k = 2 / (period + 1)
        ema_val = prices[0]
        for p in prices[1:]:
            ema_val = p * k + ema_val * (1 - k)
        return ema_val

    def momentum(self, period: int = 10) -> Optional[float]:
        """Price momentum as percentage."""
        if len(self.prices) < period:
            return None
        old = list(self.prices)[-period]
        current = self.prices[-1]
        return ((current - old) / old) * 100

    def rsi(self, period: int = 14) -> Optional[float]:
        """Relative Strength Index."""
        if len(self.prices) < period + 1:
            return None
        prices = list(self.prices)
        gains, losses = 0, 0
        for i in range(-period, 0):
            change = prices[i] - prices[i - 1]
            if change > 0:
                gains += change
            else:
                losses += abs(change)
        avg_gain = gains / period
        avg_loss = losses / period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def volatility(self, period: int = 20) -> Optional[float]:
        """Price volatility (standard deviation %)."""
        if len(self.prices) < period:
            return None
        recent = list(self.prices)[-period:]
        mean = sum(recent) / period
        variance = sum((p - mean) ** 2 for p in recent) / period
        return math.sqrt(variance) / mean * 100

    def avg_volume(self, period: int = 20) -> Optional[float]:
        """Average volume over N periods."""
        vols = list(self.volumes)
        if len(vols) < period:
            return None
        return sum(vols[-period:]) / period

    @property
    def latest_volume(self) -> Optional[float]:
        """Most recent volume."""
        return self.volumes[-1] if self.volumes else 0

    def atr_percent(self, period: int = 14) -> Optional[float]:
        """Average True Range as percentage of price."""
        atr = self.atr(period)
        if atr is None:
            return None
        last = self.prices[-1] if self.prices else 0
        return (atr / last) * 100 if last else 0

    def instantaneous_trendline(self, a: float = 0.07) -> Optional[list]:
        """John Ehlers Instantaneous Trendline — DSP-based noise-reduced trend."""
        prices = list(self.prices)
        if len(prices) < 4:
            return None
        it = [0.0] * len(prices)
        for i in range(len(prices)):
            if i < 2:
                it[i] = prices[i]
                continue
            it[i] = (
                (a - (a ** 2) / 4) * prices[i]
                + 0.5 * (a ** 2) * prices[i - 1]
                - (a - 0.75 * (a ** 2)) * prices[i - 2]
                + 2 * (1 - a) * it[i - 1]
                - (1 - a) ** 2 * it[i - 2]
            )
        return it

    def it_trend(self, a: float = 0.07, slope_period: int = 3) -> Optional[str]:
        """IT trend direction: 'up', 'down', or 'flat' based on slope."""
        it = self.instantaneous_trendline(a)
        if it is None or len(it) < slope_period + 2:
            return None
        base = it[-(slope_period + 1)]
        if base == 0:
            return "flat"
        slope_pct = (it[-1] - base) / abs(base) * 100
        if slope_pct > 0.2:
            return "up"
        elif slope_pct < -0.2:
            return "down"
        return "flat"

    def momentum_forecast(self, bars_ahead: int = 3) -> Optional[float]:
        """Linear regression slope projected N bars ahead — % change prediction."""
        prices = list(self.prices)
        n = min(20, len(prices))
        if n < 5:
            return None
        p = prices[-n:]
        mean_x = (n - 1) / 2.0
        mean_y = sum(p) / n
        num = sum((i - mean_x) * (p[i] - mean_y) for i in range(n))
        den = sum((i - mean_x) ** 2 for i in range(n))
        slope = num / den if den else 0
        predicted = p[-1] + slope * bars_ahead
        return ((predicted - p[-1]) / abs(p[-1])) * 100 if p[-1] else 0

    def support_resistance(self, lookback: int = 30) -> dict:
        """Pivot-based support/resistance with room-to-level percentages."""
        prices = list(self.prices)
        n = min(lookback, len(prices))
        if n < 6:
            return {"support": None, "resistance": None,
                    "room_to_resistance_pct": 0.0, "room_to_support_pct": 0.0}
        p = prices[-n:]
        current = p[-1]
        pivots_high, pivots_low = [], []
        for i in range(2, len(p) - 2):
            if p[i] > p[i-1] and p[i] > p[i-2] and p[i] > p[i+1] and p[i] > p[i+2]:
                pivots_high.append(p[i])
            if p[i] < p[i-1] and p[i] < p[i-2] and p[i] < p[i+1] and p[i] < p[i+2]:
                pivots_low.append(p[i])
        resistance = min((ph for ph in pivots_high if ph > current), default=max(p))
        support = max((pl for pl in pivots_low if pl < current), default=min(p))
        return {
            "support": round(support, 4),
            "resistance": round(resistance, 4),
            "room_to_resistance_pct": round((resistance - current) / current * 100, 3) if current else 0,
            "room_to_support_pct": round((current - support) / current * 100, 3) if current else 0,
        }

    def vol_forecast(self, period: int = 10) -> Optional[float]:
        """EWMA volatility forecast — next-period vol estimate (%)."""
        prices = list(self.prices)
        if len(prices) < period + 1:
            return None
        returns = [(prices[i] - prices[i-1]) / prices[i-1]
                   for i in range(max(1, len(prices) - period), len(prices))
                   if prices[i-1] != 0]
        if not returns:
            return None
        lam = 0.94
        ewma_var = returns[0] ** 2
        for r in returns[1:]:
            ewma_var = lam * ewma_var + (1 - lam) * r ** 2
        return math.sqrt(ewma_var) * 100

    def kalman_price(self, q: float = 1e-5, r: float = 0.01) -> Optional[float]:
        """Kalman filter — noise-reduced price estimate."""
        prices = list(self.prices)
        if not prices:
            return None
        x = prices[0]
        p = 1.0
        for z in prices:
            p = p + q
            k = p / (p + r)
            x = x + k * (z - x)
            p = (1 - k) * p
        return x

    def vwap(self) -> Optional[float]:
        """Volume Weighted Average Price."""
        prices = list(self.prices)
        volumes = list(self.volumes)
        total_vol = sum(volumes)
        if not prices or total_vol == 0:
            return None
        return sum(p * v for p, v in zip(prices, volumes)) / total_vol

    def vwap_deviation(self) -> Optional[float]:
        """Current price deviation from VWAP as %."""
        vwap_val = self.vwap()
        price = self.current
        if vwap_val is None or not price or vwap_val == 0:
            return None
        return ((price - vwap_val) / vwap_val) * 100

    def atr(self, period: int = 14) -> Optional[float]:
        """ATR in price units.

        Candle mode: true range = max(high-low, |high-prevClose|, |low-prevClose|).
        Legacy tick mode: approximate range from consecutive tick pairs.
        """
        prices = list(self.prices)
        if len(prices) < period + 1:
            return None
        if self.bucket_seconds > 0:
            highs = list(self.highs)
            lows = list(self.lows)
            tr_sum = 0.0
            for i in range(-period, 0):
                prev_close = prices[i - 1]
                tr = max(
                    highs[i] - lows[i],
                    abs(highs[i] - prev_close),
                    abs(lows[i] - prev_close),
                )
                tr_sum += tr
            return tr_sum / period
        tr_sum = 0.0
        for i in range(-period, 0):
            high = max(prices[i], prices[i - 1])
            low = min(prices[i], prices[i - 1])
            tr_sum += high - low
        return tr_sum / period

    def market_regime(self, atr_period: int = 14, trend_period: int = 20) -> Tuple[str, float]:
        """
        Detect market regime from price action.
        Returns (regime, strength): regime = TRENDING | SIDEWAYS | HIGH_VOL
        """
        prices = list(self.prices)
        if len(prices) < trend_period + 1:
            return ("SIDEWAYS", 0.5)

        atr_val = self.atr(atr_period)
        price = prices[-1]
        atr_pct = (atr_val / price * 100) if (atr_val and price) else 0

        # Linear regression slope over trend_period bars
        p = prices[-trend_period:]
        n = len(p)
        mean_x = (n - 1) / 2.0
        mean_y = sum(p) / n
        num = sum((i - mean_x) * (p[i] - mean_y) for i in range(n))
        den = sum((i - mean_x) ** 2 for i in range(n))
        slope = num / den if den else 0
        slope_pct = abs(slope / mean_y * 100) if mean_y else 0

        if atr_pct > 0.5:
            return ("HIGH_VOL", min(1.0, atr_pct / 2.0))
        elif slope_pct > 0.15:
            return ("TRENDING", min(1.0, slope_pct / 0.5))
        else:
            return ("SIDEWAYS", max(0.3, 1.0 - slope_pct / 0.15))
