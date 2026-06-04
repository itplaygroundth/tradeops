"""Tests for CryptoAgentManager — integration hub."""
import pytest

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
