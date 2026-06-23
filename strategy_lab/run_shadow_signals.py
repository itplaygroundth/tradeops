from __future__ import annotations

import argparse
import json
from pathlib import Path

from .shadow_runner import run_shadow_signals


def main() -> int:
    parser = argparse.ArgumentParser(description="Run signal-only shadow deployment evaluation")
    parser.add_argument("--deployments", default="strategy_lab/shadow/deployments.json")
    parser.add_argument("--signals", default="strategy_lab/shadow/signals.jsonl")
    parser.add_argument("--candles-json", help="JSON file mapping symbol to OHLCV candles")
    args = parser.parse_args()

    candles_by_symbol = {}
    if args.candles_json:
        candles_by_symbol = json.loads(Path(args.candles_json).read_text())

    result = run_shadow_signals(
        deployments_path=args.deployments,
        signals_path=args.signals,
        candles_by_symbol=candles_by_symbol,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
