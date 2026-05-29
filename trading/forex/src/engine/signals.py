"""
Forex Signal Engine — generates signals (LONG/SHORT/HOLD) using technical indicators
and LLM sentiment, adjusted for Forex trading sessions.
"""
import asyncio
import json
import logging
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
    good_sessions = SESSION_SYMBOL_AFFINITY.get(symbol, ["LONDON", "NY"])
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
