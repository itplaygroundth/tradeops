"""Tests for crypto GA evolution."""
from engine.dna import random_dna, STRATEGY_METHODS, symbol_root
from engine.evolution import evolve, fitness_score, MIN_TRADES_BEFORE_JUDGMENT


def _stats_for(dnas, trades=50, pnl=5.0, wr=60.0):
    return [
        {"id": d.id, "total_pnl_pct": pnl, "win_rate": wr, "trades": trades,
         "strategy_weights": d.strategy_weights}
        for d in dnas
    ]


def test_fitness_score_ranges():
    d = random_dna(0, "BTCUSDT")
    score = fitness_score(
        {"total_pnl_pct": 10.0, "win_rate": 70.0, "strategy_weights": d.strategy_weights},
        {k: 0.16 for k in STRATEGY_METHODS},
    )
    assert 0.0 <= score <= 1.0


def test_evolve_produces_valid_child_dna():
    dnas = [random_dna(i, ["BTCUSDT", "ETHUSDT"][i % 2]) for i in range(10)]
    stats = _stats_for(dnas)
    new_pop, next_id = evolve(dnas, stats, next_id_start=10, pairs=["BTCUSDT", "ETHUSDT"])
    assert len(new_pop) == len(dnas)
    for child in new_pop:
        # weights valid and normalized
        assert abs(sum(child.strategy_weights.values()) - 1.0) < 1e-6
        assert child.sl_pct > 0
        assert child.tp_pct > child.sl_pct
        # name matches CX-<root>-<id>
        assert child.name == f"CX-{symbol_root(child.symbol)}-{child.id:03d}"
    assert next_id > 10


def test_evolve_returns_unchanged_when_too_few_trades():
    dnas = [random_dna(i, "BTCUSDT") for i in range(10)]
    stats = _stats_for(dnas, trades=MIN_TRADES_BEFORE_JUDGMENT - 1)
    new_pop, next_id = evolve(dnas, stats, next_id_start=10, pairs=["BTCUSDT"])
    # nobody judged yet -> original population returned
    assert new_pop == dnas
    assert next_id == 10


def test_evolve_reassigns_to_active_pairs_only():
    dnas = [random_dna(i, "BTCUSDT") for i in range(8)]
    stats = _stats_for(dnas)
    pairs = ["BTCUSDT", "ETHUSDT"]
    new_pop, _ = evolve(dnas, stats, next_id_start=8, pairs=pairs)
    assert all(d.symbol in pairs for d in new_pop)
    # both active pairs covered
    assert {d.symbol for d in new_pop} == set(pairs)
