from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List


@dataclass
class ShadowMetrics:
    signals: int
    actionable: int
    outcomes: int
    wins: int
    losses: int
    win_rate: float
    expectancy_pct: float
    profit_factor: float
    total_pnl_pct: float
    by_strategy: Dict[str, Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def summarize_shadow_signals(signals_path: str | Path = "strategy_lab/shadow/signals.jsonl") -> ShadowMetrics:
    rows = _read_jsonl(signals_path)
    actionable = [row for row in rows if row.get("action") in {"LONG", "SHORT"}]
    with_outcomes = [row for row in rows if _pnl(row) is not None]
    pnls = [_pnl(row) for row in with_outcomes]
    wins = [pnl for pnl in pnls if pnl is not None and pnl > 0]
    losses = [pnl for pnl in pnls if pnl is not None and pnl <= 0]
    by_strategy: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        name = str(row.get("strategy_name") or "unknown")
        item = by_strategy.setdefault(name, {"signals": 0, "actionable": 0, "outcomes": 0, "total_pnl_pct": 0.0})
        item["signals"] += 1
        if row.get("action") in {"LONG", "SHORT"}:
            item["actionable"] += 1
        pnl = _pnl(row)
        if pnl is not None:
            item["outcomes"] += 1
            item["total_pnl_pct"] = round(float(item["total_pnl_pct"]) + pnl, 6)

    profit_factor = (sum(wins) / abs(sum(losses))) if losses and abs(sum(losses)) > 0 else (999.0 if wins else 0.0)
    return ShadowMetrics(
        signals=len(rows),
        actionable=len(actionable),
        outcomes=len(with_outcomes),
        wins=len(wins),
        losses=len(losses),
        win_rate=round(len(wins) / len(with_outcomes), 4) if with_outcomes else 0.0,
        expectancy_pct=round(mean(pnls), 6) if pnls else 0.0,
        profit_factor=round(profit_factor, 6),
        total_pnl_pct=round(sum(pnls), 6) if pnls else 0.0,
        by_strategy=by_strategy,
    )


def _pnl(row: Dict[str, Any]) -> float | None:
    for key in ("theoretical_pnl_pct", "paper_pnl_pct", "testnet_pnl_pct", "pnl_pct"):
        if row.get(key) is not None:
            return float(row[key])
    outcome = row.get("outcome") or {}
    if outcome.get("pnl_pct") is not None:
        return float(outcome["pnl_pct"])
    return None


def _read_jsonl(path: str | Path) -> List[Dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return []
    rows = []
    for line in target.read_text().splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows

