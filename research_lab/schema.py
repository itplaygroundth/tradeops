from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


class PaperValidationError(ValueError):
    pass


@dataclass
class PaperCandidate:
    paper_id: str
    title: str
    source: str
    url: str
    abstract: str = ""
    authors: List[str] = field(default_factory=list)
    published_at: str = ""
    keywords: List[str] = field(default_factory=list)
    score: float = 0.0
    discovered_at: float = field(default_factory=time.time)
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "PaperCandidate":
        if not isinstance(raw, dict):
            raise PaperValidationError("paper candidate must be an object")
        candidate = cls(
            paper_id=str(raw.get("paper_id") or "").strip(),
            title=str(raw.get("title") or "").strip(),
            source=str(raw.get("source") or "").strip(),
            url=str(raw.get("url") or "").strip(),
            abstract=str(raw.get("abstract") or "").strip(),
            authors=[str(item).strip() for item in raw.get("authors") or [] if str(item).strip()],
            published_at=str(raw.get("published_at") or "").strip(),
            keywords=[str(item).strip().lower() for item in raw.get("keywords") or [] if str(item).strip()],
            score=float(raw.get("score") or 0.0),
            discovered_at=float(raw.get("discovered_at") or time.time()),
            raw=dict(raw.get("raw") or {}),
        )
        candidate.validate()
        return candidate

    def validate(self) -> None:
        if not self.paper_id:
            raise PaperValidationError("paper_id is required")
        if not self.title:
            raise PaperValidationError("title is required")
        if not self.source:
            raise PaperValidationError("source is required")
        if not self.url:
            raise PaperValidationError("url is required")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def normalize_keywords(keywords: List[str]) -> List[str]:
    seen = set()
    out = []
    for keyword in keywords:
        item = str(keyword or "").strip().lower()
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out

