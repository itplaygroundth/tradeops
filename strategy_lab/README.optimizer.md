# Strategy Lab Optimizer

Run a parameter-grid optimization before a strategy can move beyond `draft`.

```bash
python3 -m strategy_lab.run_optimize \
  --proposal strategy_lab/strategies/btc_eth_trend_pullback_v1.json \
  --symbol BTCUSDT \
  --fetch-binance \
  --network production \
  --count 500 \
  --top 10 \
  --out strategy_lab/reports/btcusdt_optimize.json \
  --registry strategy_lab/registry/approved_strategies.json
```

The optimizer writes the best parameter set and the top candidates. Registry
status becomes `optimized` only when at least one candidate passes the gate.
Otherwise the strategy remains `draft`.

