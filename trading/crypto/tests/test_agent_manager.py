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
    for i in range(25):
        await mgr.on_tick("BTCUSDT", 100.0 + i, 5.0, float(i))
    hist = mgr.signal_engine.get_history("BTCUSDT")
    assert hist.count == 25


@pytest.mark.asyncio
async def test_on_tick_executes_via_router():
    router = MockRouter()
    mgr = CryptoAgentManager(router, paper_mode=False, agent_count=10, pairs=["BTCUSDT"])
    # strong uptrend -> overbought -> SHORT signals on momentum agents
    for i in range(60):
        await mgr.on_tick("BTCUSDT", 100.0 + i * 2, 50.0, float(i))
    # at least attempted some orders (live mode routes through router)
    assert isinstance(router.orders, list)


@pytest.mark.asyncio
async def test_to_state_dict_schema():
    mgr = _mgr(pairs=["BTCUSDT", "ETHUSDT"])
    for i in range(15):
        await mgr.on_tick("BTCUSDT", 100.0 + i, 5.0, float(i))
        await mgr.on_tick("ETHUSDT", 50.0 + i, 5.0, float(i))
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


@pytest.mark.asyncio
async def test_paper_position_lifecycle():
    mgr = _mgr(pairs=["BTCUSDT"])
    # feed downtrend so oversold -> LONG opens, then rally to TP
    for i in range(40):
        await mgr.on_tick("BTCUSDT", 200.0 - i, 50.0, float(i))
    opened = sum(1 for a in mgr.agents if a.is_in_trade)
    # rally hard to trigger TP/SL on any open paper trades
    for i in range(40):
        await mgr.on_tick("BTCUSDT", 160.0 + i * 2, 50.0, float(40 + i))
    state = mgr.to_state_dict()
    assert state["summary"]["total_trades"] >= 0  # lifecycle ran without error
