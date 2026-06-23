from __future__ import annotations

import argparse
import json

from .shadow_metrics import summarize_shadow_signals


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize signal-only shadow deployment metrics")
    parser.add_argument("--signals", default="strategy_lab/shadow/signals.jsonl")
    args = parser.parse_args()
    print(json.dumps(summarize_shadow_signals(args.signals).to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

