"""
MarkovRegimeDetector — 3-state Markov regime from D1 OHLCV candles.

States: TREND_UP, TREND_DOWN, RANGING
Transition matrix estimated from bar sequence; current regime = majority
vote over last 5 D1 bars.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

STATES = ("TREND_UP", "TREND_DOWN", "RANGING")

# Daily return thresholds for state classification
_RET_UP = 0.003    # > +0.3% = trending up
_RET_DOWN = -0.003  # < -0.3% = trending down


def _classify_bar(ret: float, atr_pct: float, atr_mean_pct: float) -> str:
    """Classify single D1 bar into a state."""
    if atr_pct > atr_mean_pct * 1.5:
        # high-volatility bar → goes with direction
        return "TREND_UP" if ret > 0 else "TREND_DOWN"
    if ret > _RET_UP:
        return "TREND_UP"
    if ret < _RET_DOWN:
        return "TREND_DOWN"
    return "RANGING"


def detect_regime(candles: List[Dict]) -> Tuple[str, Dict[str, Dict[str, float]]]:
    """Estimate current regime and transition matrix from D1 candles.

    Returns:
        (current_regime, transition_prob)
        current_regime: "TREND_UP" | "TREND_DOWN" | "RANGING"
        transition_prob: {from_state: {to_state: probability}}
    """
    if len(candles) < 10:
        return "RANGING", {s: {t: 1 / 3 for t in STATES} for s in STATES}

    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]

    atrs = [h - lo for h, lo in zip(highs, lows)]
    atr_mean = sum(atrs) / len(atrs) if atrs else 1e-9

    state_seq: List[str] = []
    for i in range(1, len(candles)):
        prev = closes[i - 1] or 1e-9
        ret = (closes[i] - prev) / prev
        atr_pct = atrs[i] / closes[i] * 100 if closes[i] else 0.0
        atr_mean_pct = atr_mean / closes[i] * 100 if closes[i] else 0.0
        state_seq.append(_classify_bar(ret, atr_pct, atr_mean_pct))

    # count transitions
    trans_counts: Dict[str, Dict[str, int]] = {s: {t: 0 for t in STATES} for s in STATES}
    for i in range(len(state_seq) - 1):
        trans_counts[state_seq[i]][state_seq[i + 1]] += 1

    # normalize to probabilities
    trans_prob: Dict[str, Dict[str, float]] = {}
    for s in STATES:
        row_sum = sum(trans_counts[s].values())
        if row_sum > 0:
            trans_prob[s] = {t: trans_counts[s][t] / row_sum for t in STATES}
        else:
            trans_prob[s] = {t: 1 / 3 for t in STATES}

    # current regime = majority of last 5 bars
    tail = state_seq[-5:] if len(state_seq) >= 5 else state_seq
    counts = {s: tail.count(s) for s in STATES}
    current = max(counts, key=lambda s: counts[s])

    logger.info("Markov regime: tail=%s → %s  trans=%s", tail, current, {
        s: max(trans_prob[s], key=lambda t: trans_prob[s][t]) for s in STATES
    })
    return current, trans_prob
