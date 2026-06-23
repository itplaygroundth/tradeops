from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


ALLOWED_REGIMES = {
    "trend",
    "range",
    "high_volatility",
    "low_liquidity",
    "market_microstructure",
    "unknown",
}


@dataclass
class StrategyHypothesis:
    hypothesis_id: str
    source_paper_id: str
    title: str
    market: str
    regime: str
    strategy_family: str
    entry_idea: str
    exit_idea: str
    risk_idea: str
    expected_failure_modes: List[str]
    testable_parameters: Dict[str, List[Any]]
    confidence: float
    citations: List[Dict[str, str]]
    created_at: float = field(default_factory=time.time)

    def validate(self) -> None:
        if not self.hypothesis_id:
            raise ValueError("hypothesis_id is required")
        if not self.source_paper_id:
            raise ValueError("source_paper_id is required")
        if self.regime not in ALLOWED_REGIMES:
            raise ValueError(f"unsupported regime: {self.regime}")
        if not self.strategy_family:
            raise ValueError("strategy_family is required")
        if not self.entry_idea or not self.exit_idea or not self.risk_idea:
            raise ValueError("entry_idea, exit_idea, and risk_idea are required")
        if not self.testable_parameters:
            raise ValueError("testable_parameters cannot be empty")

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        return asdict(self)

