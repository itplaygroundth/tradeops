from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


ALLOWED_MARKETS = {"crypto", "forex"}
ALLOWED_STRATEGY_TYPES = {
    "trend_following",
    "mean_reversion",
    "breakout",
    "market_structure",
}
ALLOWED_ACTIONS = {"LONG", "SHORT", "HOLD"}
DEFAULT_ALLOWED_TIMEFRAMES = {"M1", "M5", "M15", "M30", "H1", "H4", "D1"}


class StrategyValidationError(ValueError):
    pass


@dataclass
class StrategyProposal:
    name: str
    market: str
    symbols: List[str]
    timeframes: Dict[str, str]
    strategy_type: str
    entry_rules: List[Dict[str, Any]]
    exit_rules: List[Dict[str, Any]]
    risk_rules: Dict[str, Any] = field(default_factory=dict)
    parameters: Dict[str, Any] = field(default_factory=dict)
    version: int = 1
    status: str = "draft"

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "StrategyProposal":
        if not isinstance(raw, dict):
            raise StrategyValidationError("proposal must be an object")
        required = ["name", "market", "symbols", "timeframes", "type", "entry_rules", "exit_rules"]
        missing = [key for key in required if key not in raw]
        if missing:
            raise StrategyValidationError(f"missing required fields: {', '.join(missing)}")
        proposal = cls(
            name=str(raw["name"]).strip(),
            market=str(raw["market"]).strip().lower(),
            symbols=[str(item).strip().upper() for item in raw["symbols"]],
            timeframes={str(k): str(v).upper() for k, v in dict(raw["timeframes"]).items()},
            strategy_type=str(raw["type"]).strip(),
            entry_rules=list(raw["entry_rules"]),
            exit_rules=list(raw["exit_rules"]),
            risk_rules=dict(raw.get("risk_rules") or {}),
            parameters=dict(raw.get("parameters") or {}),
            version=int(raw.get("version") or 1),
            status=str(raw.get("status") or "draft"),
        )
        proposal.validate()
        return proposal

    def validate(self) -> None:
        if not self.name:
            raise StrategyValidationError("name is required")
        if self.market not in ALLOWED_MARKETS:
            raise StrategyValidationError(f"unsupported market: {self.market}")
        if not self.symbols:
            raise StrategyValidationError("at least one symbol is required")
        if self.market == "crypto":
            invalid = [symbol for symbol in self.symbols if not symbol.endswith("USDT")]
            if invalid:
                raise StrategyValidationError(f"crypto symbols must be USDT pairs: {invalid}")
        if self.strategy_type not in ALLOWED_STRATEGY_TYPES:
            raise StrategyValidationError(f"unsupported strategy type: {self.strategy_type}")
        for role in ("entry", "confirm", "regime"):
            tf = self.timeframes.get(role)
            if not tf:
                raise StrategyValidationError(f"timeframes.{role} is required")
            if tf not in DEFAULT_ALLOWED_TIMEFRAMES:
                raise StrategyValidationError(f"unsupported timeframe {role}={tf}")
        if not self.entry_rules:
            raise StrategyValidationError("entry_rules cannot be empty")
        if not self.exit_rules:
            raise StrategyValidationError("exit_rules cannot be empty")
        for rule in self.entry_rules + self.exit_rules:
            if not isinstance(rule, dict):
                raise StrategyValidationError("rules must be objects")
            action = str(rule.get("action", "HOLD")).upper()
            if action not in ALLOWED_ACTIONS:
                raise StrategyValidationError(f"unsupported rule action: {action}")
        risk_pct = float(self.risk_rules.get("risk_pct", 0.005))
        if risk_pct <= 0 or risk_pct > 0.05:
            raise StrategyValidationError("risk_pct must be > 0 and <= 0.05")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "market": self.market,
            "symbols": list(self.symbols),
            "timeframes": dict(self.timeframes),
            "type": self.strategy_type,
            "entry_rules": list(self.entry_rules),
            "exit_rules": list(self.exit_rules),
            "risk_rules": dict(self.risk_rules),
            "parameters": dict(self.parameters),
            "status": self.status,
        }


def validate_strategy_proposal(raw: Dict[str, Any]) -> StrategyProposal:
    return StrategyProposal.from_dict(raw)

