import pytest
import sys
import os
import json
import time
from pathlib import Path

# Add src to python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from engine.dna import create_population, random_dna, FOREX_SYMBOLS
from engine.agent import ForexAgent
from engine.agent_manager import ForexAgentManager, STATE_FILE
from engine.evolution import evolve
from mt5_bridge.client import MT5Client, Tick

def test_population_creation():
    pop = create_population(25)
    assert len(pop) == 25
    
    # Verify that agents are distributed across all symbols
    symbols_in_pop = {dna.symbol for dna in pop}
    for sym in FOREX_SYMBOLS:
        assert sym in symbols_in_pop

def test_agent_signal_generation():
    pop = create_population(5)
    from engine.signals import ForexSignalEngine
    from engine.risk_guardian import ForexRiskGuardian
    
    se = ForexSignalEngine()
    rg = ForexRiskGuardian()
    
    # Add some dummy prices to signal history so technical signals work
    for sym in FOREX_SYMBOLS:
        for i in range(50):
            se.record_tick(sym, 1.0850 + (i % 10 - 5) * 0.0001, timestamp=time.time() + i)
            
    for dna in pop:
        agent = ForexAgent(dna, se, rg, paper_mode=True)
        sig = agent.generate_signal(1.0850)
        assert "action" in sig
        assert "confidence" in sig
        assert sig["action"] in ("LONG", "SHORT", "HOLD")

def test_evolution_uniqueness_and_coverage():
    pop_dnas = create_population(25)
    
    # Mock stats
    agent_stats = []
    for dna in pop_dnas:
        # Give them 35 trades so they are judged and not just protected
        agent_stats.append({
            "id": dna.id,
            "name": dna.name,
            "symbol": dna.symbol,
            "trades": 35,
            "win_rate": 60.0,
            "total_pnl": 150.0,
            "total_pnl_pct": 15.0,
            "strategy_weights": dna.strategy_weights
        })
        
    new_dnas, next_id = evolve(pop_dnas, agent_stats, 25)
    
    assert len(new_dnas) == 25
    
    # ID uniqueness check
    ids = [dna.id for dna in new_dnas]
    assert len(ids) == len(set(ids))
    
    # Symbol coverage check
    symbols_in_pop = {dna.symbol for dna in new_dnas}
    for sym in FOREX_SYMBOLS:
        assert sym in symbols_in_pop

def test_paper_trading_execution_and_sl_tp():
    import asyncio
    asyncio.run(_async_paper_trading_test())


def test_agent_processing_uses_per_symbol_tick_counts():
    import asyncio
    asyncio.run(_async_agent_processing_uses_per_symbol_tick_counts())


def test_daily_profit_target_reached_uses_today_pnl():
    client = MT5Client()
    manager = ForexAgentManager(client, paper_mode=True, agent_count=8)
    now = time.time()
    today = time.strftime("%Y-%m-%d", time.localtime(now))
    yesterday = time.strftime("%Y-%m-%d", time.localtime(now - 86400))

    manager._daily_pnl = {yesterday: 100.0}
    assert manager._daily_profit_target_reached(now) is False

    manager._daily_pnl[today] = 19.99
    assert manager._daily_profit_target_reached(now) is False

    manager._daily_pnl[today] = 20.0
    assert manager._daily_profit_target_reached(now) is True


def test_recent_history_backfills_daily_realized_pnl(monkeypatch):
    import asyncio
    asyncio.run(_async_recent_history_backfills_daily_realized_pnl(monkeypatch))


async def _async_recent_history_backfills_daily_realized_pnl(monkeypatch):
    from storage import history_db

    now = int(time.time())

    class HistoryClient(MT5Client):
        async def get_recent_deals(self, hours=24, limit=200):
            return [
                {
                    "ticket": 101,
                    "position": 5001,
                    "time": now,
                    "entry": 1,
                    "comment": "MTAI",
                    "symbol": "EURUSDm",
                    "volume": 0.01,
                    "price": 1.1,
                    "profit": 12.5,
                    "commission": -0.1,
                    "swap": -0.05,
                },
                {
                    "ticket": 102,
                    "position": 5002,
                    "time": now,
                    "entry": 0,
                    "comment": "MTAI",
                    "symbol": "EURUSDm",
                    "volume": 0.01,
                    "price": 1.1,
                    "profit": 99.0,
                    "commission": 0.0,
                    "swap": 0.0,
                },
            ]

    monkeypatch.setattr(history_db, "upsert_order", lambda entry: True)
    manager = ForexAgentManager(HistoryClient(), paper_mode=True, agent_count=8)
    await manager._load_recent_history(hours=48, limit=10)

    today = time.strftime("%Y-%m-%d", time.localtime(now))
    assert manager._daily_pnl[today] == 12.35


async def _async_agent_processing_uses_per_symbol_tick_counts():
    client = MT5Client()
    manager = ForexAgentManager(client, paper_mode=True, agent_count=8)
    processed = []

    async def fake_process(symbol, price):
        processed.append((symbol, price))

    manager._process_agents = fake_process

    for _ in range(9):
        await manager.on_tick({"symbol": "EURUSDm", "price": 1.1000, "volume": 1.0})
        await manager.on_tick({"symbol": "GBPUSDm", "price": 1.2500, "volume": 1.0})

    assert processed == []

    await manager.on_tick({"symbol": "EURUSDm", "price": 1.1010, "volume": 1.0})
    assert processed == [("EURUSDm", 1.1010)]

    await manager.on_tick({"symbol": "GBPUSDm", "price": 1.2510, "volume": 1.0})
    assert processed == [("EURUSDm", 1.1010), ("GBPUSDm", 1.2510)]


async def _async_paper_trading_test():
    # Remove state file if exists
    if STATE_FILE.exists():
        STATE_FILE.unlink()
        
    client = MT5Client()
    manager = ForexAgentManager(client, paper_mode=True, agent_count=8)
    
    # Seed prices for all symbols
    for sym in FOREX_SYMBOLS:
        for i in range(50):
            manager.signal_engine.record_tick(sym, 1.0000, timestamp=time.time() + i)
            
    # Force one agent to trigger a LONG signal with guaranteed R:R >= 2.0
    target_agent = manager.agents[0]
    target_symbol = target_agent.dna.symbol
    target_agent.dna.strategy_weights = {"momentum": 1.0, "mean_reversion": 0.0, "grid_scalp": 0.0, "llm_sentiment": 0.0}
    # Force sl/tp so R:R = 35/15 = 2.33 > MIN_RR_RATIO (2.0) — random DNA can give 1.5 which fails
    target_agent.dna.sl_pips = 15.0
    target_agent.dna.tp_pips = 35.0
    
    # Mock technical_signal to return LONG
    import engine.signals
    old_tech_signal = manager.signal_engine.technical_signal
    manager.signal_engine.technical_signal = lambda sym: {"action": "LONG", "confidence": 90, "reason": "test"}
    
    # Mock is_good_session to return True so session block is bypassed
    old_is_good = engine.signals.is_good_session
    engine.signals.is_good_session = lambda sym: True

    try:
        # Trigger agents processing
        # Tick count mod 10 triggers processing
        manager._tick_count = 9  # next tick makes it 10
        await manager.on_tick({"symbol": target_symbol, "price": 1.0000, "volume": 1.0})
        
        # Verify position is opened
        assert target_agent.is_in_trade is True
        assert target_agent._open_side == "BUY"
        assert target_agent._open_entry == 1.0000
        assert target_agent._open_sl < 1.0000
        assert target_agent._open_tp > 1.0000
        
        # Now trigger SL hit by feeding a very low price
        low_price = target_agent._open_sl - 0.0001
        await manager.on_tick({"symbol": target_symbol, "price": low_price, "volume": 1.0})
        
        # Verify position is closed
        assert target_agent.is_in_trade is False
        assert target_agent.trades_count == 1
        assert target_agent.losses == 1
        assert target_agent.total_pnl < 0
        
        # Force state write (normally triggered at tick % 30; skip that in 2-tick test)
        manager._write_state()
        
        # Verify state file was written with correct data
        assert STATE_FILE.exists()
        with open(STATE_FILE, "r") as f:
            state_data = json.load(f)
            assert state_data["paper_mode"] is True
            assert state_data["account"]["balance"] < 1000.0
            
    finally:
        # Restore mocks
        manager.signal_engine.technical_signal = old_tech_signal
        engine.signals.is_good_session = old_is_good
        if STATE_FILE.exists():
            STATE_FILE.unlink()


def test_write_state_preserves_competition_leaderboard(monkeypatch, tmp_path):
    import engine.agent_manager as manager_mod
    state_file = tmp_path / "live_state.json"
    monkeypatch.setattr(manager_mod, "STATE_FILE", state_file)
    client = MT5Client()
    manager = manager_mod.ForexAgentManager(client, paper_mode=True, agent_count=8)
    entry = {
        "symbol": "EURUSDm",
        "regime": "RANGING",
        "winner_sharpe": 1.2,
        "winner_config": {"momentum": 1.0},
        "leader_score": 1.42,
        "selection_source": "hermes",
        "llm_error": "",
        "deterministic_winner_idx": 0,
        "llm_winner_idx": 0,
        "proposal_status": "none",
        "proposal_reason": "",
        "proposal_source": "",
        "approved": True,
        "applied": True,
        "forward_pnl": 0.3,
        "timestamp": time.time(),
    }
    manager._merge_competition_summary({}, entry)
    state_file.write_text(json.dumps({"summary": {
        "last_competition": entry,
        "competition_history": [entry],
        "competition_by_symbol": {"EURUSDm": entry},
        "best_leader_asset": entry,
    }}))

    try:
        manager._write_state()
        state_data = json.loads(state_file.read_text())
        summary = state_data["summary"]
        assert summary["last_competition"]["symbol"] == "EURUSDm"
        assert summary["competition_history"][0]["symbol"] == "EURUSDm"
        assert summary["competition_by_symbol"]["EURUSDm"]["applied"] is True
        assert summary["best_leader_asset"]["leader_score"] == 1.42
    finally:
        if state_file.exists():
            state_file.unlink()


def test_write_state_is_atomic(monkeypatch, tmp_path):
    """State writes leave no .tmp leftover and always produce valid JSON."""
    import engine.agent_manager as manager_mod
    state_file = tmp_path / "live_state.json"
    monkeypatch.setattr(manager_mod, "STATE_FILE", state_file)
    client = MT5Client()
    manager = manager_mod.ForexAgentManager(client, paper_mode=True, agent_count=8)

    manager._write_state()

    assert state_file.exists()
    json.loads(state_file.read_text())  # complete, parseable
    assert not state_file.with_suffix(state_file.suffix + ".tmp").exists()


class FakeExitClient:
    def __init__(self, tick):
        self.tick = tick
        self.closed = []
        self.modified = []

    async def get_price(self, symbol):
        return self.tick

    async def close_position(self, ticket):
        self.closed.append(ticket)
        return {"closed": ticket}

    async def modify_position(self, ticket, sl=0, tp=0):
        self.modified.append({"ticket": ticket, "sl": sl, "tp": tp})
        return {"ticket": ticket, "sl": sl, "tp": tp}


class FakeAccountRiskClient:
    def __init__(self):
        self.closed = []
        self.account = {"balance": 1000.0, "equity": 920.0, "margin": 10.0, "currency": "USD"}
        self.positions = [
            {"ticket": 11, "symbol": "GBPUSDm", "type": "BUY", "magic": 20260101, "profit": -80.0},
            {"ticket": 22, "symbol": "GBPUSDm", "type": "BUY", "magic": 0, "profit": -5.0},
        ]

    async def get_account(self):
        return self.account

    async def get_positions(self):
        return self.positions

    async def close_position(self, ticket):
        self.closed.append(ticket)
        return {"closed": ticket}


class FakeDedupClient:
    def __init__(self):
        self.placed = []
        self.account = {"balance": 1000.0, "equity": 1000.0, "margin": 1.0, "currency": "USD"}
        self.positions = [
            {"ticket": 33, "symbol": "GBPUSDm", "type": "BUY", "magic": 20260101, "profit": 0.0},
        ]

    async def get_account(self):
        return self.account

    async def get_positions(self):
        return list(self.positions)

    async def place_order(self, **kwargs):
        self.placed.append(kwargs)
        return {"order_id": 44, "price": 1.2000}


def test_position_dedup_blocks_duplicate_live_entry(monkeypatch):
    import asyncio
    asyncio.run(_async_position_dedup_blocks_duplicate_live_entry(monkeypatch))


async def _async_position_dedup_blocks_duplicate_live_entry(monkeypatch):
    client = FakeDedupClient()
    manager = ForexAgentManager(client, paper_mode=False, agent_count=8)
    monkeypatch.setattr(manager.performance_guard, "evaluate", lambda symbol, agent: type("D", (), {"allowed": True})())
    manager.leader_asset_supervisor.read_latest_proposal = lambda: None
    agent = manager.agents[0]
    agent.dna.symbol = "GBPUSDm"
    agent.dna.sl_pips = 15
    agent.dna.tp_pips = 35
    agent.generate_signal = lambda price: {"action": "LONG", "confidence": 90, "reason": "test"}

    await manager._process_agents("GBPUSDm", 1.2000)

    assert client.placed == []
    assert agent._open_ticket is None


def test_account_risk_hard_stop_closes_only_managed_positions(tmp_path):
    import asyncio
    asyncio.run(_async_account_risk_hard_stop_test(tmp_path))


async def _async_account_risk_hard_stop_test(tmp_path):
    client = FakeAccountRiskClient()
    manager = ForexAgentManager(client, paper_mode=False, agent_count=8)
    manager.account_risk_monitor.state_file = tmp_path / "risk_state.json"
    manager.account_risk_monitor.reset(equity=1000.0, current_day=int(time.time() / 86400))

    state = await manager._refresh_account_risk()

    assert state.mode == "HARD_STOP"
    assert client.closed == [11]
    assert manager.risk_guardian._open_positions == 1


def test_live_exit_management_soft_tp_uses_close_side_price():
    import asyncio
    asyncio.run(_async_soft_tp_close_side_test())


async def _async_soft_tp_close_side_test():
    client = FakeExitClient(Tick("GBPUSDm", bid=1.1999, ask=1.2000, mid=1.19995, timestamp=time.time()))
    manager = ForexAgentManager(client, paper_mode=False, agent_count=8)
    agent = manager.agents[0]
    agent.dna.symbol = "GBPUSDm"
    agent._open_ticket = 123
    agent._open_entry = 1.2050
    agent._open_side = "SELL"
    agent._open_sl = 1.2070
    agent._open_tp = 1.1999

    await manager._apply_live_exit_management([
        {"ticket": 123, "symbol": "GBPUSDm", "type": "SELL", "price_open": 1.2050, "sl": 1.2070, "tp": 1.1999}
    ])

    assert client.closed == [123]
    assert client.modified == []


def test_live_exit_management_trailing_stop_only_improves_sl():
    import asyncio
    asyncio.run(_async_trailing_stop_test())


async def _async_trailing_stop_test():
    client = FakeExitClient(Tick("GBPUSDm", bid=1.2030, ask=1.2031, mid=1.20305, timestamp=time.time()))
    manager = ForexAgentManager(client, paper_mode=False, agent_count=8)
    agent = manager.agents[0]
    agent.dna.symbol = "GBPUSDm"
    agent._open_ticket = 456
    agent._open_entry = 1.2000
    agent._open_side = "BUY"
    agent._open_sl = 1.1980
    agent._open_tp = 1.2100

    await manager._apply_live_exit_management([
        {"ticket": 456, "symbol": "GBPUSDm", "type": "BUY", "price_open": 1.2000, "sl": 1.1980, "tp": 1.2100}
    ])

    assert client.closed == []
    assert len(client.modified) == 1
    assert client.modified[0]["ticket"] == 456
    assert client.modified[0]["sl"] > 1.1980
    assert client.modified[0]["tp"] == 1.2100


def test_best_leader_asset_prioritizes_forward_pnl(monkeypatch, tmp_path):
    import engine.agent_manager as manager_mod
    state_file = tmp_path / "live_state.json"
    monkeypatch.setattr(manager_mod, "STATE_FILE", state_file)
    manager = manager_mod.ForexAgentManager(MT5Client(), paper_mode=True, agent_count=8)

    high_sharpe_low_forward = {
        "symbol": "USDJPYm",
        "regime": "RANGING",
        "winner_sharpe": 5.0,
        "winner_config": {"momentum": 1.0},
        "leader_score": 0.005,
        "selection_source": "deterministic",
        "llm_error": "",
        "deterministic_winner_idx": 0,
        "llm_winner_idx": None,
        "proposal_status": "none",
        "proposal_reason": "",
        "proposal_source": "",
        "approved": True,
        "applied": True,
        "forward_pnl": 0.0001,
        "timestamp": time.time(),
    }
    lower_sharpe_better_forward = dict(high_sharpe_low_forward)
    lower_sharpe_better_forward.update({
        "symbol": "EURUSDm",
        "winner_sharpe": 0.0,
        "leader_score": 0.01,
        "forward_pnl": 0.01,
        "timestamp": time.time() + 1,
    })

    state = {}
    manager._merge_competition_summary(state, high_sharpe_low_forward)
    manager._merge_competition_summary(state, lower_sharpe_better_forward)

    assert state["summary"]["best_leader_asset"]["symbol"] == "EURUSDm"


def test_leader_asset_supervisor_schedule_writes_summary(monkeypatch, tmp_path):
    import asyncio
    import engine.agent_manager as manager_mod

    state_file = tmp_path / "live_state.json"
    proposal_path = tmp_path / "leader_asset_proposals.json"
    monkeypatch.setattr(manager_mod, "STATE_FILE", state_file)
    monkeypatch.setenv("LEADER_ASSET_STATE_PATH", str(state_file))
    monkeypatch.setenv("LEADER_ASSET_PROPOSAL_PATH", str(proposal_path))
    monkeypatch.setenv("LEADER_ASSET_MIN_SAMPLES", "1")
    monkeypatch.setenv("LEADER_ASSET_SUPERVISOR_INTERVAL", "0")

    async def run_case():
        manager = manager_mod.ForexAgentManager(MT5Client(), paper_mode=True, agent_count=8)
        now = time.time()
        entry = {
            "symbol": "EURUSDm",
            "regime": "RANGING",
            "winner_sharpe": 0.0,
            "winner_config": {"momentum": 1.0},
            "leader_score": 0.02,
            "selection_source": "deterministic",
            "llm_error": "",
            "deterministic_winner_idx": 0,
            "llm_winner_idx": None,
            "proposal_status": "none",
            "proposal_reason": "",
            "proposal_source": "",
            "approved": True,
            "applied": True,
            "forward_pnl": 0.02,
            "timestamp": now,
        }
        state = {}
        manager._merge_competition_summary(state, entry)
        state_file.write_text(json.dumps(state))
        manager._schedule_leader_asset_supervisor()
        await manager._leader_asset_supervisor_task
        written = json.loads(state_file.read_text())
        proposal = written["summary"]["leader_asset_supervisor"]
        assert proposal["leader_asset"] == "EURUSDm"
        assert proposal["status"] == "accepted"
        assert proposal_path.exists()

    asyncio.run(run_case())


def test_leader_asset_gate_defaults_until_proposal_accepted(monkeypatch, tmp_path):
    import engine.agent_manager as manager_mod

    proposal_path = tmp_path / "leader_asset_proposals.json"
    monkeypatch.setenv("LEADER_ASSET_PROPOSAL_PATH", str(proposal_path))
    manager = manager_mod.ForexAgentManager(MT5Client(), paper_mode=True, agent_count=8)

    assert manager._leader_asset_gate("EURUSDm")["max_agents"] == 3

    proposal_path.write_text(json.dumps({"proposals": [{
        "status": "insufficient_samples",
        "leader_asset": "GBPUSDm",
        "confidence": 0.54,
        "reason": "samples 1 below 3",
    }]}))

    gate = manager._leader_asset_gate("EURUSDm")
    assert gate["max_agents"] == 3
    assert gate["min_confidence"] == 50
    assert gate["status"] == "insufficient_samples"


def test_leader_asset_gate_prioritizes_accepted_leader(monkeypatch, tmp_path):
    import engine.agent_manager as manager_mod

    proposal_path = tmp_path / "leader_asset_proposals.json"
    monkeypatch.setenv("LEADER_ASSET_PROPOSAL_PATH", str(proposal_path))
    proposal_path.write_text(json.dumps({"proposals": [{
        "status": "accepted",
        "leader_asset": "GBPUSDm",
        "confidence": 0.82,
        "reason": "GBPUSDm leads",
    }]}))
    manager = manager_mod.ForexAgentManager(MT5Client(), paper_mode=True, agent_count=8)

    leader_gate = manager._leader_asset_gate("GBPUSDm")
    other_gate = manager._leader_asset_gate("EURUSDm")

    assert leader_gate["is_leader"] is True
    assert leader_gate["min_confidence"] == 50
    assert leader_gate["max_agents"] == 3
    assert other_gate["is_leader"] is False
    assert other_gate["min_confidence"] == 65
    assert other_gate["max_agents"] == 1


def test_agent_max_dd_tracks_drawdown_from_peak():
    from engine.signals import ForexSignalEngine
    from engine.risk_guardian import ForexRiskGuardian
    dna = random_dna(1, "EURUSDm")
    agent = ForexAgent(dna, ForexSignalEngine(), ForexRiskGuardian())
    agent.record_trade_result(100.0, 10.0)   # peak equity 1100
    agent.record_trade_result(-50.0, -5.0)
    agent.record_trade_result(-50.0, -5.0)   # equity 1000
    expected = (1100.0 - 1000.0) / 1100.0 * 100
    assert abs(agent.max_dd_pct - expected) < 1e-9


def test_agent_max_dd_never_shrinks_and_expectancy():
    from engine.signals import ForexSignalEngine
    from engine.risk_guardian import ForexRiskGuardian
    dna = random_dna(2, "EURUSDm")
    agent = ForexAgent(dna, ForexSignalEngine(), ForexRiskGuardian())
    assert agent.max_dd_pct == 0.0 and agent.expectancy_pct == 0.0
    agent.record_trade_result(100.0, 10.0)
    agent.record_trade_result(-100.0, -10.0)
    dd_at_bottom = agent.max_dd_pct
    agent.record_trade_result(200.0, 20.0)
    assert agent.max_dd_pct == dd_at_bottom
    assert abs(agent.expectancy_pct - (20.0 / 3)) < 1e-9
    assert agent.gross_profit == 300.0
    assert agent.gross_loss == 100.0
    d = agent.to_dict()
    assert "max_dd_pct" in d and "expectancy_pct" in d
