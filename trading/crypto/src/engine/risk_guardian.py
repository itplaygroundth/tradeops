"""
Crypto Risk Guardian — validates orders prior to submission.
Risk is USDT %-based (not pips). Position sizing:
    risk_amount = account_balance * MAX_RISK_PCT
    notional    = risk_amount / sl_pct        (USDT exposure)
    qty         = notional / entry_price       (base-asset units)
Tracks daily loss + open position counts with a daily circuit breaker.
"""
import logging
import os
from dataclasses import dataclass

logger = logging.getLogger("risk_guardian")

# ── Micro-profit mode (env-gated) ─────────────────────────
MICRO_MODE = os.getenv("MICRO_MODE", "").lower() in ("1", "true", "yes")

# ── Hard Rules ───────────────────────────────────────────
MAX_RISK_PCT = 0.01           # 1% of balance risked per trade
MIN_RR_RATIO = float(os.getenv("CRYPTO_MIN_RR_RATIO", "1.15" if MICRO_MODE else "1.3"))
MAX_CONCURRENT_POSITIONS = int(os.getenv("CRYPTO_MAX_CONCURRENT_POSITIONS", "1"))  # max open trades per pair
DAILY_DRAWDOWN_LIMIT = 0.05   # 5% daily loss → stop all
DAILY_REALIZED_LOSS_LIMIT_USDT = 20.0  # fixed daily stop loss in USDT
DAILY_PROFIT_TARGET_USDT = float(os.getenv("CRYPTO_DAILY_PROFIT_TARGET_USDT",
                                           "2.0" if MICRO_MODE else "20.0"))
MIN_SL_PCT = 0.001            # 0.1% floor on stop distance
# Micro-mode: TP must cover round-trip fees
CRYPTO_FEE_PCT = float(os.getenv("CRYPTO_FEE_PCT", "0.001"))
MICRO_TP_FLOOR_PCT = CRYPTO_FEE_PCT * 2  # break-even floor


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
        self._daily_realized_pnl = 0.0
        self._daily_reset_day = -1
        self._is_paused = False
        self._profit_target_hit = False
        self._day_start_balance = 0.0
        # Per-pair open-position counts. The cap is per pair, so one busy
        # symbol must not starve the others.
        self._open_positions: dict[str, int] = {}

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
        # Reset daily tracker on a new day; snapshot the day-start balance so
        # the realized-loss breaker measures against a fixed baseline.
        if current_day != self._daily_reset_day:
            self._daily_reset_day = current_day
            self._daily_loss = 0.0
            self._daily_realized_pnl = 0.0
            self._is_paused = False
            self._profit_target_hit = False
            self._day_start_balance = account_balance

        # Circuit breaker
        if self._is_paused:
            return RiskResult(False, reason="Circuit breaker: daily loss limit hit")

        # Daily profit target: once the day's realized net PnL reaches the
        # target, stop opening new positions. Existing positions are left to
        # their SL/TP management; this is an entry gate, not a forced close.
        if self._profit_target_hit or self._daily_realized_pnl >= DAILY_PROFIT_TARGET_USDT:
            self._profit_target_hit = True
            return RiskResult(False, reason=f"Daily profit target ${DAILY_PROFIT_TARGET_USDT:.2f} reached — entries paused")

        # Realized-loss breaker: halt once the day's closed losses reach the
        # limit. Drives the breaker off _daily_loss (fed by on_position_closed)
        # because production reports equity == balance, leaving the equity
        # check below inert.
        if self._day_start_balance > 0 and self._daily_loss >= self._day_start_balance * DAILY_DRAWDOWN_LIMIT:
            self._is_paused = True
            return RiskResult(False, reason=f"Daily realized loss >={DAILY_DRAWDOWN_LIMIT*100:.0f}% of day-start balance — all trading stopped")

        if self._daily_loss >= DAILY_REALIZED_LOSS_LIMIT_USDT:
            self._is_paused = True
            return RiskResult(False, reason=f"Daily realized loss >= ${DAILY_REALIZED_LOSS_LIMIT_USDT:.2f} — all trading stopped")

        # Daily drawdown (unrealized): fires only when callers report live
        # equity below the balance baseline.
        if account_equity < account_balance * (1 - DAILY_DRAWDOWN_LIMIT):
            self._is_paused = True
            return RiskResult(False, reason=f"Daily drawdown >{DAILY_DRAWDOWN_LIMIT*100:.0f}% — all trading stopped")

        # Max concurrent positions (per pair)
        if self._open_positions.get(symbol, 0) >= MAX_CONCURRENT_POSITIONS:
            return RiskResult(False, reason=f"Max {MAX_CONCURRENT_POSITIONS} positions open on {symbol}")

        # SL must be valid
        if sl_pct < MIN_SL_PCT:
            return RiskResult(False, reason="SL pct must be >= 0.1%")

        if entry_price <= 0:
            return RiskResult(False, reason="Invalid entry price")

        # Auto TP if not specified
        if tp_pct <= 0:
            tp_pct = sl_pct * MIN_RR_RATIO

        # Micro-mode: TP must cover round-trip exchange fees
        if MICRO_MODE and tp_pct < MICRO_TP_FLOOR_PCT:
            tp_pct = MICRO_TP_FLOOR_PCT

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

    def on_position_opened(self, symbol: str):
        self._open_positions[symbol] = self._open_positions.get(symbol, 0) + 1

    def on_position_closed(self, symbol: str, pnl: float):
        self._open_positions[symbol] = max(0, self._open_positions.get(symbol, 0) - 1)
        self._daily_realized_pnl += pnl
        if pnl < 0:
            self._daily_loss += abs(pnl)
