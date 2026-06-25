"""
Forex Risk Guardian — checks and validates orders prior to submission.
Tracks daily loss, open position counts, and dynamically calculates lot sizes.
"""
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from mt5_bridge.pip_calc import (
    CENT_ACCOUNT_DIVISOR,
    calculate_lot_size,
    calculate_lot_size_for_profit_target,
    get_contract_size,
    get_pip_size,
    is_cent_currency,
)

logger = logging.getLogger("risk_guardian")

# ── Micro-profit mode (env-gated) ─────────────────────────
MICRO_MODE = os.getenv("MICRO_MODE", "").lower() in ("1", "true", "yes")

# ── Hard Rules ───────────────────────────────────────────
MAX_RISK_PCT = 0.01          # 1% per trade
MIN_RR_RATIO = float(os.getenv("MTAI_MIN_RR_RATIO", "1.2" if MICRO_MODE else "2.0"))
MAX_CONCURRENT_POSITIONS = 3 # max open trades
DAILY_DRAWDOWN_LIMIT = 0.05  # 5% daily loss → stop all
MAX_EFFECTIVE_LEVERAGE = 100 # effective leverage ceiling 1:100
MIN_FREE_MARGIN_AFTER_TRADE_RATIO = float(os.getenv("MIN_FREE_MARGIN_AFTER_TRADE_RATIO", "0.20"))
MAX_MARGIN_USAGE_PER_TRADE_RATIO = float(os.getenv("MAX_MARGIN_USAGE_PER_TRADE_RATIO", "0.50"))
RISK_WARNING_DD = float(os.getenv("RISK_WARNING_DD", "0.03"))
RISK_PAUSE_DD = float(os.getenv("RISK_PAUSE_DD", str(DAILY_DRAWDOWN_LIMIT)))
RISK_HARD_STOP_DD = float(os.getenv("RISK_HARD_STOP_DD", "0.07"))
RISK_MARGIN_HARD_STOP_LEVEL = float(os.getenv("RISK_MARGIN_HARD_STOP_LEVEL", "150"))
MANAGED_MAGIC = int(os.getenv("MTAI_MAGIC", "20260101"))
RISK_STATE_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "risk_state.json"

# Minimum TP in pips per symbol (spread-aware)
_BASE_MIN_TP_PIPS = {
    "EURUSDm": 10,   "GBPUSDm": 12,   "USDJPYm": 10,
    "XAUUSDm": 100,  "AUDUSDm": 10,   "USDCADm": 12,
    "USDCHFm": 10,   "NZDUSDm": 10,
}
_MICRO_TP_SCALE = float(os.getenv("MTAI_MICRO_TP_SCALE", "0.3"))
_MICRO_TP_FLOOR = 2  # pips
if MICRO_MODE:
    MIN_TP_PIPS = {k: max(_MICRO_TP_FLOOR, int(v * _MICRO_TP_SCALE))
                   for k, v in _BASE_MIN_TP_PIPS.items()}
else:
    MIN_TP_PIPS = dict(_BASE_MIN_TP_PIPS)

@dataclass
class RiskResult:
    allowed: bool
    lot_size: float = 0.0
    sl_price: float = 0.0
    tp_price: float = 0.0
    risk_amount: float = 0.0
    reason: str = ""


@dataclass
class AccountRiskState:
    mode: str = "ACTIVE"
    reason: str = ""
    day_start_equity: float = 0.0
    peak_equity: float = 0.0
    equity: float = 0.0
    balance: float = 0.0
    daily_drawdown_pct: float = 0.0
    peak_drawdown_pct: float = 0.0
    floating_pnl: float = 0.0
    open_positions: int = 0
    margin_level_pct: Optional[float] = None
    triggered_at: float = 0.0

    @property
    def blocks_entries(self) -> bool:
        return self.mode in ("PAUSED", "HARD_STOP")

    @property
    def requires_hard_stop(self) -> bool:
        return self.mode == "HARD_STOP"

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "reason": self.reason,
            "day_start_equity": round(self.day_start_equity, 2),
            "peak_equity": round(self.peak_equity, 2),
            "equity": round(self.equity, 2),
            "balance": round(self.balance, 2),
            "daily_drawdown_pct": round(self.daily_drawdown_pct, 3),
            "peak_drawdown_pct": round(self.peak_drawdown_pct, 3),
            "floating_pnl": round(self.floating_pnl, 2),
            "open_positions": self.open_positions,
            "margin_level_pct": None if self.margin_level_pct is None else round(self.margin_level_pct, 1),
            "triggered_at": self.triggered_at,
        }


class AccountRiskMonitor:
    """Persists account-level drawdown state and decides when entries must stop."""

    def __init__(self, state_file: Path = RISK_STATE_FILE, managed_magic: int = MANAGED_MAGIC):
        self.state_file = Path(state_file)
        self.managed_magic = managed_magic
        self._state = {
            "day": -1,
            "day_start_equity": 0.0,
            "peak_equity": 0.0,
            "mode": "ACTIVE",
            "reason": "",
            "triggered_at": 0.0,
        }
        self._load()
        self.current = AccountRiskState()

    def _load(self):
        try:
            if self.state_file.exists():
                import json
                loaded = json.loads(self.state_file.read_text())
                if isinstance(loaded, dict):
                    self._state.update(loaded)
        except Exception as e:
            logger.warning(f"[AccountRisk] Failed to load state: {e}")

    def _save(self):
        try:
            import json
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            self.state_file.write_text(json.dumps(self._state, indent=2))
        except Exception as e:
            logger.warning(f"[AccountRisk] Failed to save state: {e}")

    def reset(self, equity: float = 0.0, current_day: int = -1):
        """Manual/test reset for a hard stop."""
        self._state.update({
            "day": current_day,
            "day_start_equity": float(equity or 0.0),
            "peak_equity": float(equity or 0.0),
            "mode": "ACTIVE",
            "reason": "",
            "triggered_at": 0.0,
        })
        self._save()
        self.current = AccountRiskState(day_start_equity=float(equity or 0.0), peak_equity=float(equity or 0.0))

    def _is_managed_position(self, position: dict) -> bool:
        try:
            return int(position.get("magic") or 0) == self.managed_magic
        except Exception:
            return False

    def evaluate(self, account: dict, positions: list, current_day: int, now: float) -> AccountRiskState:
        balance = float(account.get("balance") or 0.0)
        equity = float(account.get("equity") or balance or 0.0)
        margin = float(account.get("margin") or 0.0)
        margin_level = (equity / margin * 100.0) if margin > 0 else None
        managed_positions = [p for p in positions if self._is_managed_position(p)]
        floating_pnl = sum(float(p.get("profit") or 0.0) for p in managed_positions)

        if current_day != int(self._state.get("day", -1)):
            self._state["day"] = current_day
            self._state["day_start_equity"] = equity
            self._state["peak_equity"] = equity
            if self._state.get("mode") != "HARD_STOP":
                self._state["mode"] = "ACTIVE"
                self._state["reason"] = ""
                self._state["triggered_at"] = 0.0

        day_start = float(self._state.get("day_start_equity") or equity or 0.0)
        peak = max(float(self._state.get("peak_equity") or equity or 0.0), equity)
        self._state["peak_equity"] = peak

        daily_dd = max((day_start - equity) / day_start, 0.0) if day_start > 0 else 0.0
        peak_dd = max((peak - equity) / peak, 0.0) if peak > 0 else 0.0
        current_mode = str(self._state.get("mode") or "ACTIVE")
        mode = current_mode if current_mode == "HARD_STOP" else "ACTIVE"
        reason = str(self._state.get("reason") or "")

        if mode != "HARD_STOP":
            worst_dd = max(daily_dd, peak_dd)
            if worst_dd >= RISK_HARD_STOP_DD:
                mode = "HARD_STOP"
                reason = f"Drawdown {worst_dd * 100:.1f}% >= hard stop {RISK_HARD_STOP_DD * 100:.1f}%"
            elif margin_level is not None and margin_level <= RISK_MARGIN_HARD_STOP_LEVEL:
                mode = "HARD_STOP"
                reason = f"Margin level {margin_level:.1f}% <= hard stop {RISK_MARGIN_HARD_STOP_LEVEL:.0f}%"
            elif worst_dd >= RISK_PAUSE_DD:
                mode = "PAUSED"
                reason = f"Drawdown {worst_dd * 100:.1f}% >= pause {RISK_PAUSE_DD * 100:.1f}%"
            elif worst_dd >= RISK_WARNING_DD:
                mode = "WARNING"
                reason = f"Drawdown {worst_dd * 100:.1f}% >= warning {RISK_WARNING_DD * 100:.1f}%"
            else:
                reason = ""

        if mode != self._state.get("mode"):
            logger.warning(f"[AccountRisk] Mode changed {self._state.get('mode')} -> {mode}: {reason}")
            self._state["triggered_at"] = now if mode in ("PAUSED", "HARD_STOP") else 0.0

        self._state["mode"] = mode
        self._state["reason"] = reason
        self._save()

        self.current = AccountRiskState(
            mode=mode,
            reason=reason,
            day_start_equity=day_start,
            peak_equity=peak,
            equity=equity,
            balance=balance,
            daily_drawdown_pct=daily_dd * 100.0,
            peak_drawdown_pct=peak_dd * 100.0,
            floating_pnl=floating_pnl,
            open_positions=len(managed_positions),
            margin_level_pct=margin_level,
            triggered_at=float(self._state.get("triggered_at") or 0.0),
        )
        return self.current


class ForexRiskGuardian:
    def __init__(self):
        self._daily_loss = 0.0
        self._daily_reset_day = -1
        self._is_paused = False
        self._open_positions = 0
        self._external_risk_scale = 1.0
        self._external_max_positions = MAX_CONCURRENT_POSITIONS
        self._external_mode = "NORMAL"

    def set_external_policy(self, mode: str, risk_scale: float, max_positions: int):
        self._external_mode = str(mode or "NORMAL").upper()
        self._external_risk_scale = max(0.0, min(1.0, float(risk_scale)))
        self._external_max_positions = max(0, min(MAX_CONCURRENT_POSITIONS, int(max_positions)))
        return self.external_policy()

    def external_policy(self):
        return {
            "mode": self._external_mode,
            "risk_scale": self._external_risk_scale,
            "max_positions": self._external_max_positions,
        }

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
        account_currency: str = None,
        open_positions: Optional[int] = None,
        account_margin_free: Optional[float] = None,
        account_leverage: Optional[float] = None,
        target_profit_remaining: Optional[float] = None,
        risk_multiplier: float = 1.0,
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
        effective_open_positions = self._open_positions if open_positions is None else int(open_positions)
        if self._external_risk_scale <= 0 or self._external_max_positions <= 0:
            return RiskResult(False, reason=f"MADS defensive policy {self._external_mode}: entries stopped")
        if effective_open_positions >= self._external_max_positions:
            return RiskResult(False, reason=f"Max {self._external_max_positions} positions open")

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

        pip_size = get_pip_size(symbol)
        sl_price_distance = sl_pips * pip_size
        tp_price_distance = tp_pips * pip_size

        # Calculate lot size (1% risk), then cap it to the remaining daily
        # profit target so a TP aims to finish near the configured daily goal.
        risk_lot_size = calculate_lot_size(
            account_balance=account_balance,
            risk_pct=MAX_RISK_PCT,
            sl_price_distance=sl_price_distance,
            symbol=symbol,
            get_price_func=get_price_func,
            account_currency=account_currency,
        )
        lot_size = risk_lot_size
        if target_profit_remaining is not None and target_profit_remaining > 0:
            target_lot_size = calculate_lot_size_for_profit_target(
                target_profit_usd=float(target_profit_remaining),
                tp_price_distance=tp_price_distance,
                symbol=symbol,
                get_price_func=get_price_func,
                account_currency=account_currency,
            )
            lot_size = min(risk_lot_size, target_lot_size)
            logger.info(
                f"[RiskGuardian] {symbol} target lot sizing: remaining=${target_profit_remaining:.2f} "
                f"target_lot={target_lot_size:.2f} risk_lot={risk_lot_size:.2f} final_lot={lot_size:.2f}"
            )
        risk_multiplier = max(
            0.0,
            min(1.0, float(risk_multiplier or 0.0) * self._external_risk_scale),
        )
        if risk_multiplier <= 0:
            return RiskResult(False, reason="Adaptive guard hard stop")
        if risk_multiplier < 1.0:
            original_lot = lot_size
            lot_size = max(0.01, round(lot_size * risk_multiplier, 2))
            logger.info(
                f"[RiskGuardian] adaptive lot multiplier={risk_multiplier:.2f} "
                f"lot {original_lot:.2f}->{lot_size:.2f}"
            )

        if account_margin_free is not None and account_leverage:
            required_margin = self._estimate_required_margin(
                symbol=symbol,
                lot_size=lot_size,
                entry_price=entry_price,
                account_leverage=float(account_leverage),
                account_currency=account_currency,
            )
            free_margin = float(account_margin_free)
            equity = float(account_equity or 0.0)
            min_free_after_trade = max(equity * MIN_FREE_MARGIN_AFTER_TRADE_RATIO, 0.0)
            max_margin_for_trade = max(free_margin * MAX_MARGIN_USAGE_PER_TRADE_RATIO, 0.0)
            if required_margin > max_margin_for_trade:
                return RiskResult(
                    False,
                    lot_size=lot_size,
                    risk_amount=account_balance * MAX_RISK_PCT,
                    reason=(
                        f"Required margin {required_margin:.2f} exceeds per-trade limit "
                        f"{max_margin_for_trade:.2f}"
                    ),
                )
            if free_margin - required_margin < min_free_after_trade:
                return RiskResult(
                    False,
                    lot_size=lot_size,
                    risk_amount=account_balance * MAX_RISK_PCT,
                    reason=(
                        f"Free margin after trade {free_margin - required_margin:.2f} "
                        f"< reserve {min_free_after_trade:.2f}"
                    ),
                )

        # Calculate SL/TP prices
        sl_distance = sl_price_distance
        tp_distance = tp_price_distance

        if action == "BUY":
            sl_price = entry_price - sl_distance
            tp_price = entry_price + tp_distance
        else:  # SELL
            sl_price = entry_price + sl_distance
            tp_price = entry_price - tp_distance

        risk_amount = min(account_balance * MAX_RISK_PCT, sl_distance * get_contract_size(symbol) * lot_size)

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

    @staticmethod
    def _estimate_required_margin(
        symbol: str,
        lot_size: float,
        entry_price: float,
        account_leverage: float,
        account_currency: Optional[str] = None,
    ) -> float:
        if account_leverage <= 0 or lot_size <= 0 or entry_price <= 0:
            return 0.0

        contract_size = get_contract_size(symbol)
        notional_usd = lot_size * contract_size * entry_price
        required_margin_usd = notional_usd / account_leverage
        if is_cent_currency(account_currency):
            return required_margin_usd * CENT_ACCOUNT_DIVISOR
        return required_margin_usd

    def on_position_opened(self):
        self._open_positions += 1

    def on_position_closed(self, pnl: float):
        self._open_positions = max(0, self._open_positions - 1)
        if pnl < 0:
            self._daily_loss += abs(pnl)

    def set_open_positions(self, count: int):
        self._open_positions = max(0, int(count or 0))
