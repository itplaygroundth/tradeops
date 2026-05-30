"""Integration tests for AssetLeader 4-phase competition."""
import asyncio
import sys
import time
import math
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from engine.asset_leader import AssetLeader, CompetitionResult
from engine.sub_agent import BacktestResult, ForwardTestResult


def make_candles(n=200):
    now = time.time()
    return [
        {
            "open": 1.1 + math.sin(i * 0.15) * 0.003,
            "high": 1.1 + math.sin(i * 0.15) * 0.003 + 0.0003,
            "low": 1.1 + math.sin(i * 0.15) * 0.003 - 0.0003,
            "close": 1.1 + math.sin(i * 0.15) * 0.003,
            "volume": 1000,
            "timestamp": now + i * 60,
        }
        for i in range(n)
    ]


def make_mock_mt5(candles):
    """MT5 client that returns candles and prices."""
    mt5 = MagicMock()
    mt5.get_ohlcv = AsyncMock(return_value=candles)
    mt5.get_price = AsyncMock(return_value=1.1050)
    return mt5


def make_mock_hermes(winner_idx=0, approved=True):
    """Hermes client that returns predictable responses."""
    h = MagicMock()
    h.select_winner = AsyncMock(return_value={
        "winner_idx": winner_idx,
        "reasoning": "Highest Sharpe with good win rate",
        "confidence": 0.85,
    })
    h.verify_forward_test = AsyncMock(return_value={
        "approved": approved,
        "apply_config": {"momentum": 0.6, "mean_reversion": 0.1, "grid_scalp": 0.1,
                         "llm_sentiment": 0.05, "order_flow": 0.05, "breakout_atr": 0.05,
                         "session_open": 0.05, "market_structure": 0.0},
        "reason": "Positive PnL, drawdown within limits",
    })
    return h


@patch("engine.sub_agent.SubAgent.run_forward_test")
def test_competition_returns_result(mock_run_forward):
    """run_competition must return a CompetitionResult with correct fields."""
    mock_run_forward.return_value = ForwardTestResult(0.15, 0.0, 3, 0.15)
    candles = make_candles()
    mt5 = make_mock_mt5(candles)
    hermes = make_mock_hermes(winner_idx=0, approved=True)
    production_agent = MagicMock()
    production_agent.update_strategy_weights = AsyncMock()

    leader = AssetLeader("EURUSDm", production_agent, mt5, hermes)
    result = asyncio.run(leader.run_competition())

    assert isinstance(result, CompetitionResult)
    assert result.symbol == "EURUSDm"
    assert isinstance(result.winner_config, dict)
    assert isinstance(result.winner_sharpe, float)
    assert isinstance(result.hermes_reasoning, str)
    assert 0.0 <= result.hermes_confidence <= 1.0
    assert isinstance(result.forward_pnl, float)
    assert isinstance(result.approved, bool)
    assert isinstance(result.applied, bool)
    assert result.timestamp > 0


@patch("engine.sub_agent.SubAgent.run_forward_test")
def test_competition_hermes_selects_winner(mock_run_forward):
    """Hermes winner_idx is respected when valid."""
    mock_run_forward.return_value = ForwardTestResult(0.15, 0.0, 3, 0.15)
    candles = make_candles()
    mt5 = make_mock_mt5(candles)
    hermes = make_mock_hermes(winner_idx=3, approved=True)
    production_agent = MagicMock()
    production_agent.update_strategy_weights = AsyncMock()

    leader = AssetLeader("EURUSDm", production_agent, mt5, hermes)
    result = asyncio.run(leader.run_competition())

    assert result.hermes_reasoning == "Highest Sharpe with good win rate"
    assert result.hermes_confidence == 0.85


@patch("engine.sub_agent.SubAgent.run_forward_test")
def test_competition_approved_applies_winner(mock_run_forward):
    """When Hermes approves, production agent's update_strategy_weights is called."""
    mock_run_forward.return_value = ForwardTestResult(0.15, 0.0, 3, 0.15)
    candles = make_candles()
    mt5 = make_mock_mt5(candles)
    hermes = make_mock_hermes(approved=True)
    production_agent = MagicMock()
    production_agent.update_strategy_weights = AsyncMock()

    leader = AssetLeader("EURUSDm", production_agent, mt5, hermes)
    result = asyncio.run(leader.run_competition())

    assert result.approved is True
    assert result.applied is True
    production_agent.update_strategy_weights.assert_called_once()


@patch("engine.sub_agent.SubAgent.run_forward_test")
def test_competition_rejected_does_not_apply(mock_run_forward):
    """When Hermes rejects, production agent is not updated."""
    mock_run_forward.return_value = ForwardTestResult(0.15, 0.0, 3, 0.15)
    candles = make_candles()
    mt5 = make_mock_mt5(candles)
    hermes = make_mock_hermes(approved=False)
    production_agent = MagicMock()
    production_agent.update_strategy_weights = AsyncMock()

    leader = AssetLeader("EURUSDm", production_agent, mt5, hermes)
    result = asyncio.run(leader.run_competition())

    assert result.approved is False
    assert result.applied is False
    production_agent.update_strategy_weights.assert_not_called()


@patch("engine.sub_agent.SubAgent.run_forward_test")
def test_competition_hermes_unreachable_fallback(mock_run_forward):
    """When Hermes is None, competition falls back to top-Sharpe algorithmic selection."""
    mock_run_forward.return_value = ForwardTestResult(0.15, 0.0, 3, 0.15)
    candles = make_candles()
    mt5 = make_mock_mt5(candles)

    leader = AssetLeader("EURUSDm", None, mt5, None)
    result = asyncio.run(leader.run_competition())

    # should not crash; approved=False when hermes unavailable
    assert isinstance(result, CompetitionResult)
    assert result.approved is False
    assert result.applied is False


@patch("engine.sub_agent.SubAgent.run_forward_test")
def test_competition_mt5_offline_graceful(mock_run_forward):
    """When MT5 is None (no candles), competition should return empty result gracefully."""
    mock_run_forward.return_value = ForwardTestResult(0.0, 0.0, 0, 0.0)
    leader = AssetLeader("EURUSDm", None, None, None)
    result = asyncio.run(leader.run_competition())

    assert isinstance(result, CompetitionResult)
    # 0 candles -> all sharpes are 0.0 -> still produces a result
    assert result.symbol == "EURUSDm"


def test_make_configs_count_and_uniqueness():
    """_make_configs produces 12 distinct configs each summing to 1.0."""
    leader = AssetLeader("EURUSDm", None, None, None)
    configs = leader._make_configs()
    assert len(configs) == 12
    unique = [str(sorted(c.items())) for c in configs]
    assert len(set(unique)) == 12
    for i, c in enumerate(configs):
        total = sum(c.values())
        assert abs(total - 1.0) < 1e-9, f"config {i} weights sum={total}"


# ── Real ForexAgent integration (catches mock-only gaps) ──────────────────

def make_real_agent(symbol="EURUSDm"):
    """Build a REAL ForexAgent (not a mock) so update_strategy_weights is exercised."""
    from engine.dna import random_dna
    from engine.signals import ForexSignalEngine
    from engine.risk_guardian import ForexRiskGuardian
    from engine.agent import ForexAgent
    dna = random_dna(0, symbol)
    return ForexAgent(dna, ForexSignalEngine(), ForexRiskGuardian(), paper_mode=True)


def test_real_agent_has_update_strategy_weights():
    """Regression: real ForexAgent must expose update_strategy_weights (was mock-only)."""
    agent = make_real_agent()
    assert hasattr(agent, "update_strategy_weights")


def test_update_strategy_weights_normalizes():
    agent = make_real_agent()
    agent.update_strategy_weights({"momentum": 3.0, "order_flow": 1.0})
    w = agent.dna.strategy_weights
    assert abs(sum(w.values()) - 1.0) < 1e-9
    assert abs(w["momentum"] - 0.75) < 1e-9
    assert abs(w["order_flow"] - 0.25) < 1e-9


def test_update_strategy_weights_drops_invalid():
    agent = make_real_agent()
    agent.update_strategy_weights({"momentum": 1.0, "bogus": 5.0, "order_flow": -2.0})
    w = agent.dna.strategy_weights
    assert "bogus" not in w
    assert "order_flow" not in w  # negative dropped
    assert w["momentum"] == 1.0


def test_update_strategy_weights_empty_is_noop():
    agent = make_real_agent()
    before = dict(agent.dna.strategy_weights)
    agent.update_strategy_weights({})
    assert agent.dna.strategy_weights == before


def test_competition_applies_to_real_agent():
    """End-to-end: approved competition mutates a REAL agent's DNA weights."""
    candles = make_candles()
    mt5 = make_mock_mt5(candles)
    hermes = make_mock_hermes(winner_idx=0, approved=True)
    agent = make_real_agent()
    before = dict(agent.dna.strategy_weights)

    leader = AssetLeader("EURUSDm", agent, mt5, hermes)
    result = asyncio.run(leader.run_competition())

    assert result.approved is True
    assert result.applied is True
    assert abs(sum(agent.dna.strategy_weights.values()) - 1.0) < 1e-9
    assert agent.dna.strategy_weights != before  # actually changed
