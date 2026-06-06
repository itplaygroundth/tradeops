import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


WEEKEND_REOPEN_GUARD_ENABLED = str(os.getenv("WEEKEND_REOPEN_GUARD_ENABLED", "true")).lower() in ("1", "true", "yes", "on")
WEEKEND_REOPEN_GAP_SECONDS = int(os.getenv("WEEKEND_REOPEN_GAP_SECONDS", "43200"))
WEEKEND_REOPEN_BLOCK_SECONDS = int(os.getenv("WEEKEND_REOPEN_BLOCK_SECONDS", "1800"))
WEEKEND_REOPEN_AUTO_CLOSE = str(os.getenv("WEEKEND_REOPEN_AUTO_CLOSE", "false")).lower() in ("1", "true", "yes", "on")
WEEKEND_REOPEN_STATE_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "weekend_reopen_state.json"

MAX_SPREAD = {
    "XAU": float(os.getenv("WEEKEND_REOPEN_MAX_SPREAD_XAU", "1.50")),
    "JPY": float(os.getenv("WEEKEND_REOPEN_MAX_SPREAD_JPY", "0.050")),
    "FX": float(os.getenv("WEEKEND_REOPEN_MAX_SPREAD_FX", "0.00050")),
}

ADVERSE_GAP = {
    "XAU": float(os.getenv("WEEKEND_REOPEN_ADVERSE_GAP_XAU", "5.00")),
    "JPY": float(os.getenv("WEEKEND_REOPEN_ADVERSE_GAP_JPY", "0.15")),
    "FX": float(os.getenv("WEEKEND_REOPEN_ADVERSE_GAP_FX", "0.0020")),
}


@dataclass
class WeekendReopenDecision:
    status: str = "inactive"
    reason: str = ""
    block_entries_until: float = 0.0
    close_tickets: List[int] = field(default_factory=list)
    spread: Optional[float] = None
    gap: Optional[float] = None
    adverse_gap: Optional[float] = None
    age_seconds: Optional[int] = None

    @property
    def blocks_entries(self) -> bool:
        return self.block_entries_until > time.time()

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "reason": self.reason,
            "block_entries_until": self.block_entries_until,
            "close_tickets": self.close_tickets,
            "spread": self.spread,
            "gap": self.gap,
            "adverse_gap": self.adverse_gap,
            "age_seconds": self.age_seconds,
        }


def symbol_group(symbol: str) -> str:
    value = (symbol or "").upper()
    if "XAU" in value or "GOLD" in value:
        return "XAU"
    if "JPY" in value:
        return "JPY"
    return "FX"


def position_side(position: dict) -> str:
    side = position.get("type")
    if side == 0:
        return "BUY"
    if side == 1:
        return "SELL"
    return str(side or "").upper()


def _normalize_ts(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    try:
        ts = float(value)
    except Exception:
        return None
    if ts > 10_000_000_000:
        return ts / 1000.0
    return ts


class WeekendReopenGuard:
    """Detects post-weekend reopen risk and temporarily blocks new entries.

    The guard stores the last known mid/spread per symbol. When the next tick for
    that symbol arrives after a long quiet window, it compares the new price to
    the stored price, checks spread widening, and decides whether entries should
    pause while liquidity normalizes. Existing positions are only auto-closed
    when WEEKEND_REOPEN_AUTO_CLOSE is explicitly enabled.
    """

    def __init__(
        self,
        state_file: Path = WEEKEND_REOPEN_STATE_FILE,
        enabled: bool = WEEKEND_REOPEN_GUARD_ENABLED,
        gap_seconds: int = WEEKEND_REOPEN_GAP_SECONDS,
        block_seconds: int = WEEKEND_REOPEN_BLOCK_SECONDS,
        auto_close: bool = WEEKEND_REOPEN_AUTO_CLOSE,
    ):
        self.state_file = Path(state_file)
        self.enabled = enabled
        self.gap_seconds = gap_seconds
        self.block_seconds = block_seconds
        self.auto_close = auto_close
        self._state = self._load()
        self._last_summary: Dict[str, Any] = {"enabled": self.enabled, "symbols": {}}

    def _load(self) -> dict:
        try:
            if self.state_file.exists():
                data = json.loads(self.state_file.read_text())
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
        return {"symbols": {}}

    def _save(self) -> None:
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            self.state_file.write_text(json.dumps(self._state, indent=2))
        except Exception:
            pass

    def evaluate_symbol(
        self,
        symbol: str,
        bid: float,
        ask: float,
        positions: List[dict],
        now: Optional[float] = None,
        market_ts: Optional[float] = None,
    ) -> WeekendReopenDecision:
        now = now or time.time()
        market_ts = _normalize_ts(market_ts) or now
        if not self.enabled:
            return WeekendReopenDecision(status="disabled", reason="guard disabled")

        bid = float(bid)
        ask = float(ask)
        mid = (bid + ask) / 2.0
        spread = max(ask - bid, 0.0)
        group = symbol_group(symbol)
        symbols = self._state.setdefault("symbols", {})
        previous = symbols.get(symbol) or {}
        previous_ts = float(previous.get("market_timestamp") or previous.get("timestamp") or 0.0)
        previous_mid = float(previous.get("mid") or 0.0)
        age = int(market_ts - previous_ts) if previous_ts else None
        gap = abs(mid - previous_mid) if previous_mid else None

        decision = WeekendReopenDecision(status="ok", reason="normal", spread=spread, gap=gap, age_seconds=age)
        quiet_reopen = bool(age is not None and age >= self.gap_seconds)
        spread_wide = spread > MAX_SPREAD[group]
        if quiet_reopen or spread_wide:
            reasons = []
            if quiet_reopen:
                reasons.append(f"quiet window {age}s >= {self.gap_seconds}s")
            if spread_wide:
                reasons.append(f"spread {spread:.5f} > {MAX_SPREAD[group]:.5f}")
            decision.status = "guarded"
            decision.reason = "; ".join(reasons)
            decision.block_entries_until = now + self.block_seconds

            adverse_gaps = []
            for position in positions:
                if str(position.get("symbol") or "") != symbol:
                    continue
                side = position_side(position)
                if side == "BUY":
                    adverse = max((float(position.get("price_open") or mid) - bid), 0.0)
                else:
                    adverse = max((ask - float(position.get("price_open") or mid)), 0.0)
                adverse_gaps.append(adverse)
                if self.auto_close and adverse >= ADVERSE_GAP[group] and position.get("ticket"):
                    decision.close_tickets.append(int(position["ticket"]))
            if adverse_gaps:
                decision.adverse_gap = max(adverse_gaps)

        symbols[symbol] = {
            "timestamp": now,
            "market_timestamp": market_ts,
            "bid": bid,
            "ask": ask,
            "mid": mid,
            "spread": spread,
            "block_entries_until": max(
                float(previous.get("block_entries_until") or 0.0),
                decision.block_entries_until,
            ),
            "last_status": decision.status,
            "last_reason": decision.reason,
        }
        self._save()
        self._last_summary = {"enabled": self.enabled, "symbols": symbols}
        return decision

    def blocks_entries(self, symbol: str, now: Optional[float] = None) -> tuple[bool, str]:
        now = now or time.time()
        item = (self._state.get("symbols") or {}).get(symbol) or {}
        until = float(item.get("block_entries_until") or 0.0)
        if until > now:
            return True, f"weekend reopen guard active for {int(until - now)}s: {item.get('last_reason', '')}"
        return False, ""

    def summary(self) -> dict:
        return self._last_summary
