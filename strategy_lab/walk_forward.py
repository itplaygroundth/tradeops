from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Tuple

from .backtest import run_crypto_backtest
from .schema import StrategyProposal, validate_strategy_proposal


@dataclass
class WalkForwardWindow:
    index: int
    train_start: int
    train_end: int
    test_start: int
    test_end: int
    train: Dict[str, Any]
    test: Dict[str, Any]
    passed: bool
    reasons: List[str]


@dataclass
class WalkForwardReport:
    strategy_name: str
    symbol: str
    windows: int
    passed_windows: int
    pass_rate: float
    approved_for_forward_test: bool
    gate_reasons: List[str]
    window_reports: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def build_walk_forward_splits(
    candles: List[Dict[str, Any]],
    train_size: int = 160,
    test_size: int = 80,
    step_size: int = 80,
) -> List[Tuple[int, int, int, int]]:
    splits = []
    total = len(candles)
    start = 0
    while start + train_size + test_size <= total:
        train_start = start
        train_end = start + train_size
        test_start = train_end
        test_end = train_end + test_size
        splits.append((train_start, train_end, test_start, test_end))
        start += step_size
    return splits


def run_walk_forward(
    proposal: StrategyProposal,
    symbol: str,
    candles: List[Dict[str, Any]],
    train_size: int = 160,
    test_size: int = 80,
    step_size: int = 80,
    min_pass_rate: float = 0.6,
) -> WalkForwardReport:
    if proposal.market != "crypto":
        raise ValueError("run_walk_forward only accepts crypto proposals")
    proposal = validate_strategy_proposal(proposal.to_dict())
    splits = build_walk_forward_splits(candles, train_size=train_size, test_size=test_size, step_size=step_size)
    windows: List[WalkForwardWindow] = []
    for idx, (train_start, train_end, test_start, test_end) in enumerate(splits):
        train_report = run_crypto_backtest(proposal, symbol, candles[train_start:train_end])
        test_report = run_crypto_backtest(proposal, symbol, candles[test_start:test_end])
        test_data = test_report.to_dict()
        passed, reasons = _window_gate(test_data)
        windows.append(WalkForwardWindow(
            index=idx,
            train_start=train_start,
            train_end=train_end,
            test_start=test_start,
            test_end=test_end,
            train=_compact_report(train_report.to_dict()),
            test=_compact_report(test_data),
            passed=passed,
            reasons=reasons,
        ))
    passed_windows = sum(1 for window in windows if window.passed)
    pass_rate = passed_windows / len(windows) if windows else 0.0
    gate_reasons = []
    if not windows:
        gate_reasons.append("not enough candles for walk-forward splits")
    if pass_rate < min_pass_rate:
        gate_reasons.append(f"walk-forward pass rate below {min_pass_rate:.0%}")
    approved = not gate_reasons
    return WalkForwardReport(
        strategy_name=proposal.name,
        symbol=symbol,
        windows=len(windows),
        passed_windows=passed_windows,
        pass_rate=round(pass_rate, 4),
        approved_for_forward_test=approved,
        gate_reasons=gate_reasons,
        window_reports=[asdict(window) for window in windows],
    )


def _window_gate(report: Dict[str, Any]) -> tuple[bool, List[str]]:
    reasons = []
    if report["trades"] < 2:
        reasons.append("test window has too few trades")
    if report["expectancy_pct"] <= 0:
        reasons.append("test expectancy is not positive")
    if report["profit_factor"] < 1.05:
        reasons.append("test profit factor below 1.05")
    if report["max_drawdown_pct"] > 5.0:
        reasons.append("test max drawdown above 5%")
    return not reasons, reasons


def _compact_report(report: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "trades": report["trades"],
        "win_rate": report["win_rate"],
        "total_pnl_pct": report["total_pnl_pct"],
        "expectancy_pct": report["expectancy_pct"],
        "profit_factor": report["profit_factor"],
        "max_drawdown_pct": report["max_drawdown_pct"],
        "approved_for_forward_test": report["approved_for_forward_test"],
        "gate_reasons": report["gate_reasons"],
    }
