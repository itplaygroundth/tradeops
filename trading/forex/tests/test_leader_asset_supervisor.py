from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from engine.leader_asset_supervisor import LeaderAssetSupervisor


def entry(symbol, forward, ts, *, applied=True, sharpe=0.0, config=None):
    return {
        "symbol": symbol,
        "regime": "RANGING",
        "winner_sharpe": sharpe,
        "winner_config": config or {"momentum": 1.0},
        "leader_score": forward,
        "selection_source": "deterministic",
        "llm_error": "",
        "deterministic_winner_idx": 0,
        "llm_winner_idx": None,
        "proposal_status": "none",
        "proposal_reason": "",
        "proposal_source": "",
        "approved": applied,
        "applied": applied,
        "forward_pnl": forward,
        "timestamp": ts,
    }


def test_rank_assets_prefers_rolling_forward_and_consistency(tmp_path):
    sup = LeaderAssetSupervisor(proposal_path=tmp_path / "proposal.json", min_samples=2)
    now = time.time()
    history = [
        entry("EURUSDm", 0.01, now - 10),
        entry("EURUSDm", 0.02, now - 20),
        entry("GBPUSDm", 0.03, now - 10),
        entry("GBPUSDm", -0.02, now - 20),
    ]

    ranking = sup.rank_assets(history)

    assert ranking[0]["symbol"] == "EURUSDm"
    assert ranking[0]["samples"] == 2
    assert ranking[0]["positive_rate"] == 1.0


def test_build_proposal_accepts_valid_leader(tmp_path):
    sup = LeaderAssetSupervisor(proposal_path=tmp_path / "proposal.json", min_samples=1, min_confidence=0.5)
    ranking = [{
        "symbol": "GBPUSDm",
        "score": 0.05,
        "avg_forward_pnl": 0.05,
        "median_forward_pnl": 0.05,
        "volatility": 0.0,
        "applied_rate": 1.0,
        "positive_rate": 1.0,
        "avg_sharpe": 0.0,
        "samples": 3,
        "latest_forward_pnl": 0.05,
        "latest_timestamp": time.time(),
        "winner_config": {"mean_reversion": 1.0},
    }]

    proposal = sup.build_proposal(ranking)

    assert proposal["status"] == "accepted"
    assert proposal["leader_asset"] == "GBPUSDm"
    assert proposal["confidence"] >= 0.5


def test_run_writes_proposal_file_from_state(tmp_path):
    proposal_path = tmp_path / "leader_asset_proposals.json"
    sup = LeaderAssetSupervisor(proposal_path=proposal_path, min_samples=1, min_confidence=0.5)
    now = time.time()
    state = {"summary": {"competition_history": [entry("EURUSDm", 0.01, now)]}}

    proposal = sup.run(state)
    raw = json.loads(proposal_path.read_text())

    assert proposal["leader_asset"] == "EURUSDm"
    assert raw["proposals"][0]["leader_asset"] == "EURUSDm"


def test_invalid_entries_are_ignored(tmp_path):
    sup = LeaderAssetSupervisor(proposal_path=tmp_path / "proposal.json")
    now = time.time()
    state = {"summary": {"competition_history": [
        entry("EURUSDm", 0.01, now),
        entry("BAD", 9.0, now),
        {"symbol": "GBPUSDm", "forward_pnl": 1.0, "timestamp": now},
    ]}}

    history = sup.load_history(state)

    assert [item["symbol"] for item in history] == ["EURUSDm"]


def test_no_history_proposal_is_safe(tmp_path):
    sup = LeaderAssetSupervisor(proposal_path=tmp_path / "proposal.json")

    proposal = sup.build_proposal([])

    assert proposal["status"] == "no_history"
    assert proposal["leader_asset"] is None
