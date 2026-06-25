import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from engine.agent_manager import ForexAgentManager
from mt5_bridge.client import MT5Client


def _write_shadow_guard_policy(path: Path) -> None:
    path.write_text(json.dumps({
        "mode": "shadow_with_regime_no_trade_guard",
        "no_trade_regimes": ["high_volatility"],
        "enforcement": {
            "block_new_entries_when_regime_in": ["high_volatility"],
        },
    }))


def test_shadow_guard_policy_blocks_high_volatility_entries(tmp_path):
    policy_path = tmp_path / "shadow_guard_policy.json"
    _write_shadow_guard_policy(policy_path)

    manager = ForexAgentManager(MT5Client(), paper_mode=True, agent_count=1)
    manager._shadow_guard_policy_path = policy_path
    symbol = manager.agents[0].dna.symbol

    asyncio.run(manager._process_agents(symbol, 1.0850, regime="high_volatility"))

    assert all(not agent.is_in_trade for agent in manager.agents)
    assert manager._entry_audit[0]["block_stage"] == "shadow_guard_policy"
    assert manager._entry_audit[0]["symbol"] == symbol
    assert manager._entry_audit[0]["signal"]["regime"] == "high_volatility"


def test_shadow_guard_policy_allows_non_blocked_regime(tmp_path):
    policy_path = tmp_path / "shadow_guard_policy.json"
    _write_shadow_guard_policy(policy_path)

    manager = ForexAgentManager(MT5Client(), paper_mode=True, agent_count=1)
    manager._shadow_guard_policy_path = policy_path

    decision = manager._shadow_guard_decision(manager.agents[0].dna.symbol, regime="sideways")

    assert decision["allowed"] is True
    assert "allowed" in decision["reason"]
