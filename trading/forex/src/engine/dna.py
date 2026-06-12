"""
Forex Agent DNA — defines configuration parameters, strategy weights, and TF/session biases.
Each agent DNA is specialized to trade a single symbol.
"""
import random
from dataclasses import dataclass, field
from typing import Dict

FOREX_SYMBOLS = ["EURUSDm", "GBPUSDm", "USDJPYm", "XAUUSDm", "AUDUSDm", "USDCADm", "USDCHFm", "NZDUSDm"]
TIMEFRAMES = ["M15", "H1", "H4"]
SESSIONS = ["LONDON", "NY", "ASIA", "ALL"]

STRATEGY_METHODS = ["momentum", "mean_reversion", "grid_scalp", "llm_sentiment"]

# Symbol-specific defaults (from backtests)
SYMBOL_DEFAULTS = {
    "EURUSDm": {"sl_range": (10, 25), "tp_mult": (1.5, 3.0), "tf_bias": "M15"},
    "GBPUSDm": {"sl_range": (15, 30), "tp_mult": (1.5, 2.5), "tf_bias": "M15"},
    "USDJPYm": {"sl_range": (10, 20), "tp_mult": (1.5, 3.0), "tf_bias": "H1"},
    "XAUUSDm": {"sl_range": (100, 250), "tp_mult": (1.5, 3.0), "tf_bias": "H1"},
    "AUDUSDm": {"sl_range": (10, 20), "tp_mult": (1.5, 2.5), "tf_bias": "H1"},
    "USDCADm": {"sl_range": (10, 20), "tp_mult": (1.5, 2.5), "tf_bias": "H1"},
    "USDCHFm": {"sl_range": (10, 20), "tp_mult": (1.5, 2.5), "tf_bias": "H1"},
    "NZDUSDm": {"sl_range": (10, 20), "tp_mult": (1.5, 2.5), "tf_bias": "H4"},
}

@dataclass
class ForexAgentDNA:
    id: int
    name: str
    symbol: str
    strategy_weights: Dict[str, float] = field(default_factory=dict)
    sl_pips: float = 15.0
    tp_pips: float = 30.0
    risk_pct: float = 0.01
    timeframe: str = "M15"
    session_bias: str = "ALL"
    regime_bias: str = "any"   # "bull"|"bear"|"range"|"any"

def random_dna(agent_id: int, symbol: str = None, regime: str = "MIXED") -> ForexAgentDNA:
    """Generate random DNA for an agent."""
    if symbol is None:
        symbol = random.choice(FOREX_SYMBOLS)

    defaults = SYMBOL_DEFAULTS.get(symbol, SYMBOL_DEFAULTS["EURUSDm"])
    sl_min, sl_max = defaults["sl_range"]
    tp_mult_min, tp_mult_max = defaults["tp_mult"]

    sl_pips = random.uniform(sl_min, sl_max)
    tp_pips = sl_pips * random.uniform(tp_mult_min, tp_mult_max)

    # Strategy weights (sum = 1.0)
    weights = {m: random.random() for m in STRATEGY_METHODS}
    total = sum(weights.values())
    weights = {k: v / total for k, v in weights.items()}

    # Regime-aware bias
    regime_map = {
        "TRENDING": "bull",
        "SIDEWAYS": "range",
        "HIGH_VOL": "range",
        "BEARISH": "bear",
        "BULLISH": "bull",
    }
    regime_bias = regime_map.get(regime, random.choice(["bull", "bear", "range", "any"]))

    return ForexAgentDNA(
        id=agent_id,
        name=f"FX-{symbol[:3]}-{agent_id:03d}",
        symbol=symbol,
        strategy_weights=weights,
        sl_pips=round(sl_pips, 1),
        tp_pips=round(tp_pips, 1),
        risk_pct=round(random.uniform(0.005, 0.012), 3),
        timeframe=random.choice(TIMEFRAMES),
        session_bias=random.choice(SESSIONS),
        regime_bias=regime_bias,
    )

def create_population(count: int = 25) -> list:
    """Creates a population distributed across available Forex symbols."""
    agents = []
    symbols_cycle = FOREX_SYMBOLS * (count // len(FOREX_SYMBOLS) + 1)
    for i in range(count):
        symbol = symbols_cycle[i]
        dna = random_dna(agent_id=i, symbol=symbol)
        agents.append(dna)
    return agents
