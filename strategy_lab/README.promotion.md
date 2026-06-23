# Strategy Promotion Gate

Promotion is the handoff between Strategy Lab research and paper/testnet shadow deployment.
It is deliberately fail-closed: a strategy cannot enter shadow testing unless optimizer
evidence passes the configured gates.

## Gate Rules

Default requirements:

- registry status is `optimized` or `backtested`
- optimizer `best.approved_for_forward_test` is true
- at least 10 closed trades
- positive expectancy
- profit factor >= 1.15
- max drawdown <= 8%
- no upstream optimizer gate reasons

## Promote To Shadow

```bash
python3 -m strategy_lab.run_promotion btc_eth_trend_pullback_v1
```

If approved, the command writes:

```text
strategy_lab/shadow/deployments.json
strategy_lab/shadow/events.jsonl
```

Shadow deployments always start with:

```json
{
  "mode": "testnet_shadow",
  "network": "testnet",
  "order_execution": "disabled",
  "status": "active",
  "execution_enabled": false,
  "paper_or_testnet_only": true
}
```

This uses the same shadow deployment store that the dashboard reads. It keeps
research promotion separate from real execution. A later live-readiness approval
must still certify demo/testnet soak, round-trip evidence, and engine health.

## Dry Failure Check

To inspect gate output without writing rejected status:

```bash
python3 -m strategy_lab.run_promotion btc_eth_trend_pullback_v1 --no-reject-write
```
