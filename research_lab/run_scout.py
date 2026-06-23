from __future__ import annotations

import argparse
import json
from pathlib import Path

from .paper_scout import search_arxiv
from .schema import normalize_keywords
from .store import PaperStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Search paper metadata for TradeOps Research Lab")
    parser.add_argument("--keywords", nargs="*", default=[])
    parser.add_argument("--keywords-file", default="research_lab/config/keywords.json")
    parser.add_argument("--max-results", type=int, default=10)
    parser.add_argument("--store", default="research_lab/data/paper_store.jsonl")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    keywords = list(args.keywords)
    if not keywords and Path(args.keywords_file).exists():
        data = json.loads(Path(args.keywords_file).read_text())
        keywords = data.get("keywords", [])
    keywords = normalize_keywords(keywords)
    candidates = search_arxiv(keywords, max_results=args.max_results)
    rows = PaperStore(args.store).upsert_many(candidates)
    payload = {
        "keywords": keywords,
        "found": len(candidates),
        "stored": len(rows),
        "top": [item.to_dict() for item in rows[: min(10, len(rows))]],
    }
    rendered = json.dumps(payload, indent=2, sort_keys=True)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(rendered)
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

