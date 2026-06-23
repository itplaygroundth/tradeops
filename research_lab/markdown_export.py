from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, List

from .schema import PaperCandidate


def paper_to_markdown(paper: PaperCandidate, abstract_chars: int = 700) -> str:
    abstract = _compact(paper.abstract, abstract_chars)
    keywords = ", ".join(paper.keywords) if paper.keywords else "n/a"
    authors = ", ".join(paper.authors[:4]) if paper.authors else "n/a"
    if len(paper.authors) > 4:
        authors += ", et al."
    return "\n".join([
        f"## {paper.title}",
        "",
        f"- id: `{paper.paper_id}`",
        f"- source: `{paper.source}`",
        f"- score: `{paper.score:.2f}`",
        f"- published: `{paper.published_at or 'unknown'}`",
        f"- authors: {authors}",
        f"- keywords: {keywords}",
        f"- url: {paper.url}",
        "",
        "**Abstract Brief**",
        "",
        abstract or "n/a",
        "",
        "**Research Use**",
        "",
        _research_use(paper),
        "",
    ])


def papers_to_markdown(
    papers: Iterable[PaperCandidate],
    title: str = "TradeOps Paper Brief",
    limit: int = 20,
    abstract_chars: int = 700,
) -> str:
    rows: List[PaperCandidate] = list(papers)[:limit]
    lines = [
        f"# {title}",
        "",
        f"papers: {len(rows)}",
        "",
        "> Compact markdown generated from paper metadata/abstracts for low-token research review.",
        "",
    ]
    for paper in rows:
        lines.append(paper_to_markdown(paper, abstract_chars=abstract_chars))
    return "\n".join(lines).rstrip() + "\n"


def write_papers_markdown(
    papers: Iterable[PaperCandidate],
    path: str | Path,
    title: str = "TradeOps Paper Brief",
    limit: int = 20,
    abstract_chars: int = 700,
) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(papers_to_markdown(papers, title=title, limit=limit, abstract_chars=abstract_chars))
    return out


def _compact(text: str, max_chars: int) -> str:
    value = re.sub(r"\s+", " ", text or "").strip()
    if len(value) <= max_chars:
        return value
    return value[: max(0, max_chars - 3)].rstrip() + "..."


def _research_use(paper: PaperCandidate) -> str:
    text = f"{paper.title} {paper.abstract}".lower()
    if "volatility" in text:
        return "Candidate for volatility-regime filters, risk throttles, or high-volatility no-trade gates."
    if "order book" in text or "market impact" in text or "adverse selection" in text:
        return "Candidate for order-flow, liquidity, slippage, and execution-quality filters."
    if "mean reversion" in text:
        return "Candidate for range/sideway mean-reversion or dynamic-grid guard conditions."
    if "trend" in text or "momentum" in text:
        return "Candidate for trend-strength filters, trend-following entries, or trend-risk models."
    return "Candidate for research review; convert into a testable hypothesis before strategy proposal."

