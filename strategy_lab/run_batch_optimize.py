from __future__ import annotations

import argparse
import json
from pathlib import Path

from .batch_runner import run_batch_optimize


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch optimize Strategy Lab proposals")
    parser.add_argument("--proposals", default="strategy_lab/strategies/generated/*.json")
    parser.add_argument("--reports-dir", default="strategy_lab/reports/batch")
    parser.add_argument("--registry", default="strategy_lab/registry/approved_strategies.json")
    parser.add_argument("--network", default="production")
    parser.add_argument("--count", type=int, default=500)
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--out", default="strategy_lab/reports/batch_summary.json")
    args = parser.parse_args()

    report = run_batch_optimize(
        args.proposals,
        reports_dir=args.reports_dir,
        registry_path=args.registry,
        network=args.network,
        count=args.count,
        top_n=args.top,
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    print(json.dumps({
        "proposals": report.proposals,
        "runs": report.runs,
        "passed_runs": report.passed_runs,
        "out": str(out),
    }, sort_keys=True))
    return 0 if report.passed_runs else 2


if __name__ == "__main__":
    raise SystemExit(main())

