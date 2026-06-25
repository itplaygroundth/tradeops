"""
Crypto Agent DNA — defines configuration parameters, strategy weights, and biases.
Each agent DNA is specialized to trade a single crypto pair (USDT-quoted).
Risk is expressed as price-distance percentages (sl_pct/tp_pct), not pips.
"""
import os
import random
from dataclasses import dataclass, field
from typing import Dict

def _env_pairs(name: str = "CRYPTO_PAIRS") -> list[str]:
    raw = os.getenv(name, "BTCUSDT,ETHUSDT")
    pairs = [item.strip().upper() for item in raw.split(",") if item.strip()]
    return pairs or ["BTCUSDT", "ETHUSDT"]

CRYPTO_SYMBOLS = _env_pairs()
TIMEFRAMES = ["M5", "M15", "H1", "H4"]
TF_SECONDS = {"M5": 300, "M15": 900, "H1": 3600, "H4": 14400}

STRATEGY_METHODS = [
    "momentum", "mean_reversion", "grid_scalp",
    "order_flow", "breakout_atr", "market_structure",
]

MICRO_MODE = os.getenv("MICRO_MODE", "").lower() in ("1", "true", "yes")

# Symbol root for naming (BTCUSDT -> BTC)
def symbol_root(symbol: str) -> str:
    s = symbol.upper()
    for quote in ("USDT", "USDC", "USD"):
        if s.endswith(quote):
            return s[: -len(quote)]
    return s[:3]


@dataclass
class CryptoAgentDNA:
    id: int
    name: str
    symbol: str
    strategy_weights: Dict[str, float] = field(default_factory=dict)
    sl_pct: float = 0.02   # stop-loss as price-distance fraction (0.02 = 2%)
    tp_pct: float = 0.04   # take-profit as price-distance fraction
    risk_pct: float = 0.01
    timeframe: str = "M15"
    regime_bias: str = "any"   # "bull"|"bear"|"range"|"any"


def random_dna(agent_id: int, symbol: str = None, regime: str = "MIXED") -> CryptoAgentDNA:
    """Generate random DNA for a crypto agent."""
    if symbol is None:
        symbol = random.choice(CRYPTO_SYMBOLS)

    # Intraday crypto targets should be reachable; strategy caps in the
    # manager tighten these further for scalp/timeframe-specific entries.
    if MICRO_MODE:
        sl_pct = random.uniform(0.002, 0.006)
        tp_pct = sl_pct * random.uniform(1.1, 1.4)
    else:
        sl_pct = random.uniform(0.006, 0.018)
        tp_pct = sl_pct * random.uniform(1.3, 1.8)

    # Strategy weights (normalized to sum 1.0)
    weights = {m: random.random() for m in STRATEGY_METHODS}
    total = sum(weights.values())
    weights = {k: v / total for k, v in weights.items()}

    regime_map = {
        "TRENDING": "bull",
        "SIDEWAYS": "range",
        "HIGH_VOL": "range",
        "BEARISH": "bear",
        "BULLISH": "bull",
    }
    regime_bias = regime_map.get(regime, random.choice(["bull", "bear", "range", "any"]))

    return CryptoAgentDNA(
        id=agent_id,
        name=f"CX-{symbol_root(symbol)}-{agent_id:03d}",
        symbol=symbol,
        strategy_weights=weights,
        sl_pct=round(sl_pct, 4),
        tp_pct=round(tp_pct, 4),
        risk_pct=round(random.uniform(0.005, 0.012), 3),
        timeframe=random.choice(TIMEFRAMES),
        regime_bias=regime_bias,
    )


def create_population(count: int = 25, pairs: list = None) -> list:
    """Creates a population distributed across the available crypto pairs."""
    syms = pairs if pairs else CRYPTO_SYMBOLS
    agents = []
    symbols_cycle = syms * (count // len(syms) + 1)
    for i in range(count):
        symbol = symbols_cycle[i]
        agents.append(random_dna(agent_id=i, symbol=symbol))
    return agents
