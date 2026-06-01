"""
Crypto Risk Guardian — validates orders prior to submission.
Risk is USDT %-based (not pips). Position sizing:
    risk_amount = account_balance * MAX_RISK_PCT
    notional    = risk_amount / sl_pct        (USDT exposure)
    qty         = notional / entry_price       (base-asset units)
Tracks daily loss + open position counts with a daily circuit breaker.
"""
import logging
from dataclasses import dataclass

logger = logging.getLogger("risk_guardian")

# ── Hard Rules ───────────────────────────────────────────
MAX_RISK_PCT = 0.01           # 1% of balance risked per trade
MIN_RR_RATIO = 2.0            # TP must be >= 2x SL distance
MAX_CONCURRENT_POSITIONS = 3  # max open trades per pair
DAILY_DRAWDOWN_LIMIT = 0.05   # 5% daily loss → stop all
MIN_SL_PCT = 0.001            # 0.1% floor on stop distance


@dataclass
class RiskResult:
    allowed: bool
    qty: float = 0.0          # base-asset quantity to trade
    notional: float = 0.0     # USDT exposure
    sl_price: float = 0.0
    tp_price: float = 0.0
    risk_amount: float = 0.0  # USDT at risk
    reason: str = ""


class CryptoRiskGuardian:
    def __init__(self):
        self._daily_loss = 0.0
        self._daily_reset_day = -1
        self._is_paused = False
        self._open_positions = 0

    def validate(
        self,
        symbol: str,
        action: str,            # "BUY" | "SELL"
        entry_price: float,
        sl_pct: float,          # stop-loss as price-distance fraction (0.02 = 2%)
        tp_pct: float,          # take-profit fraction (0 = auto MIN_RR x SL)
        account_balance: float,
        account_equity: float,
        current_day: int,
    ) -> RiskResult:
        # Reset daily tracker on a new day
        if current_day != self._daily_reset_day:
            self._daily_reset_day = current_day
            self._daily_loss = 0.0
            self._is_paused = False

        # Circuit breaker
        if self._is_paused:
            return RiskResult(False, reason="Circuit breaker: daily loss limit hit")

        # Daily drawdown
        if account_equity < account_balance * (1 - DAILY_DRAWDOWN_LIMIT):
            self._is_paused = True
            return RiskResult(False, reason=f"Daily drawdown >{DAILY_DRAWDOWN_LIMIT*100:.0f}% — all trading stopped")

        # Max concurrent positions
        if self._open_positions >= MAX_CONCURRENT_POSITIONS:
            return RiskResult(False, reason=f"Max {MAX_CONCURRENT_POSITIONS} positions open")

        # SL must be valid
        if sl_pct < MIN_SL_PCT:
            return RiskResult(False, reason="SL pct must be >= 0.1%")

        if entry_price <= 0:
            return RiskResult(False, reason="Invalid entry price")

        # Auto TP if not specified
        if tp_pct <= 0:
            tp_pct = sl_pct * MIN_RR_RATIO

        # R:R check
        rr_ratio = tp_pct / sl_pct
        if rr_ratio < MIN_RR_RATIO:
            return RiskResult(False, reason=f"R:R {rr_ratio:.1f} < minimum {MIN_RR_RATIO}")

        # Position sizing from price %
        risk_amount = account_balance * MAX_RISK_PCT
        notional = risk_amount / sl_pct
        qty = notional / entry_price

        # SL/TP prices
        if action == "BUY":
            sl_price = entry_price * (1 - sl_pct)
            tp_price = entry_price * (1 + tp_pct)
        else:  # SELL
            sl_price = entry_price * (1 + sl_pct)
            tp_price = entry_price * (1 - tp_pct)

        logger.info(
            f"[RiskGuardian] ALLOW {action} {symbol} qty={qty:.6f} notional={notional:.2f} "
            f"SL={sl_price:.4f} TP={tp_price:.4f} risk=${risk_amount:.2f}"
        )

        return RiskResult(
            allowed=True,
            qty=qty,
            notional=notional,
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
