from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path

from .proposal_builder import build_proposals, write_proposals


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Strategy Lab proposals from Research Lab hypotheses")
    parser.add_argument("--hypotheses-dir", default="research_lab/hypotheses")
    parser.add_argument("--out-dir", default="strategy_lab/strategies/generated")
    parser.add_argument("--report", default="research_lab/reports/latest_generated_proposals.json")
    args = parser.parse_args()

    hypotheses = [
        json.loads(Path(path).read_text())
        for path in sorted(glob.glob(f"{args.hypotheses_dir}/*.json"))
    ]
    proposals = build_proposals(hypotheses)
    paths = write_proposals(proposals, args.out_dir)
    payload = {
        "hypotheses": len(hypotheses),
        "proposals": len(proposals),
        "files": [str(path) for path in paths],
        "items": proposals,
    }
    report = Path(args.report)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(payload, indent=2, sort_keys=True))
    print(json.dumps({"hypotheses": len(hypotheses), "proposals": len(proposals)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

