"""
Evolution Engine for Forex — ranks population, preserves elite/diversity,
and performs crossover/mutation to evolve agents.
"""
import copy
import random
from typing import List

from engine.dna import ForexAgentDNA, FOREX_SYMBOLS, STRATEGY_METHODS, random_dna

MIN_TRADES_BEFORE_JUDGMENT = 30
EVOLUTION_INTERVAL = 3600

def fitness_score(agent_dict: dict, pop_strategy_avg: dict) -> float:
    """Calculates fitness score based on PnL, Win Rate, and strategy diversity."""
    pnl = max(agent_dict.get("total_pnl_pct", 0), -50)
    wr = agent_dict.get("win_rate", 0) / 100.0
    pnl_score = min(max((pnl + 50) / 100.0, 0), 1.0)

    # Diversity bonus
    weights = agent_dict.get("strategy_weights", {})
    diversity_sum = sum(abs(weights.get(k, 0) - pop_strategy_avg.get(k, 0)) for k in pop_strategy_avg)
    diversity_bonus = min(diversity_sum / max(len(pop_strategy_avg), 1) * 5, 1.0)

    return 0.5 * pnl_score + 0.3 * wr + 0.2 * diversity_bonus

def evolve(agents: List[ForexAgentDNA], agent_stats: List[dict], next_id_start: int) -> tuple:
    """
    Runs one evolution cycle.
    Returns: (new_population, next_id)
    """
    if len(agents) < 5:
        return agents, next_id_start

    # Split: protected (< MIN_TRADES) vs ranked
    stats_map = {s["id"]: s for s in agent_stats}
    protected = [a for a in agents if stats_map.get(a.id, {}).get("trades", 0) < MIN_TRADES_BEFORE_JUDGMENT]
    ranked_pool = [a for a in agents if stats_map.get(a.id, {}).get("trades", 0) >= MIN_TRADES_BEFORE_JUDGMENT]

    if not ranked_pool:
        # If no agent has completed enough trades, return original population
        return agents, next_id_start

    # Calculate population strategy average
    all_weights = [a.strategy_weights for a in ranked_pool]
    strategies = list(all_weights[0].keys()) if all_weights else []
    pop_avg = {s: sum(w.get(s, 0) for w in all_weights) / len(all_weights) for s in strategies}

    # Score + rank
    scored = [(a, fitness_score(stats_map.get(a.id, {}), pop_avg)) for a in ranked_pool]
    scored.sort(key=lambda x: x[1], reverse=True)

    # Elite (top 20%)
    elite_count = max(1, len(scored) // 5)
    elite = [a for a, _ in scored[:elite_count]]

    next_id = next_id_start
    next_gen = []

    # Keep protected
    for a in protected:
        next_gen.append(a)

    # Keep elite (reassign IDs to avoid duplicates)
    for e in elite:
        new = copy.deepcopy(e)
        new.id = next_id
        new.name = f"FX-{new.symbol[:3]}-{next_id:03d}"
        next_id += 1
        next_gen.append(new)

    # Ensure symbol coverage — must have at least 1 agent per symbol
    covered_symbols = {a.symbol for a in next_gen}
    for sym in FOREX_SYMBOLS:
        if sym not in covered_symbols:
            fresh = random_dna(agent_id=next_id, symbol=sym)
            next_id += 1
            next_gen.append(fresh)
            covered_symbols.add(sym)

    # Fill remaining with mutations + crossovers + fresh blood
    target_count = len(agents)
    while len(next_gen) < target_count:
        roll = random.random()
        if roll < 0.3 and elite:
            # Mutation
            parent = random.choice(elite)
            child = copy.deepcopy(parent)
            child.id = next_id
            child.name = f"FX-{child.symbol[:3]}-{next_id:03d}"
            # Mutate weights
            for k in child.strategy_weights:
                child.strategy_weights[k] *= random.uniform(0.7, 1.3)
            total = sum(child.strategy_weights.values())
            if total > 0:
                child.strategy_weights = {k: v/total for k, v in child.strategy_weights.items()}
            # Mutate pips
            child.sl_pips = max(5, child.sl_pips * random.uniform(0.8, 1.2))
            child.tp_pips = max(child.sl_pips * 1.5, child.tp_pips * random.uniform(0.8, 1.2))
            next_id += 1
            next_gen.append(child)
        elif roll < 0.5 and len(elite) >= 2:
            # Crossover
            p1, p2 = random.sample(elite, 2)
            child_dna = random_dna(next_id, symbol=p1.symbol)
            # Blend weights
            for k in STRATEGY_METHODS:
                w1 = p1.strategy_weights.get(k, 0)
                w2 = p2.strategy_weights.get(k, 0)
                child_dna.strategy_weights[k] = (w1 + w2) / 2
            total = sum(child_dna.strategy_weights.values())
            if total > 0:
                child_dna.strategy_weights = {k: v/total for k, v in child_dna.strategy_weights.items()}
            next_id += 1
            next_gen.append(child_dna)
        else:
            # Fresh blood
            sym = random.choice(FOREX_SYMBOLS)
            fresh = random_dna(next_id, symbol=sym)
            next_id += 1
            next_gen.append(fresh)

    return next_gen[:target_count], next_id
