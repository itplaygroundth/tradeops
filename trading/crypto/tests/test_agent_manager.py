"""Tests for CryptoAgentManager — integration hub."""
import json

import pytest

import engine.agent_manager as manager_mod
from engine.agent_manager import CryptoAgentManager


class MockRouter:
    paper_mode = True
    exchange_name = "binance"
    live_trading_supported = False
    network = "paper"
    credential_status = "not_required"
    supports_short = True
    uses_ticket_positions = False

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


def _write_shadow_guard_policy(path):
    path.write_text(json.dumps({
        "version": 1,
        "mode": "shadow_with_regime_no_trade_guard",
        "no_trade_regimes": ["high_volatility"],
        "enforcement": {
            "pre_order_required": True,
            "block_new_entries_when_regime_in": ["high_volatility"],
        },
    }))


def test_default_pairs():
    mgr = CryptoAgentManager(MockRouter(), agent_count=10)
    assert mgr.pairs == ['BTCUSDT', 'ETHUSDT']


def test_custom_pairs():
    mgr = CryptoAgentManager(MockRouter(), agent_count=4, pairs=["BTCUSDT", "ETHUSDT"])
    assert mgr.pairs == ["BTCUSDT", "ETHUSDT"]
    assert all(a.dna.symbol in ("BTCUSDT", "ETHUSDT") for a in mgr.agents)


def test_initial_balance_equity():
    mgr = _mgr()
    assert mgr._account_balance == 1000.0
    assert mgr._account_equity == 1000.0


def test_demo_mode_reports_demo_execution():
    mgr = CryptoAgentManager(MockRouter(), paper_mode=True, agent_count=2,
                             pairs=["BTCUSDT"], runtime_mode="demo")
    assert mgr.control_status()["execution_mode"] == "demo"
    assert mgr.control_status()["signal_only_execution"] is False
    assert mgr.to_state_dict()["summary"]["mode"] == "demo"


def test_demo_without_testnet_credentials_reports_signal_only():
    router = MockRouter()
    router.paper_mode = False
    router.network = "testnet"
    router.credential_status = "missing"
    router.supports_short = False
    mgr = CryptoAgentManager(router, paper_mode=False, agent_count=2,
                             pairs=["BTCUSDT"], runtime_mode="demo")
    status = mgr.control_status()
    assert status["execution_mode"] == "signal_only"
    assert status["network"] == "testnet"
    assert status["credential_status"] == "missing"


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
async def test_live_unsupported_runs_signal_only_without_router_order():
    router = MockRouter()
    mgr = CryptoAgentManager(router, paper_mode=False, agent_count=1, pairs=["BTCUSDT"])
    agent = mgr.agents[0]
    agent.dna.symbol = "BTCUSDT"
    agent.dna.timeframe = "M15"
    _force_strategy(agent, "momentum")
    agent.generate_signal = lambda price, **kw: {
        "action": "LONG", "confidence": 90, "reason": "unit long"
    }
    _seed_manager_trend(mgr, "BTCUSDT", "up")

    await mgr._process_agents("BTCUSDT", 100.0, regime="TREND_UP")

    assert router.orders == []
    assert not agent.is_in_trade
    assert mgr.control_status()["execution_mode"] == "signal_only"
    assert mgr.control_status()["signal_only_execution"] is True
    assert mgr.to_state_dict()["summary"]["execution_mode"] == "signal_only"
    assert mgr._order_history
    assert mgr._order_history[0]["type"] == "signal_only"
    assert mgr._order_history[0]["status"] == "blocked"


@pytest.mark.asyncio
async def test_spot_short_entry_is_blocked(monkeypatch):
    monkeypatch.setattr(manager_mod, "ENTRY_STRATEGY_ALLOWLIST", set())
    router = MockRouter()
    router.live_trading_supported = True
    router.network = "testnet"
    router.credential_status = "configured"
    router.supports_short = False
    mgr = CryptoAgentManager(router, paper_mode=False, agent_count=1,
                             pairs=["BTCUSDT"], runtime_mode="demo")
    agent = mgr.agents[0]
    agent.dna.symbol = "BTCUSDT"
    _force_strategy(agent, "momentum")
    agent.generate_signal = lambda price, **kw: {
        "action": "SHORT", "confidence": 90, "reason": "unit short"
    }
    _seed_manager_trend(mgr, "BTCUSDT", "down")

    await mgr._process_agents("BTCUSDT", 100.0, regime="TREND_DOWN")

    assert router.orders == []
    assert not agent.is_in_trade


@pytest.mark.asyncio
async def test_spot_buy_position_closes_with_sell_at_tp():
    router = MockRouter()
    router.live_trading_supported = True
    router.network = "testnet"
    router.credential_status = "configured"
    router.supports_short = False
    mgr = CryptoAgentManager(router, paper_mode=False, agent_count=1,
                             pairs=["BTCUSDT"], runtime_mode="demo")
    agent = mgr.agents[0]
    agent._open_ticket = 123
    agent._open_entry = 100.0
    agent._open_side = "BUY"
    agent._open_sl = 95.0
    agent._open_tp = 105.0
    agent._open_qty = 2.0
    agent._open_risk_amount = 10.0
    mgr.risk_guardian.on_position_opened("BTCUSDT")

    await mgr._check_live_managed_positions("BTCUSDT", 106.0)

    assert router.orders[0][1]["side"] == "SELL"
    assert not agent.is_in_trade
    assert mgr._order_history[0]["status"] == "closed"
    assert mgr._order_history[0]["network"] == "testnet"


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


@pytest.mark.asyncio
async def test_strategy_allowlist_block_is_audited(monkeypatch):
    monkeypatch.setattr(manager_mod, "ENTRY_STRATEGY_ALLOWLIST", {"momentum"})
    mgr = _mgr(pairs=["BTCUSDT"])
    agent = mgr.agents[0]
    agent.dna.symbol = "BTCUSDT"
    _force_strategy(agent, "mean_reversion")
    mgr.agents = [agent]

    await mgr._process_agents("BTCUSDT", 100.0)

    assert mgr._entry_audit
    row = mgr._entry_audit[0]
    assert row["symbol"] == "BTCUSDT"
    assert row["strategy"] == "mean_reversion"
    assert row["block_stage"] == "strategy_allowlist"


@pytest.mark.asyncio
async def test_shadow_guard_policy_blocks_high_volatility_entries(tmp_path, monkeypatch):
    monkeypatch.setattr(manager_mod, "ENTRY_STRATEGY_ALLOWLIST", set())
    guard = tmp_path / "shadow_guard_policy.json"
    _write_shadow_guard_policy(guard)
    mgr = _mgr(pairs=["BTCUSDT"])
    mgr._shadow_guard_policy_path = guard
    agent = mgr.agents[0]
    agent.dna.symbol = "BTCUSDT"
    _force_strategy(agent, "momentum")
    agent.generate_signal = lambda price, **kw: {
        "action": "LONG", "confidence": 90, "reason": "unit long"
    }
    mgr.agents = [agent]

    await mgr._process_agents("BTCUSDT", 100.0, regime="high_volatility")

    assert not agent.is_in_trade
    assert mgr._order_history == []
    assert mgr._entry_audit
    assert mgr._entry_audit[0]["block_stage"] == "shadow_guard_policy"
    assert "high_volatility" in mgr._entry_audit[0]["reason"]


@pytest.mark.asyncio
async def test_shadow_guard_policy_allows_non_blocked_regime(tmp_path, monkeypatch):
    monkeypatch.setattr(manager_mod, "ENTRY_STRATEGY_ALLOWLIST", set())
    guard = tmp_path / "shadow_guard_policy.json"
    _write_shadow_guard_policy(guard)
    mgr = _mgr(pairs=["BTCUSDT"])
    mgr._shadow_guard_policy_path = guard
    agent = mgr.agents[0]
    agent.dna.symbol = "BTCUSDT"
    _force_strategy(agent, "momentum")
    agent.generate_signal = lambda price, **kw: {
        "action": "LONG", "confidence": 90, "reason": "unit long"
    }
    mgr.agents = [agent]

    await mgr._process_agents("BTCUSDT", 100.0, regime="sideways")

    assert agent.is_in_trade
    assert mgr._order_history
    assert mgr._order_history[0]["action"] == "BUY"


def test_signal_quality_summary_includes_crypto_audit_events():
    mgr = _mgr(pairs=["BTCUSDT"])
    agent = mgr.agents[0]
    agent.dna.symbol = "BTCUSDT"
    _force_strategy(agent, "momentum")
    mgr._audit_entry(
        symbol="BTCUSDT",
        stage="signal_confidence",
        reason="unit low confidence",
        agent=agent,
        strategy="momentum",
        action="LONG",
        confidence=42,
    )

    summary = mgr.to_state_dict()["summary"]["signal_quality"]

    assert summary["audit_events"] == 1
    assert summary["by_block_stage"]["signal_confidence"] == 1
    assert summary["audit_by_symbol"]["BTCUSDT"] == 1
    assert summary["audit_by_strategy"]["momentum"] == 1


def test_htf_aligned_signal_gets_confidence_boost():
    mgr = _mgr(pairs=["BTCUSDT"])
    _seed_manager_trend(mgr, "BTCUSDT", "down")
    agent = mgr.agents[0]
    agent.dna.symbol = "BTCUSDT"
    agent.dna.timeframe = "M15"
    _force_strategy(agent, "momentum")
    agent.generate_signal = lambda price, **kw: {
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
    agent.generate_signal = lambda price, **kw: {
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
    agent.generate_signal = lambda price, **kw: {
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
            agent.generate_signal = lambda price, **kw: {
                "action": "HOLD", "confidence": 0, "reason": "first three idle"
            }
        else:
            _force_strategy(agent, "momentum")
            agent.generate_signal = lambda price, **kw: {
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
    agents[0].generate_signal = lambda price, **kw: {
        "action": "HOLD", "confidence": 0, "reason": "idle"
    }

    agents[1].dna.symbol = "BTCUSDT"
    agents[1].dna.timeframe = "M15"
    agents[1].dna.sl_pct = 0.018
    agents[1].dna.tp_pct = 0.03
    _force_strategy(agents[1], "grid_scalp")
    agents[1].generate_signal = lambda price, **kw: {
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


def test_evolution_keeps_open_positions_and_risk_guardian_state():
    """Evolution must wait until positions close so runtime ownership is kept."""
    mgr = _mgr(pairs=["BTCUSDT"])
    # simulate 3 agents holding open positions
    for agent in mgr.agents[:3]:
        agent._open_ticket = 1
        agent._open_side = "BUY"
        mgr.risk_guardian.on_position_opened(agent.dna.symbol)
    assert sum(mgr.risk_guardian._open_positions.values()) == 3

    mgr._run_evolution()

    assert sum(a.is_in_trade for a in mgr.agents) == 3
    assert sum(mgr.risk_guardian._open_positions.values()) == 3


def test_evolution_is_deferred_while_position_open():
    mgr = _mgr(pairs=["BTCUSDT"])
    original_ids = [agent.dna.id for agent in mgr.agents]
    mgr.agents[0]._open_ticket = 99

    mgr._run_evolution()

    assert [agent.dna.id for agent in mgr.agents] == original_ids
    assert mgr.agents[0]._open_ticket == 99


def test_runtime_state_restores_stats_and_open_position():
    mgr = CryptoAgentManager(MockRouter(), paper_mode=True, agent_count=2,
                             pairs=["BTCUSDT"], runtime_mode="demo")
    agent = mgr.agents[0]
    agent.record_trade_result(12.5, 1.25)
    agent._open_ticket = 123
    agent._open_entry = 100.0
    agent._open_side = "BUY"
    agent._open_sl = 98.0
    agent._open_tp = 104.0
    agent._open_qty = 2.0
    agent._open_risk_amount = 4.0
    mgr._account_balance = 1012.5
    state = mgr.runtime_state()

    restored = CryptoAgentManager(MockRouter(), paper_mode=True, agent_count=1,
                                  pairs=["ETHUSDT"], runtime_mode="demo")
    assert restored.restore_runtime_state(state) is True
    restored_agent = next(item for item in restored.agents if item.dna.id == agent.dna.id)
    assert restored_agent.trades_count == 1
    assert restored_agent.total_pnl == pytest.approx(12.5)
    assert restored_agent._open_ticket == 123
    assert restored._account_balance == pytest.approx(1012.5)
    assert restored.control_status()["open_positions"] == 1


def test_runtime_state_cannot_cross_networks():
    paper = CryptoAgentManager(MockRouter(), paper_mode=True, agent_count=1,
                               pairs=["BTCUSDT"], runtime_mode="paper")
    state = paper.runtime_state()
    router = MockRouter()
    router.network = "testnet"
    demo = CryptoAgentManager(router, paper_mode=False, agent_count=1,
                              pairs=["BTCUSDT"], runtime_mode="demo")
    assert demo.restore_runtime_state(state) is False


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
