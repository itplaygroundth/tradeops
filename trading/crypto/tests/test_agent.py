"""Tests for CryptoAgent."""
from engine.dna import CryptoAgentDNA
from engine.signals import CryptoSignalEngine
from engine.risk_guardian import CryptoRiskGuardian
from engine.agent import CryptoAgent


def _make_agent(dominant, symbol="BTCUSDT"):
    from engine.dna import STRATEGY_METHODS
    weights = {m: 0.01 for m in STRATEGY_METHODS}
    weights[dominant] = 0.9
    dna = CryptoAgentDNA(id=1, name="CX-BTC-001", symbol=symbol, strategy_weights=weights)
    return CryptoAgent(dna, CryptoSignalEngine(), CryptoRiskGuardian())


def _feed(agent, prices, vol=10.0):
    # space ticks by a large interval so each price forms its own candle
    # across every timeframe bucket (H1 = 3600s is the coarsest)
    for i, p in enumerate(prices):
        agent.signal_engine.record_tick(agent.dna.symbol, p, vol, timestamp=float((i + 1) * 3600))


def test_generate_signal_momentum_dispatch():
    agent = _make_agent("momentum")
    _feed(agent, [100.0 + i for i in range(40)])
    sig = agent.generate_signal(140.0)
    # rising trend: the RSI trend-guard prevents a counter-trend SHORT, so the
    # momentum strategy follows the uptrend (LONG) or stands aside — never SHORT
    assert sig["action"] != "SHORT"


def test_mean_reversion_holds_in_trending_regime():
    """A strong directional move is TRENDING/HIGH_VOL — mean reversion must NOT
    fade it; it should HOLD instead of inverting into the trend."""
    mr = _make_agent("mean_reversion")
    _feed(mr, [100.0 + i for i in range(40)])  # strong uptrend -> HIGH_VOL
    sig = mr.generate_signal(140.0)
    assert sig["action"] == "HOLD"
    assert "regime" in sig["reason"].lower() or "trend" in sig["reason"].lower()


def test_mean_reversion_inverts_in_sideways_regime():
    """In a ranging (SIDEWAYS) market, mean reversion inverts the technical signal."""
    import math
    mr = _make_agent("mean_reversion", symbol="ETHUSDT")
    _feed(mr, [100.0 + 0.2 * math.sin(i / 2.0) for i in range(60)])
    tech_action = mr.signal_engine.technical_signal("ETHUSDT", mr.dna.timeframe)["action"]
    sig = mr.generate_signal(100.0)
    if tech_action == "SHORT":
        assert sig["action"] == "LONG"
    elif tech_action == "LONG":
        assert sig["action"] == "SHORT"


def test_generate_signal_order_flow_dispatch():
    agent = _make_agent("order_flow")
    _feed(agent, [100.0 + (i % 3) for i in range(30)])
    sig = agent.generate_signal(100.0)
    assert sig["action"] in ("LONG", "SHORT", "HOLD")


def test_record_trade_result_updates_win_loss():
    agent = _make_agent("momentum")
    agent.record_trade_result(10.0, 1.0)
    agent.record_trade_result(-5.0, -0.5)
    agent.record_trade_result(8.0, 0.8)
    assert agent.trades_count == 3
    assert agent.wins == 2
    assert agent.losses == 1
    assert agent.win_rate == 2 / 3
    assert agent.total_pnl == 13.0


def test_to_dict_schema():
    agent = _make_agent("momentum")
    d = agent.to_dict()
    for key in ("id", "name", "symbol", "strategy", "trades", "win_rate",
                "total_pnl", "total_pnl_pct", "pnl_pct", "sl_pct", "tp_pct",
                "strategy_weights", "in_trade"):
        assert key in d
    assert d["strategy"] == "momentum"


def test_update_strategy_weights_normalizes():
    agent = _make_agent("momentum")
    agent.update_strategy_weights({"momentum": 2.0, "order_flow": 2.0})
    assert abs(sum(agent.dna.strategy_weights.values()) - 1.0) < 1e-9
    assert agent.dna.strategy_weights["momentum"] == 0.5
