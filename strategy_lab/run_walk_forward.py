from __future__ import annotations

import argparse
import json
from pathlib import Path

from .data import fetch_binance_ohlcv
from .registry import StrategyRegistry
from .schema import validate_strategy_proposal
from .walk_forward import run_walk_forward


def _load_json(path: str | Path):
    return json.loads(Path(path).read_text())


def main() -> int:
    parser = argparse.ArgumentParser(description="Run walk-forward gate for a Strategy Lab proposal")
    parser.add_argument("--proposal", required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--candles", default="")
    parser.add_argument("--fetch-binance", action="store_true")
    parser.add_argument("--network", default="production")
    parser.add_argument("--timeframe", default="")
    parser.add_argument("--count", type=int, default=600)
    parser.add_argument("--train-size", type=int, default=240)
    parser.add_argument("--test-size", type=int, default=120)
    parser.add_argument("--step-size", type=int, default=120)
    parser.add_argument("--out", default="")
    parser.add_argument("--registry", default="")
    args = parser.parse_args()

    proposal = validate_strategy_proposal(_load_json(args.proposal))
    timeframe = args.timeframe or proposal.timeframes.get("entry", "M15")
    if args.fetch_binance:
        candles = fetch_binance_ohlcv(args.symbol.upper(), timeframe=timeframe, count=args.count, network=args.network)
    elif args.candles:
        candles = _load_json(args.candles)
    else:
        raise SystemExit("provide --candles or --fetch-binance")

    report = run_walk_forward(
        proposal,
        args.symbol.upper(),
        candles,
        train_size=args.train_size,
        test_size=args.test_size,
        step_size=args.step_size,
    )
    data = report.to_dict()
    rendered = json.dumps(data, indent=2, sort_keys=True)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(rendered)
    else:
        print(rendered)

    if args.registry:
        status = "forward_testing" if report.approved_for_forward_test else "optimized"
        StrategyRegistry(args.registry).upsert(proposal.to_dict(), status=status, report=data)
    return 0 if report.approved_for_forward_test else 2


if __name__ == "__main__":
    raise SystemExit(main())

