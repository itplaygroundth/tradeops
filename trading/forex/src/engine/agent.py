"""
Forex Trading Agent — holds DNA, generates signals based on weighted strategies,
and keeps track of agent trading stats and state.
"""
import logging
import random
import time
from typing import Optional

from engine.dna import ForexAgentDNA
from engine.signals import ForexSignalEngine
from engine.risk_guardian import ForexRiskGuardian, RiskResult

logger = logging.getLogger("agent")

class ForexAgent:
    def __init__(
        self,
        dna: ForexAgentDNA,
        signal_engine: ForexSignalEngine,
        risk_guardian: ForexRiskGuardian,
        paper_mode: bool = True,
    ):
        self.dna = dna
        self.signal_engine = signal_engine
        self.risk_guardian = risk_guardian
        self.paper_mode = paper_mode

        # Performance tracking
        self.trades_count = 0
        self.wins = 0
        self.losses = 0
        self.total_pnl = 0.0
        self.total_pnl_pct = 0.0
        self.gross_profit = 0.0
        self.gross_loss = 0.0
        self.max_dd_pct = 0.0
        self._peak_pnl = 0.0

        # State
        self._open_ticket: Optional[int] = None  # MT5 ticket ID
        self._open_entry: float = 0.0
        self._open_side: str = ""
        self._open_sl: float = 0.0
        self._open_tp: float = 0.0
        self._open_risk_amount: float = 0.0
        self._consecutive_losses = 0

    @property
    def win_rate(self) -> float:
        if self.trades_count == 0:
            return 0.0
        return self.wins / self.trades_count

    @property
    def expectancy_pct(self) -> float:
        if self.trades_count == 0:
            return 0.0
        return self.total_pnl_pct / self.trades_count

    @property
    def is_in_trade(self) -> bool:
        return self._open_ticket is not None

    def generate_signal(self, price: float) -> dict:
        """Generates signal for the agent's assigned symbol."""
        symbol = self.dna.symbol

        # Dominant strategy
        dominant = max(self.dna.strategy_weights, key=lambda k: self.dna.strategy_weights[k])

        if dominant == "momentum":
            return self.signal_engine.technical_signal(symbol)
        elif dominant == "mean_reversion":
            # Invert momentum signal for mean reversion
            tech = self.signal_engine.technical_signal(symbol)
            if tech["action"] == "LONG":
                tech["action"] = "SHORT"
                tech["reason"] = "MR: " + tech["reason"]
            elif tech["action"] == "SHORT":
                tech["action"] = "LONG"
                tech["reason"] = "MR: " + tech["reason"]
            return tech
        elif dominant == "grid_scalp":
            return self._grid_signal(symbol, price)
        elif dominant == "order_flow":
            return self.signal_engine.order_flow_signal(symbol)
        elif dominant == "breakout_atr":
            return self.signal_engine.breakout_atr_signal(symbol)
        elif dominant == "session_open":
            return self.signal_engine.session_open_signal(symbol)
        elif dominant == "market_structure":
            return self.signal_engine.market_structure_signal(symbol)
        else:
            return self.signal_engine.technical_signal(symbol)

    def _grid_signal(self, symbol: str, price: float) -> dict:
        hist = self.signal_engine.get_history(symbol)
        sma20 = hist.sma(20)
        if not sma20:
            return {"action": "HOLD", "confidence": 0, "reason": "Grid: no SMA20"}
        vwap_dev = hist.vwap_deviation()
        deviation = vwap_dev if vwap_dev is not None else ((price - sma20) / sma20) * 100
        spacing = 0.08  # 0.08% threshold
        if deviation > spacing:
            return {"action": "SHORT", "confidence": 55, "reason": f"Grid: {deviation:.2f}% above mean"}
        elif deviation < -spacing:
            return {"action": "LONG", "confidence": 55, "reason": f"Grid: {abs(deviation):.2f}% below mean"}
        return {"action": "HOLD", "confidence": 25, "reason": f"Grid: {deviation:+.2f}%"}

    def record_trade_result(self, pnl: float, pnl_pct: float):
        """Called when a position for this agent is closed."""
        self.trades_count += 1
        self.total_pnl += pnl
        self.total_pnl_pct += pnl_pct
        if pnl > 0:
            self.wins += 1
            self.gross_profit += pnl
            self._consecutive_losses = 0
        else:
            self.losses += 1
            self.gross_loss += abs(pnl)
            self._consecutive_losses += 1
        self._peak_pnl = max(self._peak_pnl, self.total_pnl)
        peak_equity = self._initial_equity() + self._peak_pnl
        equity = self._initial_equity() + self.total_pnl
        if peak_equity > 0:
            dd_pct = (peak_equity - equity) / peak_equity * 100
            self.max_dd_pct = max(self.max_dd_pct, dd_pct)

    def update_strategy_weights(self, weights: dict):
        """Apply a winning strategy-weight config (from AssetLeader competition).

        Keeps only known strategies, drops non-positive/invalid values, and
        normalizes to sum 1.0. No-op if nothing valid remains.
        """
        from engine.dna import STRATEGY_METHODS
        clean = {
            k: float(v)
            for k, v in (weights or {}).items()
            if k in STRATEGY_METHODS and isinstance(v, (int, float)) and v > 0
        }
        total = sum(clean.values())
        if total <= 0:
            logger.warning(f"Agent {self.dna.id}: ignoring empty/invalid weights {weights}")
            return
        self.dna.strategy_weights = {k: v / total for k, v in clean.items()}
        logger.info(f"Agent {self.dna.id} ({self.dna.symbol}) weights updated -> {self.dna.strategy_weights}")

    def to_dict(self) -> dict:
        return {
            "id": self.dna.id,
            "name": self.dna.name,
            "symbol": self.dna.symbol,
            "strategy": max(self.dna.strategy_weights, key=lambda k: self.dna.strategy_weights[k]),
            "trades": self.trades_count,
            "win_rate": round(self.win_rate * 100, 1),
            "total_pnl": round(self.total_pnl, 2),
            "total_pnl_pct": round(self.total_pnl_pct, 2),
            "pnl_pct": round(self.total_pnl_pct, 2),
            "equity": round(self._initial_equity() + self.total_pnl, 2),
            "consecutive_losses": self._consecutive_losses,
            "max_dd_pct": round(self.max_dd_pct, 2),
            "expectancy_pct": round(self.expectancy_pct, 4),
            "gross_profit": round(self.gross_profit, 2),
            "gross_loss": round(self.gross_loss, 2),
            "in_trade": self.is_in_trade,
            "timeframe": self.dna.timeframe,
            "sl_pips": self.dna.sl_pips,
            "tp_pips": self.dna.tp_pips,
            "strategy_weights": self.dna.strategy_weights,
        }

    def _initial_equity(self) -> float:
        return 1000.0
