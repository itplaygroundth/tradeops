from __future__ import annotations

from dataclasses import dataclass, asdict
from itertools import product
from typing import Any, Dict, Iterable, List

from .backtest import BacktestReport, run_crypto_backtest
from .schema import StrategyProposal, validate_strategy_proposal


DEFAULT_CRYPTO_GRID = {
    "fast_sma": [5, 9, 12],
    "slow_sma": [21, 34, 55],
    "max_entry_rsi": [60, 68, 72],
    "max_hold_bars": [8, 12, 20],
}

BREAKOUT_CRYPTO_GRID = {
    "fast_sma": [5, 9, 12],
    "slow_sma": [21, 34, 55],
    "breakout_lookback": [12, 20, 34],
    "min_atr_pct": [0.03, 0.05, 0.10],
    "max_atr_pct": [1.5, 2.5, 4.0],
    "max_entry_rsi": [72, 78, 85],
    "max_hold_bars": [8, 12, 20],
}

MEAN_REVERSION_CRYPTO_GRID = {
    "mean_window": [14, 20, 34],
    "entry_deviation_pct": [0.4, 0.6, 0.9],
    "exit_deviation_pct": [-0.1, 0.0, 0.15],
    "max_oversold_rsi": [30, 35, 42],
    "max_hold_bars": [8, 12, 20],
}


@dataclass
class OptimizationResult:
    strategy_name: str
    symbol: str
    tested: int
    passed: int
    best: Dict[str, Any] | None
    top: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def parameter_grid(grid: Dict[str, Iterable[Any]]) -> List[Dict[str, Any]]:
    keys = list(grid.keys())
    values = [list(grid[key]) for key in keys]
    if not keys or any(not value for value in values):
        return []
    return [dict(zip(keys, combo)) for combo in product(*values)]


def optimize_crypto_strategy(
    proposal: StrategyProposal,
    symbol: str,
    candles: List[Dict[str, Any]],
    grid: Dict[str, Iterable[Any]] | None = None,
    top_n: int = 10,
) -> OptimizationResult:
    if proposal.market != "crypto":
        raise ValueError("optimize_crypto_strategy only accepts crypto proposals")
    grid = grid or _default_grid_for(proposal.strategy_type)
    baseline_params = dict(proposal.parameters)
    rows: List[Dict[str, Any]] = []
    for params in parameter_grid(grid):
        raw = proposal.to_dict()
        merged_params = dict(baseline_params)
        merged_params.update(params)
        raw["parameters"] = merged_params
        candidate = validate_strategy_proposal(raw)
        report = run_crypto_backtest(candidate, symbol, candles)
        rows.append(_score_report(report, merged_params))

    rows.sort(
        key=lambda item: (
            item["approved_for_forward_test"],
            item["score"],
            item["profit_factor"],
            item["total_pnl_pct"],
        ),
        reverse=True,
    )
    passed = sum(1 for row in rows if row["approved_for_forward_test"])
    best = rows[0] if rows else None
    return OptimizationResult(
        strategy_name=proposal.name,
        symbol=symbol,
        tested=len(rows),
        passed=passed,
        best=best,
        top=rows[:top_n],
    )


def _default_grid_for(strategy_type: str) -> Dict[str, Iterable[Any]]:
    if strategy_type == "breakout":
        return BREAKOUT_CRYPTO_GRID
    if strategy_type == "mean_reversion":
        return MEAN_REVERSION_CRYPTO_GRID
    return DEFAULT_CRYPTO_GRID


def _score_report(report: BacktestReport, params: Dict[str, Any]) -> Dict[str, Any]:
    data = report.to_dict()
    score = (
        data["expectancy_pct"] * 4
        + min(data["profit_factor"], 5.0)
        + data["total_pnl_pct"] * 0.1
        - data["max_drawdown_pct"] * 0.25
    )
    return {
        "score": round(score, 6),
        "parameters": dict(params),
        "approved_for_forward_test": data["approved_for_forward_test"],
        "gate_reasons": data["gate_reasons"],
        "trades": data["trades"],
        "win_rate": data["win_rate"],
        "total_pnl_pct": data["total_pnl_pct"],
        "expectancy_pct": data["expectancy_pct"],
        "profit_factor": data["profit_factor"],
        "max_drawdown_pct": data["max_drawdown_pct"],
        "sharpe": data["sharpe"],
    }
