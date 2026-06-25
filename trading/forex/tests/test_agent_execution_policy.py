from types import SimpleNamespace
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from engine.agent_execution_policy import AgentExecutionPolicy


def make_agent(agent_id, symbol, timeframe, strategy, pnl=0.0, losses=0):
    weights = {
        "momentum": 0.05,
        "breakout_atr": 0.05,
        "market_structure": 0.05,
        "mean_reversion": 0.05,
    }
    weights[strategy] = 0.8
    agent = SimpleNamespace(
        dna=SimpleNamespace(
            id=agent_id,
            name=f"FX-{symbol[:3]}-{agent_id:03d}",
            symbol=symbol,
            timeframe=timeframe,
            strategy_weights=weights,
        ),
        trades_count=4,
        wins=2,
        losses=2,
        total_pnl=pnl,
        win_rate=0.5,
        _consecutive_losses=losses,
    )
    return agent


def test_policy_selects_one_executor_per_symbol_by_default(monkeypatch):
    monkeypatch.delenv("AGENT_EXECUTORS_PER_SYMBOL", raising=False)
    policy = AgentExecutionPolicy()
    agents = [
        make_agent(1, "GBPUSDm", "H1", "momentum"),
        make_agent(2, "GBPUSDm", "M15", "breakout_atr"),
        make_agent(3, "GBPUSDm", "M15", "mean_reversion"),
    ]

    selection = policy.select("GBPUSDm", agents, max_agents=3)

    assert selection["executor_limit"] == 1
    assert len(selection["executors"]) == 1
    assert len(selection["observers"]) == 2
    assert policy.permission_for(selection, agents[0]).allowed is True
    assert policy.permission_for(selection, agents[1]).role == "observer"
    assert "allowlist" in selection["observers"][0]["reason"]


def test_policy_prefers_symbol_timeframe_and_safer_strategy(monkeypatch):
    monkeypatch.setenv("AGENT_EXECUTORS_PER_SYMBOL", "1")
    policy = AgentExecutionPolicy()
    wrong_tf = make_agent(1, "XAUUSDm", "M15", "momentum", pnl=5.0)
    preferred_tf = make_agent(2, "XAUUSDm", "H1", "breakout_atr")
    martingale_like = make_agent(3, "XAUUSDm", "H1", "mean_reversion", losses=3)

    selection = policy.select("XAUUSDm", [wrong_tf, preferred_tf, martingale_like], max_agents=3)

    assert selection["executors"][0]["name"] == wrong_tf.dna.name
    assert policy.permission_for(selection, wrong_tf).allowed is True
    assert policy.permission_for(selection, preferred_tf).allowed is False
    assert policy.permission_for(selection, martingale_like).allowed is False


def test_policy_can_be_disabled_for_legacy_max_agent_behavior(monkeypatch):
    monkeypatch.setenv("AGENT_EXECUTION_POLICY_ENABLED", "false")
    policy = AgentExecutionPolicy()
    agents = [
        make_agent(1, "EURUSDm", "M15", "momentum"),
        make_agent(2, "EURUSDm", "H1", "breakout_atr"),
        make_agent(3, "EURUSDm", "H4", "market_structure"),
    ]

    selection = policy.select("EURUSDm", agents, max_agents=2)

    assert selection["enabled"] is False
    assert len(selection["executors"]) == 2
    assert sum(1 for agent in agents if policy.permission_for(selection, agent).allowed) == 2
