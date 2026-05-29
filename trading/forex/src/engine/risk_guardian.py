"""
Forex Risk Guardian — checks and validates orders prior to submission.
Tracks daily loss, open position counts, and dynamically calculates lot sizes.
"""
import logging
from dataclasses import dataclass
from typing import Optional

from mt5_bridge.pip_calc import calculate_lot_size, get_pip_size

logger = logging.getLogger("risk_guardian")

# ── Hard Rules ───────────────────────────────────────────
MAX_RISK_PCT = 0.01          # 1% per trade
MIN_RR_RATIO = 2.0           # TP must be >= 2x SL distance
MAX_CONCURRENT_POSITIONS = 3 # max open trades
DAILY_DRAWDOWN_LIMIT = 0.05  # 5% daily loss → stop all
MAX_EFFECTIVE_LEVERAGE = 100 # effective leverage ceiling 1:100

# Minimum TP in pips per symbol (spread-aware)
MIN_TP_PIPS = {
    "EURUSDm": 10,   "GBPUSDm": 12,   "USDJPYm": 10,
    "XAUUSDm": 100,  "AUDUSDm": 10,   "USDCADm": 12,
    "USDCHFm": 10,   "NZDUSDm": 10,
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
        get_price_func = None,
    ) -> RiskResult:
        """
        Validates signal + calculates lot size.
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
            get_price_func=get_price_func,
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
