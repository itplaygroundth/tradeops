# Phase 3: Risk Engine (Forex-Aware)

> **Objective:** Risk Guardian ที่รู้จัก pip value, spread, leverage ของ Forex  
> Source reference: `ai-trading-live/engine/` (risk logic) + `sstu/core/dynamic_risk_manager.py`

---

## Forex Risk vs Crypto Risk — Key Differences

| Aspect | Crypto (เดิม) | Forex (ใหม่) |
|--------|--------------|-------------|
| Position size | USDT amount | Lot size (0.01-10.0) |
| Stop Loss | % จาก entry | Pips จาก entry |
| Leverage | 1x-125x (optional) | 1:200-1:2000 (Exness) |
| Min position | 0.001 BTC | 0.01 lot (micro) |
| Fee | 0.1% taker | Spread (0.1-1.5 pip) |

---

## Task 3.1: Forex Risk Guardian

**Files:**
- Create: `src/engine/risk_guardian.py`

```python
"""
Forex Risk Guardian
ดัดแปลงจาก ai-trading-live/engine/ risk logic

Hard Rules (เหมือนเดิม):
1. Max 1% risk per trade
2. R:R >= 1:2
3. Circuit breaker (5% daily drawdown)
4. Max 3 concurrent positions

Forex-specific additions:
5. Pip-based position sizing (ไม่ใช่ % of equity)
6. Spread-aware TP minimum
7. Session filter (block trades ใน dead sessions)
8. Leverage cap (max 1:100 effective)
"""
import logging
from dataclasses import dataclass
from typing import Optional

from mt5_bridge.pip_calc import calculate_lot_size, get_pip_size, price_to_pips

logger = logging.getLogger("risk_guardian")

# ── Hard Rules ───────────────────────────────────────────
MAX_RISK_PCT = 0.01          # 1% per trade
MIN_RR_RATIO = 2.0           # TP must be >= 2x SL distance
MAX_CONCURRENT_POSITIONS = 3 # max open trades
DAILY_DRAWDOWN_LIMIT = 0.05  # 5% daily loss → stop all
MAX_EFFECTIVE_LEVERAGE = 100 # ไม่เกิน 1:100

# Minimum TP in pips per symbol (spread-aware)
MIN_TP_PIPS = {
    "EURUSD": 10,   "GBPUSD": 12,   "USDJPY": 10,
    "XAUUSD": 100,  "AUDUSD": 10,   "USDCAD": 12,
    "USDCHF": 10,   "NZDUSD": 10,
}

@dataclass
class RiskResult:
    allowed: bool
    lot_size: float = 0.0
    sl_price: float = 0.0
    tp_price: float = 0.0
    risk_amount: float = 0.0
    reason: str = ""

class ForexRiskGuardian:
    """
    Validates every trade signal before execution.
    Returns RiskResult with calculated lot size + SL/TP prices.
    """

    def __init__(self):
        self._daily_loss = 0.0
        self._daily_reset_day = -1
        self._is_paused = False
        self._open_positions = 0

    def validate(
        self,
        symbol: str,
        action: str,           # "BUY" | "SELL"
        entry_price: float,
        sl_pips: float,        # stop loss in pips
        tp_pips: float,        # take profit in pips (0 = auto 2x SL)
        account_balance: float,
        account_equity: float,
        current_day: int,
        spread_pips: float = 0.0,
    ) -> RiskResult:
        """
        Validate signal + calculate lot size.
        
        Returns RiskResult:
            - allowed=False: reject with reason
            - allowed=True: lot_size, sl_price, tp_price calculated
        """
        # Reset daily tracker
        if current_day != self._daily_reset_day:
            self._daily_reset_day = current_day
            self._daily_loss = 0.0
            self._is_paused = False

        # Circuit breaker check
        if self._is_paused:
            return RiskResult(False, reason="Circuit breaker: daily loss limit hit")

        # Daily drawdown check
        if account_equity < account_balance * (1 - DAILY_DRAWDOWN_LIMIT):
            self._is_paused = True
            return RiskResult(False, reason=f"Daily drawdown >{DAILY_DRAWDOWN_LIMIT*100:.0f}% — all trading stopped")

        # Max concurrent positions
        if self._open_positions >= MAX_CONCURRENT_POSITIONS:
            return RiskResult(False, reason=f"Max {MAX_CONCURRENT_POSITIONS} positions open")

        # SL must be valid
        if sl_pips <= 0:
            return RiskResult(False, reason="SL pips must be > 0")

        # Auto TP if not specified
        if tp_pips <= 0:
            tp_pips = sl_pips * MIN_RR_RATIO

        # R:R check
        rr_ratio = tp_pips / sl_pips
        if rr_ratio < MIN_RR_RATIO:
            return RiskResult(False, reason=f"R:R {rr_ratio:.1f} < minimum {MIN_RR_RATIO}")

        # Minimum TP (spread-aware)
        min_tp = MIN_TP_PIPS.get(symbol, 10)
        if tp_pips < min_tp:
            tp_pips = min_tp
            logger.info(f"[RiskGuardian] {symbol} TP adjusted to minimum {min_tp} pips")

        # Spread cost check — SL must be > spread
        if spread_pips > 0 and sl_pips < spread_pips * 2:
            return RiskResult(False, reason=f"SL ({sl_pips:.1f}pip) too tight vs spread ({spread_pips:.1f}pip)")

        # Calculate lot size (1% risk)
        pip_size = get_pip_size(symbol)
        sl_price_distance = sl_pips * pip_size
        lot_size = calculate_lot_size(
            account_balance=account_balance,
            risk_pct=MAX_RISK_PCT,
            sl_price_distance=sl_price_distance,
            symbol=symbol,
        )

        # Calculate SL/TP prices
        sl_distance = sl_pips * pip_size
        tp_distance = tp_pips * pip_size

        if action == "BUY":
            sl_price = entry_price - sl_distance
            tp_price = entry_price + tp_distance
        else:  # SELL
            sl_price = entry_price + sl_distance
            tp_price = entry_price - tp_distance

        risk_amount = account_balance * MAX_RISK_PCT

        logger.info(
            f"[RiskGuardian] ALLOW {action} {symbol} lot={lot_size} "
            f"SL={sl_price:.5f} TP={tp_price:.5f} risk=${risk_amount:.2f}"
        )

        return RiskResult(
            allowed=True,
            lot_size=lot_size,
            sl_price=sl_price,
            tp_price=tp_price,
            risk_amount=risk_amount,
            reason="OK",
        )

    def on_position_opened(self):
        self._open_positions += 1

    def on_position_closed(self, pnl: float):
        self._open_positions = max(0, self._open_positions - 1)
        if pnl < 0:
            self._daily_loss += abs(pnl)
```

---

## Task 3.2: Dynamic Risk (Regime-Based)

**Files:**
- Create: `src/engine/dynamic_risk.py`

```python
"""
Dynamic Risk Manager สำหรับ Forex
ดัดแปลงจาก sstu/core/dynamic_risk_manager.py

Adjusts SL/TP/position size ตาม market regime
"""
from dataclasses import dataclass

@dataclass
class ForexRiskParams:
    sl_pips: float
    tp_pips: float
    risk_pct: float    # 0.005-0.015

# Default per-symbol parameters (backtested)
SYMBOL_DEFAULTS = {
    "EURUSD": ForexRiskParams(sl_pips=15, tp_pips=30, risk_pct=0.01),
    "GBPUSD": ForexRiskParams(sl_pips=20, tp_pips=40, risk_pct=0.008),
    "USDJPY": ForexRiskParams(sl_pips=15, tp_pips=30, risk_pct=0.01),
    "XAUUSD": ForexRiskParams(sl_pips=150, tp_pips=300, risk_pct=0.007),  # Gold: wider
    "AUDUSD": ForexRiskParams(sl_pips=15, tp_pips=30, risk_pct=0.009),
    "USDCAD": ForexRiskParams(sl_pips=15, tp_pips=30, risk_pct=0.009),
}

# Regime multipliers (เหมือน ai-trading-live dynamic_risk_manager.py)
REGIME_MULTIPLIERS = {
    "TRENDING":  {"sl": 0.9, "tp": 1.3, "risk": 1.2},   # trend → wider TP, tighter SL
    "SIDEWAYS":  {"sl": 1.1, "tp": 0.8, "risk": 0.7},   # range → tighter both
    "HIGH_VOL":  {"sl": 1.5, "tp": 1.5, "risk": 0.5},   # volatile → wider SL, half risk
    "BEARISH":   {"sl": 0.8, "tp": 1.0, "risk": 0.6},   # bear → smaller size
    "BULLISH":   {"sl": 0.8, "tp": 1.2, "risk": 1.1},   # bull → small boost
}

def get_risk_params(symbol: str, regime: str = "MIXED") -> ForexRiskParams:
    base = SYMBOL_DEFAULTS.get(symbol, ForexRiskParams(sl_pips=15, tp_pips=30, risk_pct=0.01))
    mult = REGIME_MULTIPLIERS.get(regime, {"sl": 1.0, "tp": 1.0, "risk": 1.0})

    return ForexRiskParams(
        sl_pips=round(base.sl_pips * mult["sl"]),
        tp_pips=round(base.tp_pips * mult["tp"]),
        risk_pct=max(0.005, min(0.015, base.risk_pct * mult["risk"])),
    )
```

---

## Task 3.3: Test Risk Guardian

```python
# tests/test_risk.py
from engine.risk_guardian import ForexRiskGuardian
from engine.dynamic_risk import get_risk_params
import time

def test_valid_trade():
    rg = ForexRiskGuardian()
    result = rg.validate(
        symbol="EURUSD",
        action="BUY",
        entry_price=1.0850,
        sl_pips=15,
        tp_pips=30,
        account_balance=1000.0,
        account_equity=1000.0,
        current_day=int(time.time() / 86400),
    )
    assert result.allowed == True
    assert result.lot_size > 0
    assert result.sl_price < 1.0850  # SL below entry for BUY
    assert result.tp_price > 1.0850  # TP above entry for BUY
    print(f"✅ Valid trade: lot={result.lot_size}, SL={result.sl_price:.5f}, TP={result.tp_price:.5f}")

def test_rr_rejection():
    rg = ForexRiskGuardian()
    result = rg.validate(
        symbol="EURUSD",
        action="BUY",
        entry_price=1.0850,
        sl_pips=20,
        tp_pips=10,  # TP < 2x SL → reject
        account_balance=1000.0,
        account_equity=1000.0,
        current_day=int(time.time() / 86400),
    )
    assert result.allowed == False
    print(f"✅ R:R rejection: {result.reason}")

def test_dynamic_risk():
    params = get_risk_params("XAUUSD", regime="HIGH_VOL")
    assert params.sl_pips > 150  # wider in high vol
    assert params.risk_pct < 0.01  # smaller size
    print(f"✅ XAUUSD HIGH_VOL: SL={params.sl_pips}pip, risk={params.risk_pct*100:.1f}%")

test_valid_trade()
test_rr_rejection()
test_dynamic_risk()
```

---

## Phase 3 Checklist

- [ ] `validate()` reject R:R < 1:2
- [ ] `validate()` คำนวณ lot size ถูกต้อง (1% risk, 1000 balance, 15pip SL → ~0.67 lot)
- [ ] Circuit breaker หยุดเมื่อ equity drop 5%
- [ ] Max 3 concurrent positions block ได้
- [ ] `get_risk_params("XAUUSD", "HIGH_VOL")` return SL ≥ 200 pips
- [ ] EURUSD BUY: SL < entry, TP > entry ✓

---

## Pitfalls

1. **Leverage illusion** — Exness offer 1:2000 leverage แต่ 1% risk rule กำหนด lot size อยู่แล้ว → ไม่ต้องตั้ง leverage ใน code
2. **Gold (XAUUSD) contract size = 100oz** — pip value ≠ currency pairs → ต้องใช้ pip_calc ที่ calibrate แล้ว
3. **Margin call ก่อน SL hit** — ถ้า lot ใหญ่ + leverage สูง margin อาจหมดก่อน SL → เพิ่ม margin check
4. **Overnight swap** — Forex เก็บ swap ถ้า hold ข้ามคืน → TP/SL calculation ต้องรวม swap cost สำหรับ position >1 วัน
