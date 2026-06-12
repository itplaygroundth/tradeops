"""
Crypto Signal Engine — generates signals (LONG/SHORT/HOLD) using technical indicators
and (optionally) LLM sentiment. Crypto trades 24/7, so there is NO session filter.
"""
import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Dict, List
import aiohttp

from engine.price_history import PriceHistory
from engine.dna import TIMEFRAMES, TF_SECONDS

logger = logging.getLogger("signals")

DEFAULT_TIMEFRAME = "M15"

BCPROXY_URL = os.environ.get("BCPROXY_URL", "http://192.168.1.166:3333/v1/chat/completions")


class CryptoSignalEngine:
    def __init__(self):
        self._histories: Dict[str, PriceHistory] = {}
        self._llm_cache: Dict[str, dict] = {}
        self._llm_timeout_count = 0
        self._llm_lock = asyncio.Lock()
        self._llm_last_retry_time = 0
        self._llm_retry_interval = 300

    def get_history(self, symbol: str, timeframe: str = DEFAULT_TIMEFRAME) -> PriceHistory:
        key = (symbol, timeframe)
        if key not in self._histories:
            self._histories[key] = PriceHistory(
                maxlen=200, bucket_seconds=TF_SECONDS.get(timeframe, 900)
            )
        return self._histories[key]

    def record_tick(self, symbol: str, price: float, volume: float = 0,
                    timestamp: float = 0, is_buy: bool = True):
        ts = timestamp or time.time()
        # fan the tick into every timeframe bucket so any agent timeframe is ready
        for tf in TIMEFRAMES:
            self.get_history(symbol, tf).add(price, volume, ts, is_buy)

    def technical_signal(self, symbol: str, timeframe: str = DEFAULT_TIMEFRAME) -> dict:
        """Technical-only signal (no LLM, no session filter — crypto is 24/7)."""
        hist = self.get_history(symbol, timeframe)
        if hist.count < 20:
            return {"action": "HOLD", "confidence": 0, "reason": "Insufficient data"}

        mom = hist.momentum(10) or 0
        rsi_val = hist.rsi(14)
        if rsi_val is None:
            rsi_val = 50.0

        sma5 = hist.sma(5)
        sma20 = hist.sma(20)
        trend = hist.it_trend()  # 'up' | 'down' | 'flat' | None

        action = "HOLD"
        confidence = 30
        reason = f"Tech: RSI={rsi_val:.0f} Mom={mom:+.2f}%"

        # RSI extreme bypass — but never counter-trade a CONFIRMED trend.
        # Crypto RSI stays extended for hours; fading it bleeds money.
        if rsi_val < 20 and trend != "down":
            action = "LONG"
            confidence = 80
            reason = f"RSI extreme oversold {rsi_val:.0f}"
        elif rsi_val > 80 and trend != "up":
            action = "SHORT"
            confidence = 80
            reason = f"RSI extreme overbought {rsi_val:.0f}"
        elif rsi_val < 20 or rsi_val > 80:
            # extreme RSI but the trend confirms it -> stand aside, don't fade
            reason = f"RSI {rsi_val:.0f} extreme but trend={trend} confirms; HOLD"
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
                reason = "SMA5 > SMA20"
            elif sma5 < sma20 and action == "HOLD":
                action = "SHORT"
                confidence = 40
                reason = "SMA5 < SMA20"

        return {"action": action, "confidence": confidence, "reason": reason}

    async def batch_llm_signal(self, symbols: list) -> dict:
        """Single LLM call for all symbols using crypto context."""
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

            symbol_contexts = []
            for sym in symbols:
                hist = self.get_history(sym, DEFAULT_TIMEFRAME)
                if hist.count < 10:
                    continue
                price = hist.current
                mom = hist.momentum(10) or 0
                rsi = hist.rsi(14) or 50.0
                regime, _ = hist.market_regime()
                symbol_contexts.append(
                    f"{sym}: {price:.4f} | Mom={mom:+.2f}% | RSI={rsi:.0f} | {regime}"
                )

            if not symbol_contexts:
                return self._generate_technical_signals(symbols)

            prompt = f"""You are a crypto trader. Markets run 24/7.

Market snapshot:
{chr(10).join(symbol_contexts)}

For each symbol, give a trading signal. Consider:
- Trend vs range based on momentum + RSI
- Volatility regime (HIGH_VOL = reduce conviction)

Respond ONLY with JSON:
{{"BTCUSDT": {{"action": "LONG", "confidence": 65, "reason": "momentum breakout"}}, ...}}
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
        return {sym: self.technical_signal(sym, DEFAULT_TIMEFRAME) for sym in symbols}

    def order_flow_signal(self, symbol: str, timeframe: str = DEFAULT_TIMEFRAME) -> dict:
        """Order flow via CVD divergence approximation."""
        hist = self.get_history(symbol, timeframe)
        if hist.count < 10:
            return {"action": "HOLD", "confidence": 0, "reason": "Insufficient data"}

        # CVD from the true aggressor side (is_buy flag), not price-direction proxy
        cvd = hist.cvd(30)

        mom = hist.momentum(10) or 0.0
        avg_vol = hist.avg_volume(20) or 0.0
        thresh = max(1.0, avg_vol * 3)

        action = "HOLD"
        confidence = 30
        reason = f"OrderFlow: CVD={cvd:.1f} Mom={mom:+.2f}%"

        if mom > 0.5 and cvd < -thresh:
            action = "SHORT"
            confidence = 60
            reason = "CVD bearish divergence"
        elif mom < -0.5 and cvd > thresh:
            action = "LONG"
            confidence = 60
            reason = "CVD bullish divergence"

        return {"action": action, "confidence": confidence, "reason": reason}

    def breakout_atr_signal(self, symbol: str, timeframe: str = DEFAULT_TIMEFRAME) -> dict:
        """Breakout filtered by ATR to avoid false breakouts."""
        hist = self.get_history(symbol, timeframe)
        if hist.count < 30:
            return {"action": "HOLD", "confidence": 0, "reason": "Insufficient data"}

        sr = hist.support_resistance(20)
        price = hist.current
        if price is None:
            return {"action": "HOLD", "confidence": 0, "reason": "No price"}

        atr_pct = hist.atr_percent(14) or 0.0
        action = "HOLD"
        confidence = 30
        reason = f"Breakout: price={price:.4f} R={sr['resistance']} S={sr['support']} ATR%={atr_pct:.3f}"

        if sr.get("resistance") and price > sr["resistance"] and atr_pct < 0.6:
            action = "LONG"
            confidence = min(80, max(40, int(sr["room_to_resistance_pct"] + 40)))
            reason = "Breakout above resistance with ATR filter"
        elif sr.get("support") and price < sr["support"] and atr_pct < 0.6:
            action = "SHORT"
            confidence = min(80, max(40, int(sr["room_to_support_pct"] + 40)))
            reason = "Breakout below support with ATR filter"

        return {"action": action, "confidence": confidence, "reason": reason}

    def market_structure_signal(self, symbol: str, timeframe: str = DEFAULT_TIMEFRAME) -> dict:
        """Detect Break of Structure (BoS) using IT trend and support/resistance."""
        hist = self.get_history(symbol, timeframe)
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
