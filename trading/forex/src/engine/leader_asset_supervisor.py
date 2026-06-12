from __future__ import annotations

import json
import math
import os
import statistics
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .dna import FOREX_SYMBOLS

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_STATE_FILE = ROOT_DIR / "dashboard" / "live_state.json"
DEFAULT_PROPOSAL_FILE = ROOT_DIR / "data" / "leader_asset_proposals.json"
SOURCE = "leader_asset_supervisor_v1"


class LeaderAssetSupervisor:
    """Ranks leader assets from completed competitions and writes guarded proposals.

    This supervisor is deliberately outside the trading hot path. It never places
    orders and never mutates strategy weights directly; the engine can inspect
    its proposal and apply separate guardrails.
    """

    def __init__(
        self,
        state_path: Optional[Path] = None,
        proposal_path: Optional[Path] = None,
        lookback: Optional[int] = None,
        min_samples: Optional[int] = None,
        min_confidence: Optional[float] = None,
        expiry_seconds: Optional[int] = None,
    ):
        self.state_path = Path(state_path or os.getenv("LEADER_ASSET_STATE_PATH", DEFAULT_STATE_FILE))
        self.proposal_path = Path(proposal_path or os.getenv("LEADER_ASSET_PROPOSAL_PATH", DEFAULT_PROPOSAL_FILE))
        self.lookback = int(lookback if lookback is not None else os.getenv("LEADER_ASSET_LOOKBACK", "50"))
        self.min_samples = int(min_samples if min_samples is not None else os.getenv("LEADER_ASSET_MIN_SAMPLES", "3"))
        self.min_confidence = float(
            min_confidence if min_confidence is not None else os.getenv("LEADER_ASSET_MIN_CONFIDENCE", "0.55")
        )
        self.expiry_seconds = int(
            expiry_seconds if expiry_seconds is not None else os.getenv("LEADER_ASSET_PROPOSAL_TTL", "3600")
        )
        self.supported_symbols = set(FOREX_SYMBOLS)

    def load_history(self, state: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        if state is None:
            if not self.state_path.exists():
                return []
            try:
                state = json.loads(self.state_path.read_text())
            except Exception:
                return []
        summary = state.get("summary", {}) if isinstance(state, dict) else {}
        history = summary.get("competition_history") or []
        if not isinstance(history, list):
            return []
        cleaned = [entry for entry in history if self._valid_entry(entry)]
        cleaned.sort(key=lambda item: float(item.get("timestamp", 0)), reverse=True)
        return cleaned[: self.lookback]

    def rank_assets(self, history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for entry in history:
            grouped.setdefault(entry["symbol"], []).append(entry)

        ranking = []
        now = time.time()
        for symbol, entries in grouped.items():
            entries.sort(key=lambda item: float(item.get("timestamp", 0)), reverse=True)
            forwards = [float(item.get("forward_pnl", 0.0)) for item in entries]
            sharpes = [float(item.get("winner_sharpe", 0.0)) for item in entries]
            applied = [1.0 if item.get("applied") else 0.0 for item in entries]
            positive = [1.0 if value > 0 else 0.0 for value in forwards]
            samples = len(entries)
            avg_forward = statistics.fmean(forwards) if forwards else 0.0
            median_forward = statistics.median(forwards) if forwards else 0.0
            volatility = statistics.pstdev(forwards) if len(forwards) > 1 else 0.0
            applied_rate = statistics.fmean(applied) if applied else 0.0
            positive_rate = statistics.fmean(positive) if positive else 0.0
            avg_sharpe = statistics.fmean(sharpes) if sharpes else 0.0
            latest_ts = float(entries[0].get("timestamp", 0.0)) if entries else 0.0
            age_seconds = max(0.0, now - latest_ts) if latest_ts else self.expiry_seconds
            stale_penalty = min(0.05, age_seconds / max(self.expiry_seconds, 1) * 0.02)
            consistency = applied_rate * positive_rate
            score = (
                avg_forward
                + median_forward * 0.5
                + consistency * 0.02
                + applied_rate * 0.01
                + avg_sharpe * 0.0001
                - volatility * 0.2
                - stale_penalty
            )
            ranking.append({
                "symbol": symbol,
                "score": round(score, 6),
                "avg_forward_pnl": avg_forward,
                "median_forward_pnl": median_forward,
                "volatility": volatility,
                "applied_rate": applied_rate,
                "positive_rate": positive_rate,
                "avg_sharpe": avg_sharpe,
                "samples": samples,
                "latest_forward_pnl": forwards[0] if forwards else 0.0,
                "latest_timestamp": latest_ts,
                "winner_config": entries[0].get("winner_config"),
            })
        ranking.sort(key=lambda item: (item["score"], item["avg_forward_pnl"], item["latest_forward_pnl"]), reverse=True)
        return ranking

    def build_proposal(self, ranking: List[Dict[str, Any]], now: Optional[float] = None) -> Dict[str, Any]:
        now = float(now if now is not None else time.time())
        base = {
            "source": SOURCE,
            "created_at": now,
            "expires_at": now + self.expiry_seconds,
            "lookback_competitions": self.lookback,
            "min_samples": self.min_samples,
            "ranking": ranking,
        }
        if not ranking:
            return {**base, "status": "no_history", "leader_asset": None, "confidence": 0.0, "score": 0.0,
                    "reason": "No valid competition history available"}

        leader = ranking[0]
        runner_up = ranking[1] if len(ranking) > 1 else None
        score = float(leader.get("score", 0.0))
        runner_score = float(runner_up.get("score", 0.0)) if runner_up else 0.0
        margin = score - runner_score
        margin_pct = margin / max(abs(runner_score), 1e-9) if runner_up else 1.0
        sample_factor = min(1.0, leader.get("samples", 0) / max(self.min_samples, 1))
        consistency = float(leader.get("positive_rate", 0.0)) * float(leader.get("applied_rate", 0.0))
        margin_factor = min(1.0, max(0.0, margin_pct))
        confidence = max(0.0, min(0.99, 0.35 + sample_factor * 0.25 + consistency * 0.25 + margin_factor * 0.15))
        if int(leader.get("samples", 0)) < self.min_samples:
            confidence = min(confidence, 0.54)
        if runner_up is None:
            confidence = min(confidence, 0.75)

        status = "accepted"
        reasons = []
        if int(leader.get("samples", 0)) < self.min_samples:
            status = "insufficient_samples"
            reasons.append(f"samples {leader.get('samples', 0)} below {self.min_samples}")
        elif confidence < self.min_confidence:
            status = "insufficient_confidence"
            reasons.append(f"confidence {confidence:.2f} below {self.min_confidence:.2f}")
        if not isinstance(leader.get("winner_config"), dict):
            status = "invalid_config"
            reasons.append("winner_config missing")

        reason = "; ".join(reasons) if reasons else (
            f"{leader['symbol']} leads rolling forward ranking with score {score:.6f}"
        )
        return {
            **base,
            "status": status,
            "leader_asset": leader["symbol"],
            "confidence": round(confidence, 4),
            "score": round(score, 6),
            "margin": round(margin, 6),
            "margin_pct": round(margin_pct, 6),
            "reason": reason,
            "winner_config": leader.get("winner_config"),
        }

    def write_proposal(self, proposal: Dict[str, Any]) -> Dict[str, Any]:
        self.proposal_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"proposals": [proposal]}
        tmp_path = self.proposal_path.with_suffix(self.proposal_path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True))
        tmp_path.replace(self.proposal_path)
        return payload

    def run(self, state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        history = self.load_history(state)
        ranking = self.rank_assets(history)
        proposal = self.build_proposal(ranking)
        self.write_proposal(proposal)
        return proposal

    def read_latest_proposal(self) -> Optional[Dict[str, Any]]:
        if not self.proposal_path.exists():
            return None
        try:
            raw = json.loads(self.proposal_path.read_text())
        except Exception:
            return None
        proposals = raw.get("proposals", []) if isinstance(raw, dict) else []
        if not proposals:
            return None
        proposal = proposals[0]
        return proposal if isinstance(proposal, dict) else None

    def _valid_entry(self, entry: Any) -> bool:
        if not isinstance(entry, dict):
            return False
        symbol = entry.get("symbol")
        if symbol not in self.supported_symbols:
            return False
        if not isinstance(entry.get("winner_config"), dict):
            return False
        try:
            forward = float(entry.get("forward_pnl", 0.0))
            timestamp = float(entry.get("timestamp", 0.0))
        except (TypeError, ValueError):
            return False
        if not math.isfinite(forward) or not math.isfinite(timestamp) or timestamp <= 0:
            return False
        return bool(entry.get("approved") or entry.get("applied"))
