"""
Dynamic Risk Manager for Forex — regime-based position sizing and target adjustments.
Adapted from Siam-Synapse.
"""
from dataclasses import dataclass

@dataclass
class ForexRiskParams:
    sl_pips: float
    tp_pips: float
    risk_pct: float    # 0.005 - 0.015

# Default per-symbol parameters (backtested)
SYMBOL_DEFAULTS = {
    "EURUSDm": ForexRiskParams(sl_pips=15, tp_pips=30, risk_pct=0.01),
    "GBPUSDm": ForexRiskParams(sl_pips=20, tp_pips=40, risk_pct=0.008),
    "USDJPYm": ForexRiskParams(sl_pips=15, tp_pips=30, risk_pct=0.01),
    "XAUUSDm": ForexRiskParams(sl_pips=150, tp_pips=300, risk_pct=0.007),  # Gold: wider
    "AUDUSDm": ForexRiskParams(sl_pips=15, tp_pips=30, risk_pct=0.009),
    "USDCADm": ForexRiskParams(sl_pips=15, tp_pips=30, risk_pct=0.009),
}

# Regime multipliers (trending, sideways, high-vol, etc.)
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
