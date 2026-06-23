# Strategy Lab Batch Runner

Batch optimize generated strategy proposals and rank them before any execution
engine can use them.

```bash
python3 -m strategy_lab.run_batch_optimize \
  --proposals 'strategy_lab/strategies/generated/*.json' \
  --reports-dir strategy_lab/reports/batch \
  --registry strategy_lab/registry/approved_strategies.json \
  --network production \
  --count 500 \
  --top 10 \
  --out strategy_lab/reports/batch_summary.json
```

Strategies remain `draft` unless at least one symbol/parameter run passes the
gate. Passing this batch step is still not enough for live execution; the next
gate is walk-forward and demo/testnet forward testing.

