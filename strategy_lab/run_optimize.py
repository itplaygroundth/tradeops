from __future__ import annotations

import argparse
import json
from pathlib import Path

from .data import fetch_binance_ohlcv
from .optimizer import optimize_crypto_strategy
from .registry import StrategyRegistry
from .schema import validate_strategy_proposal


def _load_json(path: str | Path):
    return json.loads(Path(path).read_text())


def main() -> int:
    parser = argparse.ArgumentParser(description="Optimize a Strategy Lab proposal")
    parser.add_argument("--proposal", required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--candles", default="")
    parser.add_argument("--fetch-binance", action="store_true")
    parser.add_argument("--network", default="production")
    parser.add_argument("--timeframe", default="")
    parser.add_argument("--count", type=int, default=500)
    parser.add_argument("--grid", default="", help="Optional JSON parameter grid")
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--out", default="")
    parser.add_argument("--registry", default="")
    args = parser.parse_args()

    proposal = validate_strategy_proposal(_load_json(args.proposal))
    if proposal.market != "crypto":
        raise SystemExit("Only crypto optimization is implemented in this phase")
    timeframe = args.timeframe or proposal.timeframes.get("entry", "M15")
    if args.fetch_binance:
        candles = fetch_binance_ohlcv(
            args.symbol.upper(),
            timeframe=timeframe,
            count=args.count,
            network=args.network,
        )
    elif args.candles:
        candles = _load_json(args.candles)
    else:
        raise SystemExit("provide --candles or --fetch-binance")

    grid = _load_json(args.grid) if args.grid else None
    result = optimize_crypto_strategy(
        proposal,
        args.symbol.upper(),
        candles,
        grid=grid,
        top_n=args.top,
    )
    data = result.to_dict()
    rendered = json.dumps(data, indent=2, sort_keys=True)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(rendered)
    else:
        print(rendered)

    if args.registry and result.best:
        raw = proposal.to_dict()
        raw["parameters"] = dict(result.best["parameters"])
        status = "optimized" if result.passed else "draft"
        StrategyRegistry(args.registry).upsert(raw, status=status, report=data)
    return 0 if result.passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
