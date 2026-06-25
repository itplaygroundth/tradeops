"""
Forex Signal Engine — generates signals (LONG/SHORT/HOLD) using technical indicators
and LLM sentiment, adjusted for Forex trading sessions.
"""
import asyncio
import json
import logging
import statistics
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional
import aiohttp

from engine.price_history import PriceHistory

logger = logging.getLogger("signals")

BCPROXY_URL = "http://192.168.1.166:3333/v1/chat/completions"

# Forex trading sessions (UTC)
SESSIONS = {
    "ASIA":   (0, 8),    # 00:00-08:00 UTC — JPY, AUD, NZD active
    "LONDON": (7, 16),   # 07:00-16:00 UTC — EUR, GBP active
    "NY":     (13, 21),  # 13:00-21:00 UTC — USD, CAD active
}

def get_active_sessions() -> List[str]:
    """Returns a list of currently active sessions based on UTC hour."""
    hour = datetime.now(timezone.utc).hour
    active = []
    
    # 00:00-08:00 UTC - ASIA active
    if 0 <= hour < 8:
        active.append("ASIA")
        
    # 07:00-16:00 UTC - LONDON active
    if 7 <= hour < 16:
        active.append("LONDON")
        
    # 13:00-21:00 UTC - NY active
    if 13 <= hour < 21:
        active.append("NY")
        
    # London and NY overlap (13:00-16:00 UTC)
    if 13 <= hour < 16:
        active.append("OVERLAP")
        
    return active

# Session bias per symbol
SESSION_SYMBOL_AFFINITY = {
    "EURUSDm": ["LONDON", "NY", "OVERLAP"],
    "GBPUSDm": ["LONDON", "NY", "OVERLAP"],
    "USDJPYm": ["ASIA", "NY"],
    "XAUUSDm": ["LONDON", "NY", "OVERLAP"],
    "AUDUSDm": ["ASIA", "LONDON"],
    "USDCADm": ["NY"],
    "USDCHFm": ["LONDON", "OVERLAP"],
    "NZDUSDm": ["ASIA"],
}

def is_good_session(symbol: str) -> bool:
    """Checks if the current session is active and suitable for trading the given symbol."""
    active = get_active_sessions()
    if not active:
        return False
    # Support lookup with/without suffix 'm' and case-insensitive
    keys_to_try = [symbol, symbol.upper(), symbol + "m", symbol.upper() + "m"]
    good_sessions = None
    for k in keys_to_try:
        if k in SESSION_SYMBOL_AFFINITY:
            good_sessions = SESSION_SYMBOL_AFFINITY[k]
            break
    if good_sessions is None:
        good_sessions = ["LONDON", "NY"]
    return any(s in good_sessions for s in active)

class ForexSignalEngine:
    def __init__(self):
        self._histories: Dict[str, PriceHistory] = {}
        self._llm_cache: Dict[str, dict] = {}
        self._llm_timeout_count = 0
        self._llm_lock = asyncio.Lock()
        self._llm_last_retry_time = 0
        self._llm_retry_interval = 300

    def get_history(self, symbol: str) -> PriceHistory:
        if symbol not in self._histories:
            self._histories[symbol] = PriceHistory(maxlen=200)
        return self._histories[symbol]

    def record_tick(self, symbol: str, price: float, volume: float = 0, timestamp: float = 0):
        self.get_history(symbol).add(price, volume, timestamp or time.time())

    def technical_signal(self, symbol: str) -> dict:
        """Technical-only signal (no LLM)."""
        hist = self.get_history(symbol)
        if hist.count < 20:
            return {"action": "HOLD", "confidence": 0, "reason": "Insufficient data"}

        # Session check — don't trade in dead sessions
        if not is_good_session(symbol):
            active_sess = get_active_sessions()
            sess_str = active_sess[0] if active_sess else "CLOSED"
            return {"action": "HOLD", "confidence": 0, "reason": f"Session: {sess_str} (low liquidity)"}

        price = hist.current
        mom = hist.momentum(10) or 0
        rsi_val = hist.rsi(14)
        if rsi_val is None:
            rsi_val = 50.0

        sma5 = hist.sma(5)
        sma20 = hist.sma(20)
        active_sess = get_active_sessions()
        session = active_sess[0] if active_sess else "CLOSED"

        action = "HOLD"
        confidence = 30
        reason = f"Tech: RSI={rsi_val:.0f} Mom={mom:+.2f}% [{session}]"

        # RSI extreme bypass
        if rsi_val < 20:
            action = "LONG"
            confidence = 80
            reason = f"RSI extreme oversold {rsi_val:.0f} [{session}]"
        elif rsi_val > 80:
            action = "SHORT"
            confidence = 80
            reason = f"RSI extreme overbought {rsi_val:.0f} [{session}]"
        elif mom > 0.5 and rsi_val < 65:
            action = "LONG"
            confidence = max(40, min(70, int(25 + abs(mom) * 10)))
            reason = f"Momentum LONG {mom:+.2f}% RSI={rsi_val:.0f}"
        elif mom < -0.5 and rsi_val > 35:
            action = "SHORT"
            confidence = max(40, min(70, int(25 + abs(mom) * 10)))
            reason = f"Momentum SHORT {mom:+.2f}% RSI={rsi_val:.0f}"

        # SMA crossover confirmation
        if sma5 and sma20:
            if sma5 > sma20 and action == "HOLD":
                action = "LONG"
                confidence = 40
                reason = f"SMA5 > SMA20 [{session}]"
            elif sma5 < sma20 and action == "HOLD":
                action = "SHORT"
                confidence = 40
                reason = f"SMA5 < SMA20 [{session}]"

        return {"action": action, "confidence": confidence, "reason": reason}

    async def batch_llm_signal(self, symbols: list) -> dict:
        """Single LLM call for all symbols using Forex context."""
        cache_key = f"batch_{int(time.time() / 30)}"
        if cache_key in self._llm_cache:
            return self._llm_cache[cache_key]

        if self._llm_timeout_count >= 5:
            now_ts = time.time()
            if now_ts - self._llm_last_retry_time < self._llm_retry_interval:
                return self._generate_technical_signals(symbols)
            self._llm_last_retry_time = now_ts

        if self._llm_lock.locked():
            return self._generate_technical_signals(symbols)

        async with self._llm_lock:
            if cache_key in self._llm_cache:
                return self._llm_cache[cache_key]

            active_sess = get_active_sessions()
            session = active_sess[0] if active_sess else "CLOSED"
            symbol_contexts = []
            for sym in symbols:
                hist = self.get_history(sym)
                if hist.count < 10:
                    continue
                price = hist.current
                mom = hist.momentum(10) or 0
                rsi = hist.rsi(14) or 50.0
                regime, _ = hist.market_regime()
                symbol_contexts.append(
                    f"{sym}: {price:.5f} | Mom={mom:+.2f}% | RSI={rsi:.0f} | {regime}"
                )

            if not symbol_contexts:
                return self._generate_technical_signals(symbols)

            prompt = f"""You are a Forex trader. Current session: {session} UTC.

Market snapshot:
{chr(10).join(symbol_contexts)}

For each symbol, give trading signal. Consider:
- Forex session timing (London/NY overlap = highest volume)
- Major news events (NFP, CPI, Fed = avoid or reduce size)
- Trend vs range based on momentum + RSI

Respond ONLY with JSON:
{{"EURUSD": {{"action": "LONG", "confidence": 65, "reason": "momentum break London open"}}, ...}}
Valid actions: LONG, SHORT, HOLD
Confidence: 0-100"""

            try:
                async with aiohttp.ClientSession() as session_http:
                    async with session_http.post(
                        BCPROXY_URL,
                        json={"model": "sml/auto", "messages": [{"role": "user", "content": prompt}], "max_tokens": 300},
                        timeout=aiohttp.ClientTimeout(total=8),
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            content = data["choices"][0]["message"]["content"]
                            # Parse JSON from response
                            start = content.find("{")
                            end = content.rfind("}") + 1
                            signals = json.loads(content[start:end])
                            self._llm_timeout_count = 0
                            self._llm_cache[cache_key] = signals
                            return signals
                        else:
                            logger.warning(f"LLM returned HTTP {resp.status}")
                            self._llm_timeout_count += 1
                            fallback = self._generate_technical_signals(symbols)
                            self._llm_cache[cache_key] = fallback
                            return fallback
            except asyncio.TimeoutError:
                self._llm_timeout_count += 1
                logger.warning(f"LLM request timeout ({self._llm_timeout_count}x)")
                fallback = self._generate_technical_signals(symbols)
                self._llm_cache[cache_key] = fallback
                return fallback
            except Exception as e:
                self._llm_timeout_count += 1
                logger.warning(f"LLM error: {e}")
                fallback = self._generate_technical_signals(symbols)
                self._llm_cache[cache_key] = fallback
                return fallback

    def _generate_technical_signals(self, symbols: list) -> dict:
        return {sym: self.technical_signal(sym) for sym in symbols}

    def order_flow_signal(self, symbol: str) -> dict:
        """Order flow via CVD divergence approximation.

        Uses price changes sign * volume as a proxy for signed volume (CVD).
        Detects divergence between momentum and CVD.
        """
        hist = self.get_history(symbol)
        if hist.count < 10:
            return {"action": "HOLD", "confidence": 0, "reason": "Insufficient data"}

        prices = list(hist.prices)
        vols = list(hist.volumes)
        n = min(len(prices), 30)
        cvd = 0.0
        for i in range(-n + 1, 0):
            prev = prices[i - 1]
            curr = prices[i]
            sign = 1 if curr > prev else (-1 if curr < prev else 0)
            vol = vols[i] if i < len(vols) else 0
            cvd += sign * vol

        mom = hist.momentum(10) or 0.0
        avg_vol = hist.avg_volume(20) or 0.0

        # threshold scales with avg volume
        thresh = max(1.0, avg_vol * 3)

        action = "HOLD"
        confidence = 30
        reason = f"OrderFlow: CVD={cvd:.1f} Mom={mom:+.2f}%"

        # divergence: price up (mom>0) but CVD strongly negative => bearish divergence
        if mom > 0.5 and cvd < -thresh:
            action = "SHORT"
            confidence = 60
            reason = "CVD bearish divergence"
        elif mom < -0.5 and cvd > thresh:
            action = "LONG"
            confidence = 60
            reason = "CVD bullish divergence"

        return {"action": action, "confidence": confidence, "reason": reason}

    def mean_reversion_signal(self, symbol: str, regime: str = None) -> dict:
        """Conservative mean-reversion using Bollinger/VWAP deviation plus RSI."""
        if regime not in (None, "RANGING", "SIDEWAYS"):
            return {"action": "HOLD", "confidence": 0, "reason": f"MR skipped: regime={regime} (not ranging)"}
        hist = self.get_history(symbol)
        if hist.count < 55:
            return {"action": "HOLD", "confidence": 0, "reason": "MR insufficient data"}
        prices = list(hist.prices)
        price = hist.current
        if price is None:
            return {"action": "HOLD", "confidence": 0, "reason": "MR no price"}
        recent20 = prices[-20:]
        mean20 = sum(recent20) / 20
        std20 = statistics.pstdev(recent20)
        sma50 = hist.sma(50) or mean20
        rsi_val = hist.rsi(14) or 50.0
        vwap_dev = hist.vwap_deviation()
        if vwap_dev is None:
            vwap_dev = ((price - mean20) / mean20) * 100 if mean20 else 0.0
        mom20 = hist.momentum(20) or 0.0
        atr_pct = hist.atr_percent(14) or 0.0
        trend_slope_pct = abs((mean20 - sma50) / price * 100) if price else 0.0
        if trend_slope_pct > 0.25 or abs(mom20) > 0.60:
            return {"action": "HOLD", "confidence": 0, "reason": f"MR blocked strong trend slope={trend_slope_pct:.3f}% mom20={mom20:+.2f}%"}
        lower = mean20 - 2.0 * std20
        upper = mean20 + 2.0 * std20
        min_extension = max(0.05, atr_pct * 0.35)
        previous = prices[-2]
        extended_down = price <= lower or vwap_dev <= -min_extension
        extended_up = price >= upper or vwap_dev >= min_extension
        if extended_down and rsi_val <= 38 and price > previous:
            confidence = min(82, 58 + min(20, int(abs(vwap_dev) * 120)))
            return {"action": "LONG", "confidence": confidence, "reason": f"MR LONG: below mean and reverting RSI={rsi_val:.0f} dev={vwap_dev:+.3f}%"}
        if extended_up and rsi_val >= 62 and price < previous:
            confidence = min(82, 58 + min(20, int(abs(vwap_dev) * 120)))
            return {"action": "SHORT", "confidence": confidence, "reason": f"MR SHORT: above mean and reverting RSI={rsi_val:.0f} dev={vwap_dev:+.3f}%"}
        return {"action": "HOLD", "confidence": 30, "reason": f"MR: price={price:.5f} mean={mean20:.5f} dev={vwap_dev:+.3f}% RSI={rsi_val:.0f}"}

    def breakout_atr_signal(self, symbol: str) -> dict:
        """Breakout filtered by ATR: confirm breakout then require ATR low to avoid false breakouts."""
        hist = self.get_history(symbol)
        if hist.count < 30:
            return {"action": "HOLD", "confidence": 0, "reason": "Insufficient data"}

        sr = hist.support_resistance(20)
        price = hist.current
        if price is None:
            return {"action": "HOLD", "confidence": 0, "reason": "No price"}

        atr_pct = hist.atr_percent(14) or 0.0
        action = "HOLD"
        confidence = 30
        reason = f"Breakout: price={price:.5f} R={sr['resistance']} S={sr['support']} ATR%={atr_pct:.3f}"

        # require ATR percent to be moderate (not too high) to reduce false breakouts
        if sr.get("resistance") and price > sr["resistance"] and atr_pct < 0.6:
            action = "LONG"
            confidence = min(80, max(40, int(sr["room_to_resistance_pct"] + 40)))
            reason = "Breakout above resistance with ATR filter"
        elif sr.get("support") and price < sr["support"] and atr_pct < 0.6:
            action = "SHORT"
            confidence = min(80, max(40, int(sr["room_to_support_pct"] + 40)))
            reason = "Breakout below support with ATR filter"

        return {"action": action, "confidence": confidence, "reason": reason}

    def session_open_signal(self, symbol: str) -> dict:
        """Signal that focuses on session open momentum (first 30 minutes).

        For London/NY opens, if symbol affinity matches, use short horizon momentum.
        """
        now = datetime.now(timezone.utc)
        hour = now.hour
        minute = now.minute
        hist = self.get_history(symbol)
        if hist.count < 6:
            return {"action": "HOLD", "confidence": 0, "reason": "Insufficient data"}

        # detect London open (07:00-07:30) and NY open (13:00-13:30)
        session = None
        if hour == 7 and minute < 30:
            session = "LONDON"
        elif hour == 13 and minute < 30:
            session = "NY"

        if session is None:
            return {"action": "HOLD", "confidence": 0, "reason": "Not session open"}

        good = SESSION_SYMBOL_AFFINITY.get(symbol, [])
        if session not in good and "OVERLAP" not in good:
            return {"action": "HOLD", "confidence": 0, "reason": f"Session {session} not relevant for {symbol}"}

        mom = hist.momentum(3) or 0.0
        action = "HOLD"
        confidence = 30
        reason = f"SessionOpen {session} Mom={mom:+.2f}%"
        if mom > 0.2:
            action = "LONG"
            confidence = 60
        elif mom < -0.2:
            action = "SHORT"
            confidence = 60

        return {"action": action, "confidence": confidence, "reason": reason}

    def market_structure_signal(self, symbol: str) -> dict:
        """Detect Break of Structure (BoS) using IT trend and support/resistance structure."""
        hist = self.get_history(symbol)
        if hist.count < 10:
            return {"action": "HOLD", "confidence": 0, "reason": "Insufficient data"}

        it = hist.it_trend()
        price = hist.current
        sr = hist.support_resistance(30)
        action = "HOLD"
        confidence = 35
        reason = f"MS: IT={it} R={sr.get('resistance')} S={sr.get('support')}"

        if it == "up" and price and sr.get("resistance") and price > sr.get("resistance"):
            action = "LONG"
            confidence = 60
            reason = "Break of Structure bullish"
        elif it == "down" and price and sr.get("support") and price < sr.get("support"):
            action = "SHORT"
            confidence = 60
            reason = "Break of Structure bearish"

        return {"action": action, "confidence": confidence, "reason": reason}
