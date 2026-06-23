from __future__ import annotations

import argparse
import json

from .promotion import promote_strategy_to_shadow


def main() -> int:
    parser = argparse.ArgumentParser(description="Promote a Strategy Lab registry entry into shadow testing")
    parser.add_argument("name", help="Strategy name from the registry")
    parser.add_argument("--version", type=int, default=1)
    parser.add_argument("--registry", default="strategy_lab/registry/approved_strategies.json")
    parser.add_argument("--manifest", default="strategy_lab/shadow/deployments.json")
    parser.add_argument("--events", default="strategy_lab/shadow/events.jsonl")
    parser.add_argument("--mode", default="testnet_shadow")
    parser.add_argument("--network", default="testnet")
    parser.add_argument("--policy", default="strategy_lab/config/promotion_policy.json")
    parser.add_argument("--no-reject-write", action="store_true")
    args = parser.parse_args()

    decision = promote_strategy_to_shadow(
        args.registry,
        args.name,
        version=args.version,
        manifest_path=args.manifest,
        events_path=args.events,
        mode=args.mode,
        network=args.network,
        policy_path=args.policy,
        write_rejection=not args.no_reject_write,
    )
    print(json.dumps(decision.to_dict(), indent=2, sort_keys=True))
    return 0 if decision.approved else 2


if __name__ == "__main__":
    raise SystemExit(main())
