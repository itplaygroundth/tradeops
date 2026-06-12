"""
Regime-aware strategy routing for the forex engine.

route_strategy(weights, regime) picks the dominant strategy by weighting
each strategy's score by its regime affinity. With regime=None behaviour
is identical to the original max(weights) — no regression.
"""
from typing import Dict, Optional

REGIME_AFFINITY: Dict[str, Dict[str, float]] = {
    "TREND_UP": {
        "momentum": 1.0,
        "breakout_atr": 1.0,
        "market_structure": 1.0,
        "order_flow": 0.8,
        "session_open": 0.8,
        "mean_reversion": 0.2,
        "grid_scalp": 0.3,
    },
    "TREND_DOWN": {
        "momentum": 1.0,
        "breakout_atr": 1.0,
        "market_structure": 1.0,
        "order_flow": 0.8,
        "session_open": 0.8,
        "mean_reversion": 0.2,
        "grid_scalp": 0.3,
    },
    "RANGING": {
        "mean_reversion": 1.0,
        "grid_scalp": 1.0,
        "order_flow": 0.8,
        "market_structure": 0.7,
        "momentum": 0.3,
        "breakout_atr": 0.3,
        "session_open": 0.5,
    },
}
_DEFAULT_AFFINITY = 0.5


def route_strategy(weights: Dict[str, float], regime: Optional[str]) -> str:
    """Return dominant strategy, regime-adjusted when regime is not None."""
    if not weights:
        return "momentum"
    if regime is None or regime not in REGIME_AFFINITY:
        return max(weights, key=lambda k: weights[k])
    affinity = REGIME_AFFINITY[regime]
    scored = {k: v * affinity.get(k, _DEFAULT_AFFINITY) for k, v in weights.items()}
    return max(scored, key=lambda k: scored[k])
