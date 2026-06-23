from __future__ import annotations

import argparse
import json
from pathlib import Path

from .backtest import run_crypto_backtest
from .data import fetch_binance_ohlcv
from .registry import StrategyRegistry
from .schema import validate_strategy_proposal


def _load_json(path: str | Path):
    return json.loads(Path(path).read_text())


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a Strategy Lab backtest")
    parser.add_argument("--proposal", required=True, help="Strategy proposal JSON path")
    parser.add_argument("--candles", default="", help="OHLCV candle JSON path")
    parser.add_argument("--fetch-binance", action="store_true", help="Fetch OHLCV candles from Binance")
    parser.add_argument("--network", default="production", help="Binance network: production or testnet")
    parser.add_argument("--timeframe", default="", help="Override proposal entry timeframe")
    parser.add_argument("--count", type=int, default=500, help="Candle count when fetching Binance data")
    parser.add_argument("--symbol", required=True, help="Symbol to backtest, e.g. BTCUSDT")
    parser.add_argument("--out", default="", help="Write report JSON to this path")
    parser.add_argument("--registry", default="", help="Optional strategy registry path")
    args = parser.parse_args()

    proposal = validate_strategy_proposal(_load_json(args.proposal))
    if proposal.market != "crypto":
        raise SystemExit("Only crypto backtests are implemented in this phase")
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

    report = run_crypto_backtest(proposal, args.symbol.upper(), candles)
    data = report.to_dict()
    rendered = json.dumps(data, indent=2, sort_keys=True)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(rendered)
    else:
        print(rendered)

    if args.registry:
        status = "backtested" if report.approved_for_forward_test else "draft"
        StrategyRegistry(args.registry).upsert(proposal.to_dict(), status=status, report=data)
    return 0 if report.approved_for_forward_test else 2


if __name__ == "__main__":
    raise SystemExit(main())

