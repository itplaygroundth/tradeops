"""
Crypto Trading Agent — holds DNA, generates signals from weighted strategies,
and tracks per-agent trading stats and open-position state.
"""
import logging
from typing import Optional

from engine.dna import CryptoAgentDNA
from engine.signals import CryptoSignalEngine
from engine.risk_guardian import CryptoRiskGuardian

logger = logging.getLogger("agent")


class CryptoAgent:
    def __init__(
        self,
        dna: CryptoAgentDNA,
        signal_engine: CryptoSignalEngine,
        risk_guardian: CryptoRiskGuardian,
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

        # Open-position state
        self._open_ticket: Optional[int] = None
        self._open_entry: float = 0.0
        self._open_side: str = ""
        self._open_sl: float = 0.0
        self._open_tp: float = 0.0
        self._open_qty: float = 0.0
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
        """Generates a signal for the agent's assigned symbol via dominant strategy."""
        symbol = self.dna.symbol
        tf = self.dna.timeframe
        dominant = max(self.dna.strategy_weights, key=lambda k: self.dna.strategy_weights[k])

        if dominant == "momentum":
            return self.signal_engine.technical_signal(symbol, tf)
        elif dominant == "mean_reversion":
            # Mean reversion only makes sense in a ranging market. Fading a
            # trending/high-vol move (crypto's norm) bleeds money, so gate on
            # the regime and HOLD when the market is directional.
            regime, _ = self.signal_engine.get_history(symbol, tf).market_regime()
            if regime != "SIDEWAYS":
                return {"action": "HOLD", "confidence": 0,
                        "reason": f"MR skipped: regime={regime} (not ranging)"}
            tech = self.signal_engine.technical_signal(symbol, tf)
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
            return self.signal_engine.order_flow_signal(symbol, tf)
        elif dominant == "breakout_atr":
            return self.signal_engine.breakout_atr_signal(symbol, tf)
        elif dominant == "market_structure":
            return self.signal_engine.market_structure_signal(symbol, tf)
        else:
            return self.signal_engine.technical_signal(symbol, tf)

    def _grid_signal(self, symbol: str, price: float) -> dict:
        hist = self.signal_engine.get_history(symbol, self.dna.timeframe)
        sma20 = hist.sma(20)
        if not sma20:
            return {"action": "HOLD", "confidence": 0, "reason": "Grid: no SMA20"}
        vwap_dev = hist.vwap_deviation()
        deviation = vwap_dev if vwap_dev is not None else ((price - sma20) / sma20) * 100
        spacing = 0.08  # 0.08% threshold
        if deviation > spacing:
            trend_block = self._grid_trend_block(symbol, "SHORT")
            if trend_block:
                return trend_block
            return {"action": "SHORT", "confidence": 55, "reason": f"Grid: {deviation:.2f}% above mean"}
        elif deviation < -spacing:
            trend_block = self._grid_trend_block(symbol, "LONG")
            if trend_block:
                return trend_block
            return {"action": "LONG", "confidence": 55, "reason": f"Grid: {abs(deviation):.2f}% below mean"}
        return {"action": "HOLD", "confidence": 25, "reason": f"Grid: {deviation:+.2f}%"}

    def _grid_trend_block(self, symbol: str, action: str) -> Optional[dict]:
        """Keep grid from fading confirmed directional markets."""
        checks = []
        for tf in (self.dna.timeframe, "H1", "H4"):
            if tf not in checks:
                checks.append(tf)

        trends = []
        for tf in checks:
            trend = self.signal_engine.get_history(symbol, tf).it_trend()
            if trend in ("up", "down"):
                trends.append((tf, trend))

        if action == "LONG":
            blockers = [f"{tf}:{trend}" for tf, trend in trends if trend == "down"]
        else:
            blockers = [f"{tf}:{trend}" for tf, trend in trends if trend == "up"]

        if not blockers:
            return None
        return {
            "action": "HOLD",
            "confidence": 0,
            "reason": f"Grid trend guard: {action} blocked by {', '.join(blockers)}",
        }

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
        peak_equity = 1000.0 + self._peak_pnl
        equity = 1000.0 + self.total_pnl
        if peak_equity > 0:
            dd_pct = (peak_equity - equity) / peak_equity * 100
            self.max_dd_pct = max(self.max_dd_pct, dd_pct)

    def update_strategy_weights(self, weights: dict):
        """Apply a winning strategy-weight config (e.g. from a competition).

        Keeps only known strategies with positive values and normalizes to 1.0.
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
        logger.info(f"Agent {self.dna.id} ({self.dna.symbol}) weights updated")

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
            "equity": round(1000.0 + self.total_pnl, 2),
            "consecutive_losses": self._consecutive_losses,
            "max_dd_pct": round(self.max_dd_pct, 2),
            "expectancy_pct": round(self.expectancy_pct, 4),
            "gross_profit": round(self.gross_profit, 2),
            "gross_loss": round(self.gross_loss, 2),
            "in_trade": self.is_in_trade,
            "timeframe": self.dna.timeframe,
            "sl_pct": self.dna.sl_pct,
            "tp_pct": self.dna.tp_pct,
            "strategy_weights": self.dna.strategy_weights,
        }
