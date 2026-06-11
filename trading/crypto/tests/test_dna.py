"""Tests for CryptoAgentDNA / random_dna."""
from engine.dna import (
    CryptoAgentDNA, random_dna, create_population,
    STRATEGY_METHODS, CRYPTO_SYMBOLS, symbol_root,
)


def test_random_dna_weights_sum_to_one():
    dna = random_dna(7, "BTCUSDT")
    assert abs(sum(dna.strategy_weights.values()) - 1.0) < 1e-9
    assert set(dna.strategy_weights.keys()) == set(STRATEGY_METHODS)


def test_random_dna_sl_tp_ranges():
    for i in range(50):
        dna = random_dna(i, "ETHUSDT")
        assert 0.006 <= dna.sl_pct <= 0.018
        assert dna.tp_pct > dna.sl_pct  # TP wider than SL
        assert dna.tp_pct <= dna.sl_pct * 1.9


def test_random_dna_name_format():
    dna = random_dna(7, "BTCUSDT")
    assert dna.name == "CX-BTC-007"
    assert dna.symbol == "BTCUSDT"


def test_symbol_root():
    assert symbol_root("BTCUSDT") == "BTC"
    assert symbol_root("SOLUSDT") == "SOL"
    assert symbol_root("XRPUSDT") == "XRP"


def test_create_population_distributes_pairs():
    pop = create_population(25)
    assert len(pop) == 25
    syms = {d.symbol for d in pop}
    assert syms == set(CRYPTO_SYMBOLS)
    assert all(isinstance(d, CryptoAgentDNA) for d in pop)


def test_create_population_custom_pairs():
    pop = create_population(6, pairs=["BTCUSDT", "ETHUSDT"])
    assert len(pop) == 6
    assert {d.symbol for d in pop} == {"BTCUSDT", "ETHUSDT"}
