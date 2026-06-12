# Phase 2: Signal Engine (Forex)

> **Objective:** Port algorithm จาก ai-trading-live ให้ทำงานกับ Forex symbols  
> เมื่อเสร็จ: ระบบ generate signal LONG/SHORT/HOLD สำหรับ EURUSD, XAUUSD ฯลฯ ได้

**Source:** `/home/alfred/Siam-Synapse/ai-trading-live/engine/signals.py`  
**Target:** `/home/alfred/mtai/src/engine/signals.py`

---

## Algorithm Reuse Analysis

| Algorithm | ใช้ได้ทันที | ต้องแก้ | หมายเหตุ |
|-----------|------------|---------|---------|
| `PriceHistory` (OHLCV indicators) | ✅ 100% | ไม่ต้อง | RSI, SMA, EMA, VWAP ทำงานเหมือนกัน |
| `mean_reversion` | ✅ 100% | ไม่ต้อง | RSI-based — universal |
| `grid_scalp` | ✅ 100% | ไม่ต้อง | VWAP/SMA deviation — universal |
| `lstm_momentum` | ✅ 100% | ไม่ต้อง | % momentum — universal |
| `llm_sentiment` | ⚠️ 80% | แก้ prompt | เปลี่ยน context จาก crypto → forex |
| `polymarket_macro` | ❌ 0% | เขียนใหม่ | แทนด้วย economic calendar |
| Regime detector | ✅ 90% | minor | เพิ่ม session detection |

---

## Task 2.1: Copy + Adapt PriceHistory

**Objective:** Copy `PriceHistory` class จาก ai-trading-live (ไม่ต้องแก้)

**Files:**
- Create: `src/engine/__init__.py`
- Create: `src/engine/price_history.py`

**Step 1: Copy price_history (จาก signals.py บรรทัด 42-270)**

```bash
# Copy จาก source แล้วแยกเป็นไฟล์ตัวเอง
cp /home/alfred/Siam-Synapse/ai-trading-live/engine/signals.py /tmp/signals_source.py
```

**Step 2: สร้าง price_history.py** (paste จาก source — class `PriceHistory` ทั้งหมด)

ไม่ต้องแก้อะไร — class นี้ pure math, ไม่มี exchange dependency ใดๆ

**Verify:**
```python
from engine.price_history import PriceHistory
h = PriceHistory()
for p in [1.0850, 1.0855, 1.0848, 1.0862, 1.0870]:
    h.add(p, volume=1000)
print("RSI:", h.rsi(14))      # None (ต้องการ 15+ bars)
print("SMA5:", h.sma(5))      # 1.0857
print("Mom:", h.momentum(4))  # ~+0.23%
```

---

## Task 2.2: Forex Signal Engine

**Objective:** สร้าง `SignalEngine` สำหรับ Forex  
**แก้จากต้นฉบับ:** ลบ Polymarket import, เพิ่ม forex-aware LLM prompt

**Files:**
- Create: `src/engine/signals.py`

```python
"""
Signal Engine — Forex version
ดัดแปลงจาก ai-trading-live/engine/signals.py

เปลี่ยน:
1. ลบ Polymarket import (ไม่มี forex markets บน Polymarket)
2. เพิ่ม forex session awareness (Asia/London/NY)
3. LLM prompt บอก context เป็น forex
4. คง PriceHistory + technical indicators ทั้งหมด (ไม่แก้)
"""
import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Dict, Optional

import aiohttp

from engine.price_history import PriceHistory

logger = logging.getLogger("signals")

BCPROXY_URL = "http://192.168.1.166:3333/v1/chat/completions"

# Forex trading sessions (UTC)
SESSIONS = {
    "ASIA":   (0, 8),    # 00:00-08:00 UTC — JPY, AUD, NZD active
    "LONDON": (7, 16),   # 07:00-16:00 UTC — EUR, GBP active
    "NY":     (13, 21),  # 13:00-21:00 UTC — USD, CAD active
    "OVERLAP":(13, 16),  # London+NY overlap — highest volume
}

def get_current_session() -> str:
    hour = datetime.now(timezone.utc).hour
    if 13 <= hour < 16:
        return "OVERLAP"
    elif 7 <= hour < 16:
        return "LONDON"
    elif 13 <= hour < 21:
        return "NY"
    elif 0 <= hour < 8:
        return "ASIA"
    return "CLOSED"  # 21:00-00:00 UTC — low liquidity

# Session bias ต่อ symbol
SESSION_SYMBOL_AFFINITY = {
    "EURUSD": ["LONDON", "NY", "OVERLAP"],
    "GBPUSD": ["LONDON", "NY", "OVERLAP"],
    "USDJPY": ["ASIA", "NY"],
    "XAUUSD": ["LONDON", "NY", "OVERLAP"],
    "AUDUSD": ["ASIA", "LONDON"],
    "USDCAD": ["NY"],
    "USDCHF": ["LONDON", "OVERLAP"],
    "NZDUSD": ["ASIA"],
}

def is_good_session(symbol: str) -> bool:
    """ตรวจว่า session ปัจจุบัน active สำหรับ symbol นี้มั้ย"""
    current = get_current_session()
    if current == "CLOSED":
        return False
    good_sessions = SESSION_SYMBOL_AFFINITY.get(symbol, ["LONDON", "NY"])
    return current in good_sessions


class ForexSignalEngine:
    """
    Signal engine สำหรับ Forex
    Interface เหมือน SignalEngine ใน ai-trading-live แต่ forex-aware
    """

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
        """Technical-only signal (no LLM) — identical logic to ai-trading-live"""
        hist = self.get_history(symbol)
        if hist.count < 20:
            return {"action": "HOLD", "confidence": 0, "reason": "Insufficient data"}

        # Session check — don't trade in dead sessions
        if not is_good_session(symbol):
            return {"action": "HOLD", "confidence": 0, "reason": f"Session: {get_current_session()} (low liquidity)"}

        price = hist.current
        mom = hist.momentum(10) or 0
        rsi_val = hist.rsi(14)
        if rsi_val is None:
            rsi_val = 50.0

        sma5 = hist.sma(5)
        sma20 = hist.sma(20)
        regime, _ = hist.market_regime()
        session = get_current_session()

        action = "HOLD"
        confidence = 30
        reason = f"Tech: RSI={rsi_val:.0f} Mom={mom:+.2f}% [{session}]"

        # RSI extreme bypass (same as source)
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
        """
        Single LLM call สำหรับทุก symbols (เหมือน ai-trading-live)
        เปลี่ยน: prompt บอก context เป็น Forex ไม่ใช่ crypto
        """
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

            session = get_current_session()
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
                        data = await resp.json()
                        content = data["choices"][0]["message"]["content"]
                        # Parse JSON from response
                        start = content.find("{")
                        end = content.rfind("}") + 1
                        signals = json.loads(content[start:end])
                        self._llm_timeout_count = 0
                        self._llm_cache[cache_key] = signals
                        return signals
            except asyncio.TimeoutError:
                self._llm_timeout_count += 1
                fallback = self._generate_technical_signals(symbols)
                self._llm_cache[cache_key] = fallback
                return fallback
            except Exception as e:
                logger.warning(f"LLM error: {e}")
                fallback = self._generate_technical_signals(symbols)
                self._llm_cache[cache_key] = fallback
                return fallback

    def _generate_technical_signals(self, symbols: list) -> dict:
        return {sym: self.technical_signal(sym) for sym in symbols}
```

---

## Task 2.3: Forex Macro Signal (แทน Polymarket)

**Objective:** Economic calendar-based macro signal แทน Polymarket

**Files:**
- Create: `src/engine/forex_macro.py`

```python
"""
Forex Macro Signal — แทน polymarket_macro ใน ai-trading-live

Sources:
1. Economic calendar (ForexFactory / investing.com API)
2. Manual high-impact event detection
3. Session-based bias
"""
import time
from datetime import datetime, timezone
from typing import Optional

# High-impact events ที่มีผลต่อ USD (กระทบทุก pair)
HIGH_IMPACT_USD_EVENTS = [
    "Non-Farm Payrolls", "NFP",
    "CPI", "Core CPI",
    "Federal Funds Rate", "FOMC",
    "GDP", "Unemployment",
    "Retail Sales",
    "ISM Manufacturing",
]

class ForexMacroSignal:
    """
    Macro signal สำหรับ Forex
    
    Phase 1: Rule-based (ไม่ต้อง API)
    Phase 2: Connect to economic calendar API
    """

    def __init__(self):
        self._cache = {}
        self._cache_time = 0
        self._cache_ttl = 300  # 5 minutes

    def get_bias(self, symbol: str) -> dict:
        """
        Return macro bias สำหรับ symbol
        
        Returns:
            {"bias": "BULLISH"|"BEARISH"|"NEUTRAL", "strength": 0-100, "reason": str}
        """
        now = datetime.now(timezone.utc)
        hour = now.hour
        weekday = now.weekday()  # 0=Mon, 4=Fri, 5=Sat, 6=Sun

        # Weekend — no trading
        if weekday >= 5:
            return {"bias": "NEUTRAL", "strength": 0, "reason": "Weekend — market closed"}

        # Friday after 20:00 UTC — reduce activity
        if weekday == 4 and hour >= 20:
            return {"bias": "NEUTRAL", "strength": 20, "reason": "Friday close — reduce exposure"}

        # Monday open gap risk
        if weekday == 0 and hour < 2:
            return {"bias": "NEUTRAL", "strength": 30, "reason": "Monday open — watch for gaps"}

        # Session-based bias per symbol
        if symbol in ("EURUSD", "GBPUSD"):
            if 7 <= hour < 16:  # London session
                return {"bias": "BULLISH" if hour < 12 else "NEUTRAL",
                        "strength": 55, "reason": f"London session open (H={hour})"}
        elif symbol == "USDJPY":
            if 0 <= hour < 8:  # Asia session
                return {"bias": "NEUTRAL", "strength": 50, "reason": "Asia session — JPY active"}
        elif symbol == "XAUUSD":
            if 13 <= hour < 16:  # London+NY overlap
                return {"bias": "BULLISH", "strength": 60, "reason": "Gold: London+NY overlap — highest volume"}

        return {"bias": "NEUTRAL", "strength": 40, "reason": f"Normal session (H={hour})"}

    def should_avoid_trading(self, symbol: str) -> tuple[bool, str]:
        """
        ตรวจว่าควร avoid trading ตอนนี้มั้ย (เช่น ก่อน NFP)
        Returns: (should_avoid: bool, reason: str)
        
        TODO Phase 2: เชื่อม economic calendar API จริง
        """
        now = datetime.now(timezone.utc)
        # First Friday of month 12:30 UTC = NFP release
        if now.weekday() == 4 and now.day <= 7 and now.hour == 12 and now.minute >= 25:
            return True, "NFP release imminent — avoid USD pairs"

        return False, ""
```

---

## Task 2.4: Integration Test

```python
# tests/test_signals.py
import asyncio
import time
from engine.signals import ForexSignalEngine

def test_technical_signal():
    engine = ForexSignalEngine()
    
    # Feed 50 bars of EURUSD-like data
    base = 1.0850
    for i in range(50):
        price = base + (i % 10 - 5) * 0.0001
        engine.record_tick("EURUSD", price, volume=1000, timestamp=time.time() + i)
    
    signal = engine.technical_signal("EURUSD")
    assert signal["action"] in ("LONG", "SHORT", "HOLD")
    assert 0 <= signal["confidence"] <= 100
    assert "reason" in signal
    print(f"EURUSD signal: {signal}")

def test_session_filter():
    engine = ForexSignalEngine()
    # Feed minimal data
    for i in range(5):
        engine.record_tick("NZDUSD", 0.6100, timestamp=time.time() + i)
    
    # NZDUSD only good in ASIA — in London session will be HOLD
    signal = engine.technical_signal("NZDUSD")
    print(f"NZDUSD: {signal}")  # Likely HOLD if not in ASIA session

test_technical_signal()
test_session_filter()
```

---

## Phase 2 Checklist

- [ ] `PriceHistory` copied + tested (RSI, SMA, momentum ทำงานถูกต้อง)
- [ ] `ForexSignalEngine.technical_signal()` return signal ถูกรูปแบบ
- [ ] Session filter ทำงาน (NZDUSD ไม่ trade ใน London session)
- [ ] LLM signal ใช้ forex context prompt
- [ ] Macro signal return `NEUTRAL` ช่วง weekend
- [ ] Batch LLM timeout fallback ไปใช้ technical signal

---

## Pitfalls

1. **Spread กินกำไร scalp** — EURUSD 0.1pip spread × 100,000 = $1/trade minimum cost → ต้องตั้ง TP ≥ 10 pips (ไม่ใช่ 2-3 pip แบบ crypto)
2. **Session mismatch** — XAUUSD ในช่วง Asia session มี spread กว้างมาก → block signal
3. **Volume ใน Forex ≠ crypto volume** — tick volume จาก MT5 ไม่ใช่ dollar volume → อย่าใช้ volume filter เหมือน crypto
4. **pip decimal ต่างกัน** — USDJPY pip = 0.01, ไม่ใช่ 0.0001 → ต้องใช้ `pip_calc.py` เสมอ
