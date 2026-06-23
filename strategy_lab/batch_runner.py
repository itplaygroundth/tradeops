from __future__ import annotations

import glob
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Dict, List

from .data import fetch_binance_ohlcv
from .optimizer import optimize_crypto_strategy
from .registry import StrategyRegistry
from .schema import StrategyProposal, validate_strategy_proposal


@dataclass
class BatchItem:
    proposal: str
    symbol: str
    tested: int
    passed: int
    status: str
    best: Dict | None
    report_path: str


@dataclass
class BatchReport:
    proposals: int
    runs: int
    passed_runs: int
    items: List[Dict]
    best_overall: List[Dict]

    def to_dict(self) -> Dict:
        return asdict(self)


def load_proposals(pattern: str) -> List[StrategyProposal]:
    proposals = []
    for path in sorted(glob.glob(pattern)):
        proposals.append(validate_strategy_proposal(json.loads(Path(path).read_text())))
    return proposals


def run_batch_optimize(
    proposal_pattern: str,
    reports_dir: str | Path = "strategy_lab/reports/batch",
    registry_path: str | Path = "strategy_lab/registry/approved_strategies.json",
    network: str = "production",
    count: int = 500,
    top_n: int = 10,
    fetcher: Callable[..., List[Dict]] = fetch_binance_ohlcv,
) -> BatchReport:
    proposals = load_proposals(proposal_pattern)
    reports = Path(reports_dir)
    reports.mkdir(parents=True, exist_ok=True)
    registry = StrategyRegistry(registry_path)
    items: List[BatchItem] = []

    for proposal in proposals:
        for symbol in proposal.symbols:
            timeframe = proposal.timeframes.get("entry", "M15")
            candles = fetcher(symbol, timeframe=timeframe, count=count, network=network)
            result = optimize_crypto_strategy(proposal, symbol, candles, top_n=top_n)
            result_data = result.to_dict()
            report_path = reports / f"{proposal.name}_{symbol.lower()}_optimize.json"
            report_path.write_text(json.dumps(result_data, indent=2, sort_keys=True))
            status = "optimized" if result.passed else "draft"
            if result.best:
                raw = proposal.to_dict()
                raw["parameters"] = dict(result.best["parameters"])
                registry.upsert(raw, status=status, report=result_data)
            items.append(BatchItem(
                proposal=proposal.name,
                symbol=symbol,
                tested=result.tested,
                passed=result.passed,
                status=status,
                best=result.best,
                report_path=str(report_path),
            ))

    rows = [asdict(item) for item in items]
    best_overall = sorted(
        rows,
        key=lambda item: (
            item["passed"],
            (item["best"] or {}).get("score", -999),
            (item["best"] or {}).get("profit_factor", 0),
        ),
        reverse=True,
    )
    return BatchReport(
        proposals=len(proposals),
        runs=len(rows),
        passed_runs=sum(1 for item in rows if item["passed"] > 0),
        items=rows,
        best_overall=best_overall[:10],
    )

