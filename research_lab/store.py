from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List

from .schema import PaperCandidate


class PaperStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> List[PaperCandidate]:
        if not self.path.exists():
            return []
        rows = []
        for line in self.path.read_text().splitlines():
            if not line.strip():
                continue
            rows.append(PaperCandidate.from_dict(json.loads(line)))
        return rows

    def upsert_many(self, candidates: Iterable[PaperCandidate]) -> List[PaperCandidate]:
        existing: Dict[str, PaperCandidate] = {item.paper_id: item for item in self.load()}
        for candidate in candidates:
            existing[candidate.paper_id] = candidate
        rows = sorted(
            [item for item in existing.values() if item.score > 0],
            key=lambda item: (-item.score, item.source, item.paper_id),
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text("\n".join(json.dumps(item.to_dict(), sort_keys=True) for item in rows) + ("\n" if rows else ""))
        tmp.replace(self.path)
        return rows
