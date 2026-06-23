from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List


STATUSES = {
    "draft",
    "backtested",
    "optimized",
    "shadow_testing",
    "paper_testing",
    "forward_testing",
    "approved",
    "rejected",
    "disabled",
}


class StrategyRegistry:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"version": 1, "strategies": []}
        return json.loads(self.path.read_text())

    def save(self, data: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
        tmp.replace(self.path)

    def upsert(self, proposal: Dict[str, Any], status: str = "draft", report: Dict[str, Any] | None = None) -> Dict[str, Any]:
        if status not in STATUSES:
            raise ValueError(f"unsupported strategy status: {status}")
        data = self.load()
        strategies: List[Dict[str, Any]] = list(data.get("strategies") or [])
        key = (proposal["name"], int(proposal.get("version") or 1))
        entry = {
            "name": key[0],
            "version": key[1],
            "market": proposal["market"],
            "symbols": list(proposal["symbols"]),
            "timeframes": dict(proposal["timeframes"]),
            "type": proposal["type"],
            "status": status,
            "updated_at": time.time(),
            "proposal": dict(proposal),
            "latest_report": dict(report or {}),
        }
        replaced = False
        for idx, item in enumerate(strategies):
            if item.get("name") == key[0] and int(item.get("version") or 1) == key[1]:
                strategies[idx] = entry
                replaced = True
                break
        if not replaced:
            strategies.append(entry)
        data["strategies"] = strategies
        self.save(data)
        return entry

    def approved(self, market: str | None = None) -> List[Dict[str, Any]]:
        rows = [item for item in self.load().get("strategies", []) if item.get("status") == "approved"]
        if market:
            rows = [item for item in rows if item.get("market") == market]
        return rows
