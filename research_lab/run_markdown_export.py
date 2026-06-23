from __future__ import annotations

import argparse
import json
from pathlib import Path

from .markdown_export import write_papers_markdown
from .store import PaperStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Export paper store to compact Markdown")
    parser.add_argument("--store", default="research_lab/data/paper_store.jsonl")
    parser.add_argument("--out", default="research_lab/reports/latest_papers.md")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--abstract-chars", type=int, default=700)
    args = parser.parse_args()

    papers = PaperStore(args.store).load()
    path = write_papers_markdown(
        papers,
        args.out,
        limit=args.limit,
        abstract_chars=args.abstract_chars,
    )
    print(json.dumps({"papers": min(len(papers), args.limit), "out": str(path)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

