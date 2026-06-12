"""
Evolution Engine for Crypto — ranks population, preserves elite/diversity,
performs crossover/mutation, and reallocates agents toward higher-fitness pairs.
"""
import copy
import os
import random
from typing import List

from engine.dna import CryptoAgentDNA, CRYPTO_SYMBOLS, STRATEGY_METHODS, random_dna, symbol_root

MIN_TRADES_BEFORE_JUDGMENT = 10
EVOLUTION_INTERVAL = 3600
DD_REF_PCT = float(os.getenv("EVO_DD_REF_PCT", "20.0"))
EXP_REF_PCT = float(os.getenv("EVO_EXP_REF_PCT", "0.5"))
MUTATION_TP_FLOOR_RR = float(os.getenv("CRYPTO_MUTATION_TP_FLOOR_RR", "1.5"))


def fitness_score(agent_dict: dict, pop_strategy_avg: dict) -> float:
    """Fitness from PnL, expectancy, win rate, diversity, and drawdown penalty.

    Missing max_dd_pct/expectancy_pct keys (legacy dicts) degrade neutral:
    dd_score=1.0, exp_score=0.5.
    """
    pnl = max(agent_dict.get("total_pnl_pct", 0), -50)
    wr = agent_dict.get("win_rate", 0) / 100.0
    pnl_score = min(max((pnl + 50) / 100.0, 0), 1.0)

    expectancy = agent_dict.get("expectancy_pct")
    exp_score = 0.5 if expectancy is None else min(max(0.5 + expectancy / (2 * EXP_REF_PCT), 0), 1.0)

    max_dd = agent_dict.get("max_dd_pct", 0.0) or 0.0
    dd_score = max(0.0, 1.0 - max_dd / DD_REF_PCT)

    weights = agent_dict.get("strategy_weights", {})
    diversity_sum = sum(abs(weights.get(k, 0) - pop_strategy_avg.get(k, 0)) for k in pop_strategy_avg)
    diversity_bonus = min(diversity_sum / max(len(pop_strategy_avg), 1) * 5, 1.0)

    return 0.35 * pnl_score + 0.20 * exp_score + 0.15 * wr + 0.15 * diversity_bonus + 0.15 * dd_score


def _pair_fitness(agents: List[CryptoAgentDNA], stats_map: dict, pairs: list) -> dict:
    """Average total_pnl_pct per active pair (dynamic pair allocation signal)."""
    agg = {p: [] for p in pairs}
    for a in agents:
        if a.symbol in agg:
            agg[a.symbol].append(stats_map.get(a.id, {}).get("total_pnl_pct", 0.0))
    return {p: (sum(v) / len(v) if v else 0.0) for p, v in agg.items()}


def _weighted_pair_choice(pair_fit: dict, pairs: list) -> str:
    """Pick a pair biased toward higher fitness (softmax-ish over shifted scores)."""
    if not pairs:
        return random.choice(CRYPTO_SYMBOLS)
    lo = min(pair_fit.get(p, 0.0) for p in pairs)
    # shift so all weights positive, +1 floor so even worst pair keeps a chance
    weights = [pair_fit.get(p, 0.0) - lo + 1.0 for p in pairs]
    return random.choices(pairs, weights=weights, k=1)[0]


def evolve(agents: List[CryptoAgentDNA], agent_stats: List[dict], next_id_start: int,
           pairs: list = None) -> tuple:
    """One evolution cycle. Returns (new_population, next_id).

    Agents are reallocated only across the active `pairs` pool, biased toward
    higher-fitness pairs (fitness = avg total_pnl_pct).
    """
    if pairs is None:
        pairs = CRYPTO_SYMBOLS
    if len(agents) < 5:
        return agents, next_id_start

    stats_map = {s["id"]: s for s in agent_stats}
    protected = [a for a in agents if stats_map.get(a.id, {}).get("trades", 0) < MIN_TRADES_BEFORE_JUDGMENT]
    ranked_pool = [a for a in agents if stats_map.get(a.id, {}).get("trades", 0) >= MIN_TRADES_BEFORE_JUDGMENT]

    if not ranked_pool:
        return agents, next_id_start

    # Population strategy average
    all_weights = [a.strategy_weights for a in ranked_pool]
    strategies = list(all_weights[0].keys()) if all_weights else []
    pop_avg = {s: sum(w.get(s, 0) for w in all_weights) / len(all_weights) for s in strategies}

    # Score + rank
    scored = [(a, fitness_score(stats_map.get(a.id, {}), pop_avg)) for a in ranked_pool]
    scored.sort(key=lambda x: x[1], reverse=True)

    elite_count = max(1, len(scored) // 5)
    elite = [a for a, _ in scored[:elite_count]]

    pair_fit = _pair_fitness(ranked_pool, stats_map, pairs)

    next_id = next_id_start
    next_gen: List[CryptoAgentDNA] = []

    def rename(d: CryptoAgentDNA, new_id: int):
        d.id = new_id
        d.name = f"CX-{symbol_root(d.symbol)}-{new_id:03d}"
        return d

    # Keep protected, but re-home any on a now-inactive pair
    for a in protected:
        if a.symbol not in pairs:
            a.symbol = _weighted_pair_choice(pair_fit, pairs)
            a.name = f"CX-{symbol_root(a.symbol)}-{a.id:03d}"
        next_gen.append(a)

    # Keep elite (reassign IDs to avoid duplicates)
    for e in elite:
        new = copy.deepcopy(e)
        if new.symbol not in pairs:
            new.symbol = _weighted_pair_choice(pair_fit, pairs)
        rename(new, next_id)
        next_id += 1
        next_gen.append(new)

    # Symbol coverage — at least 1 agent per active pair
    covered = {a.symbol for a in next_gen}
    for sym in pairs:
        if sym not in covered:
            fresh = random_dna(agent_id=next_id, symbol=sym)
            next_id += 1
            next_gen.append(fresh)
            covered.add(sym)

    # Fill remaining with mutation / crossover / fresh blood, biased to top pairs
    target_count = len(agents)
    while len(next_gen) < target_count:
        roll = random.random()
        if roll < 0.3 and elite:
            parent = random.choice(elite)
            child = copy.deepcopy(parent)
            # reallocate toward higher-fitness pairs
            child.symbol = _weighted_pair_choice(pair_fit, pairs)
            for k in child.strategy_weights:
                child.strategy_weights[k] *= random.uniform(0.7, 1.3)
            total = sum(child.strategy_weights.values())
            if total > 0:
                child.strategy_weights = {k: v / total for k, v in child.strategy_weights.items()}
            child.sl_pct = min(0.05, max(0.005, child.sl_pct * random.uniform(0.8, 1.2)))
            child.tp_pct = max(child.sl_pct * MUTATION_TP_FLOOR_RR, child.tp_pct * random.uniform(0.8, 1.2))
            rename(child, next_id)
            next_id += 1
            next_gen.append(child)
        elif roll < 0.5 and len(elite) >= 2:
            p1, p2 = random.sample(elite, 2)
            sym = _weighted_pair_choice(pair_fit, pairs)
            child_dna = random_dna(next_id, symbol=sym)
            for k in STRATEGY_METHODS:
                w1 = p1.strategy_weights.get(k, 0)
                w2 = p2.strategy_weights.get(k, 0)
                child_dna.strategy_weights[k] = (w1 + w2) / 2
            total = sum(child_dna.strategy_weights.values())
            if total > 0:
                child_dna.strategy_weights = {k: v / total for k, v in child_dna.strategy_weights.items()}
            next_id += 1
            next_gen.append(child_dna)
        else:
            sym = _weighted_pair_choice(pair_fit, pairs)
            fresh = random_dna(next_id, symbol=sym)
            next_id += 1
            next_gen.append(fresh)

    return next_gen[:target_count], next_id
