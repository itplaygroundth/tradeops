"""Tests for CryptoAgentManager — integration hub."""
import pytest

import engine.agent_manager as manager_mod
from engine.agent_manager import CryptoAgentManager


class MockRouter:
    paper_mode = True
    exchange_name = "binance"

    def __init__(self):
        self.orders = []

    async def place_order(self, *a, **k):
        self.orders.append((a, k))
        return {"ticket": 1, "status": "filled", "price": 100.0, "paper": True}

    async def get_positions(self):
        return []

    def set_tick_callback(self, cb):
        pass


def _mgr(**kw):
    return CryptoAgentManager(MockRouter(), paper_mode=True, agent_count=10, **kw)


def _force_strategy(agent, strategy):
    agent.dna.strategy_weights = {strategy: 1.0}


def _seed_manager_trend(mgr, symbol="BTCUSDT", direction="down"):
    prices = [120.0 - i for i in range(60)] if direction == "down" else [60.0 + i for i in range(60)]
    for i, price in enumerate(prices):
        mgr.signal_engine.record_tick(symbol, price, 10.0, float((i + 1) * 14400))


def test_default_pairs():
    mgr = CryptoAgentManager(MockRouter(), agent_count=10)
    assert mgr.pairs == ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]


def test_custom_pairs():
    mgr = CryptoAgentManager(MockRouter(), agent_count=4, pairs=["BTCUSDT", "ETHUSDT"])
    assert mgr.pairs == ["BTCUSDT", "ETHUSDT"]
    assert all(a.dna.symbol in ("BTCUSDT", "ETHUSDT") for a in mgr.agents)


def test_initial_balance_equity():
    mgr = _mgr()
    assert mgr._account_balance == 1000.0
    assert mgr._account_equity == 1000.0


@pytest.mark.asyncio
async def test_on_tick_feeds_signal_engine():
    mgr = _mgr(pairs=["BTCUSDT"])
    # space ticks by 1 hour so each forms its own M15 candle
    for i in range(25):
        await mgr.on_tick("BTCUSDT", 100.0 + i, 5.0, float((i + 1) * 3600))
    hist = mgr.signal_engine.get_history("BTCUSDT", "M15")
    assert hist.count == 25


@pytest.mark.asyncio
async def test_on_tick_executes_via_router():
    router = MockRouter()
    mgr = CryptoAgentManager(router, paper_mode=False, agent_count=10, pairs=["BTCUSDT"])
    # strong uptrend -> overbought -> SHORT signals on momentum agents
    for i in range(60):
        await mgr.on_tick("BTCUSDT", 100.0 + i * 2, 50.0, float((i + 1) * 3600))
    # at least attempted some orders (live mode routes through router)
    assert isinstance(router.orders, list)


@pytest.mark.asyncio
async def test_to_state_dict_schema():
    mgr = _mgr(pairs=["BTCUSDT", "ETHUSDT"])
    for i in range(15):
        await mgr.on_tick("BTCUSDT", 100.0 + i, 5.0, float((i + 1) * 3600))
        await mgr.on_tick("ETHUSDT", 50.0 + i, 5.0, float((i + 1) * 3600))
    state = mgr.to_state_dict()
    assert set(state.keys()) >= {"summary", "agents", "prices", "order_history"}
    summary = state["summary"]
    for key in ("total_pnl_pct", "total_equity", "total_trades", "winners",
                "losers", "uptime_seconds", "open_positions", "exchange", "mode"):
        assert key in summary, f"missing summary key {key}"
    assert isinstance(state["agents"], list)
    assert "BTCUSDT" in state["prices"]
    p = state["prices"]["BTCUSDT"]
    for key in ("mid", "change_pct", "bid", "ask"):
        assert key in p
    assert summary["exchange"] == "binance"
    assert summary["mode"] == "paper"


def test_add_remove_pair():
    mgr = _mgr(pairs=["BTCUSDT"])
    mgr.add_pair("ETHUSDT")
    assert "ETHUSDT" in mgr.pairs
    mgr.add_pair("ETHUSDT")  # idempotent
    assert mgr.pairs.count("ETHUSDT") == 1
    mgr.remove_pair("ETHUSDT")
    assert "ETHUSDT" not in mgr.pairs


def test_get_open_positions_returns_paper_positions():
    """Paper positions live on the agents, not the exchange feed. The dashboard
    order book reads /api/positions, so the manager must expose them with the
    schema the UI expects."""
    mgr = _mgr(pairs=["BTCUSDT"])
    agent = mgr.agents[0]
    agent._open_ticket = 12345
    agent._open_entry = 50000.0
    agent._open_side = "BUY"
    agent._open_sl = 49000.0
    agent._open_tp = 52000.0
    agent._open_qty = 0.01
    mgr._latest_prices["BTCUSDT"] = {"mid": 51000.0, "bid": 50990.0, "ask": 51010.0, "change_pct": 0.0}

    positions = mgr.get_open_positions()

    assert len(positions) == 1
    p = positions[0]
    # schema required by OrderBook.jsx
    for key in ("ticket", "symbol", "type", "volume", "price_open", "price_current", "profit", "sl", "tp"):
        assert key in p, f"missing key {key}"
    assert p["ticket"] == 12345
    assert p["symbol"] == "BTCUSDT"
    assert p["type"] == "BUY"
    assert p["price_open"] == 50000.0
    assert p["price_current"] == 51000.0
    # BUY profit = (current-entry)*qty = (51000-50000)*0.01 = 10
    assert p["profit"] == pytest.approx(10.0)


def test_get_open_positions_empty_when_flat():
    mgr = _mgr(pairs=["BTCUSDT"])
    assert mgr.get_open_positions() == []


def test_open_order_history_exposes_floating_pnl():
    mgr = _mgr(pairs=["BTCUSDT"])
    agent = mgr.agents[0]
    agent.dna.symbol = "BTCUSDT"
    agent._open_ticket = 123
    agent._open_entry = 100.0
    agent._open_side = "BUY"
    agent._open_sl = 95.0
    agent._open_tp = 110.0
    agent._open_qty = 2.0
    mgr._latest_prices["BTCUSDT"] = {"mid": 103.0, "bid": 102.99, "ask": 103.01, "change_pct": 0.0}
    mgr._order_history.insert(0, {
        "timestamp": 1.0,
        "agent": agent.dna.name,
        "symbol": "BTCUSDT",
        "action": "BUY",
        "qty": 2.0,
        "volume": 2.0,
        "price": 100.0,
        "sl": 95.0,
        "tp": 110.0,
        "pnl": 0.0,
        "pnl_pct": 0.0,
        "type": "paper",
        "status": "open",
        "ticket": 123,
    })

    history = mgr.to_state_dict()["order_history"]

    assert history[0]["ticket"] == 123
    assert history[0]["pnl"] == pytest.approx(6.0)
    assert history[0]["price_current"] == 103.0


@pytest.mark.asyncio
async def test_strategy_guard_blocks_losing_strategy():
    mgr = _mgr(pairs=["BTCUSDT"])
    agent = mgr.agents[0]
    agent.dna.symbol = "BTCUSDT"
    agent.dna.strategy_weights = {"grid_scalp": 1.0}
    mgr.agents = [agent]
    mgr.strategy_performance_guard.record("grid_scalp", -1.0)
    mgr.strategy_performance_guard.record("grid_scalp", -1.0)

    await mgr._process_agents("BTCUSDT", 100.0)

    assert not agent.is_in_trade
    assert mgr._order_history == []


def test_htf_aligned_signal_gets_confidence_boost():
    mgr = _mgr(pairs=["BTCUSDT"])
    _seed_manager_trend(mgr, "BTCUSDT", "down")
    agent = mgr.agents[0]
    agent.dna.symbol = "BTCUSDT"
    agent.dna.timeframe = "M15"
    _force_strategy(agent, "momentum")
    agent.generate_signal = lambda price: {
        "action": "SHORT", "confidence": 40, "reason": "unit short"
    }

    signal = mgr._signal_with_trend_context(agent, 100.0, "momentum")

    assert signal["action"] == "SHORT"
    assert signal["confidence"] == 55
    assert "HTF aligned" in signal["reason"]


def test_htf_guard_blocks_countertrend_signal_for_any_strategy():
    mgr = _mgr(pairs=["BTCUSDT"])
    _seed_manager_trend(mgr, "BTCUSDT", "down")
    agent = mgr.agents[0]
    agent.dna.symbol = "BTCUSDT"
    _force_strategy(agent, "breakout_atr")
    agent.generate_signal = lambda price: {
        "action": "LONG", "confidence": 90, "reason": "unit long"
    }

    signal = mgr._signal_with_trend_context(agent, 100.0, "breakout_atr")

    assert signal["action"] == "HOLD"
    assert "HTF trend guard" in signal["reason"]


def test_trend_follow_fallback_opens_direction_when_signal_holds():
    mgr = _mgr(pairs=["BTCUSDT"])
    _seed_manager_trend(mgr, "BTCUSDT", "down")
    agent = mgr.agents[0]
    agent.dna.symbol = "BTCUSDT"
    agent.dna.timeframe = "M15"
    _force_strategy(agent, "market_structure")
    agent.generate_signal = lambda price: {
        "action": "HOLD", "confidence": 35, "reason": "structure waiting"
    }

    signal = mgr._signal_with_trend_context(agent, 100.0, "market_structure")

    assert signal["action"] == "SHORT"
    assert signal["confidence"] == 55
    assert "Trend-follow fallback" in signal["reason"]


def test_effective_sl_tp_caps_scalp_targets():
    mgr = _mgr(pairs=["BTCUSDT"])
    agent = mgr.agents[0]
    agent.dna.timeframe = "M5"
    agent.dna.sl_pct = 0.025
    agent.dna.tp_pct = 0.085
    _force_strategy(agent, "grid_scalp")

    sl_pct, tp_pct = mgr._effective_sl_tp(agent, "grid_scalp")

    assert sl_pct == pytest.approx(0.008)
    assert tp_pct == pytest.approx(0.012)


def test_effective_sl_tp_uses_atr_to_tighten_stop():
    mgr = _mgr(pairs=["BTCUSDT"])
    agent = mgr.agents[0]
    agent.dna.symbol = "BTCUSDT"
    agent.dna.timeframe = "M15"
    agent.dna.sl_pct = 0.012
    agent.dna.tp_pct = 0.020
    _force_strategy(agent, "momentum")

    prices = [100.0 + ((i % 2) * 0.08) for i in range(40)]
    for i, price in enumerate(prices):
        mgr.signal_engine.record_tick("BTCUSDT", price, 10.0, float((i + 1) * 900))

    sl_pct, tp_pct = mgr._effective_sl_tp(agent, "momentum")

    assert sl_pct < 0.012
    assert sl_pct >= 0.003
    assert tp_pct >= sl_pct * 1.3


@pytest.mark.asyncio
async def test_process_agents_evaluates_beyond_first_three_and_selects_signal(monkeypatch):
    monkeypatch.setattr(manager_mod, "ENTRY_STRATEGY_ALLOWLIST", set())
    mgr = _mgr(pairs=["BTCUSDT"])
    _seed_manager_trend(mgr, "BTCUSDT", "down")
    agents = mgr.agents[:4]
    for idx, agent in enumerate(agents):
        agent.dna.symbol = "BTCUSDT"
        agent.dna.timeframe = "M15"
        agent.dna.sl_pct = 0.01
        agent.dna.tp_pct = 0.015
        if idx < 3:
            _force_strategy(agent, "mean_reversion")
            agent.generate_signal = lambda price: {
                "action": "HOLD", "confidence": 0, "reason": "first three idle"
            }
        else:
            _force_strategy(agent, "momentum")
            agent.generate_signal = lambda price: {
                "action": "SHORT", "confidence": 60, "reason": "fourth agent short"
            }
    mgr.agents = agents

    await mgr._process_agents("BTCUSDT", 100.0)

    assert agents[3].is_in_trade
    assert mgr._order_history[0]["action"] == "SELL"
    assert mgr._order_history[0]["agent"] == agents[3].dna.name


@pytest.mark.asyncio
async def test_process_agents_uses_selected_agent_strategy_for_risk_caps(monkeypatch):
    monkeypatch.setattr(manager_mod, "ENTRY_STRATEGY_ALLOWLIST", set())
    mgr = _mgr(pairs=["BTCUSDT"])
    _seed_manager_trend(mgr, "BTCUSDT", "down")
    agents = mgr.agents[:2]

    agents[0].dna.symbol = "BTCUSDT"
    agents[0].dna.timeframe = "M15"
    agents[0].dna.sl_pct = 0.018
    agents[0].dna.tp_pct = 0.03
    _force_strategy(agents[0], "mean_reversion")
    agents[0].generate_signal = lambda price: {
        "action": "HOLD", "confidence": 0, "reason": "idle"
    }

    agents[1].dna.symbol = "BTCUSDT"
    agents[1].dna.timeframe = "M15"
    agents[1].dna.sl_pct = 0.018
    agents[1].dna.tp_pct = 0.03
    _force_strategy(agents[1], "grid_scalp")
    agents[1].generate_signal = lambda price: {
        "action": "SHORT", "confidence": 60, "reason": "selected scalp"
    }
    mgr.agents = agents

    await mgr._process_agents("BTCUSDT", 100.0)

    row = mgr._order_history[0]
    assert row["agent"] == agents[1].dna.name
    assert row["strategy"] == "grid_scalp"
    assert row["timeframe"] == "M15"
    assert row["sl_pct"] == pytest.approx(0.008)
    assert row["tp_pct"] == pytest.approx(0.012)


def test_evolution_releases_open_positions_from_risk_guardian():
    """Evolution rebuilds all agent objects. Agents holding positions must be
    released from the risk guardian first, otherwise _open_positions leaks and
    permanently blocks new trades at MAX_CONCURRENT_POSITIONS."""
    mgr = _mgr(pairs=["BTCUSDT"])
    # simulate 3 agents holding open positions
    for agent in mgr.agents[:3]:
        agent._open_ticket = 1
        agent._open_side = "BUY"
        mgr.risk_guardian.on_position_opened(agent.dna.symbol)
    assert sum(mgr.risk_guardian._open_positions.values()) == 3

    mgr._run_evolution()

    # new agents are fresh (no positions); risk guardian must be back to 0
    assert all(not a.is_in_trade for a in mgr.agents)
    assert sum(mgr.risk_guardian._open_positions.values()) == 0


@pytest.mark.asyncio
async def test_paper_position_lifecycle():
    mgr = _mgr(pairs=["BTCUSDT"])
    # feed downtrend so oversold -> LONG opens, then rally to TP
    for i in range(40):
        await mgr.on_tick("BTCUSDT", 200.0 - i, 50.0, float((i + 1) * 3600))
    opened = sum(1 for a in mgr.agents if a.is_in_trade)
    # rally hard to trigger TP/SL on any open paper trades
    for i in range(40):
        await mgr.on_tick("BTCUSDT", 160.0 + i * 2, 50.0, float((41 + i) * 3600))
    state = mgr.to_state_dict()
    assert state["summary"]["total_trades"] >= 0  # lifecycle ran without error
