from __future__ import annotations

import argparse
import json
from pathlib import Path

from .digest import digest_papers, write_hypotheses
from .store import PaperStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Digest paper candidates into testable hypotheses")
    parser.add_argument("--store", default="research_lab/data/paper_store.jsonl")
    parser.add_argument("--hypotheses-dir", default="research_lab/hypotheses")
    parser.add_argument("--out", default="research_lab/reports/latest_hypotheses.json")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    papers = PaperStore(args.store).load()[: max(1, args.limit)]
    hypotheses = digest_papers(papers)
    paths = write_hypotheses(hypotheses, args.hypotheses_dir)
    payload = {
        "papers": len(papers),
        "hypotheses": len(hypotheses),
        "files": [str(path) for path in paths],
        "top": [item.to_dict() for item in hypotheses[:10]],
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True))
    print(json.dumps({"papers": len(papers), "hypotheses": len(hypotheses)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

