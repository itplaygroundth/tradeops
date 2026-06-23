# Strategy Lab Walk-Forward Gate

Walk-forward testing checks whether an optimized strategy survives out-of-sample
windows before it can move to `forward_testing`.

```bash
python3 -m strategy_lab.run_walk_forward \
  --proposal strategy_lab/strategies/btc_eth_mean_reversion_wf_candidate_v1.json \
  --symbol BTCUSDT \
  --fetch-binance \
  --network production \
  --count 600 \
  --train-size 240 \
  --test-size 120 \
  --step-size 120 \
  --out strategy_lab/reports/btcusdt_mean_reversion_walk_forward.json \
  --registry strategy_lab/registry/approved_strategies.json
```

Passing optimizer is not enough. A strategy must also pass enough out-of-sample
windows before it can become `forward_testing`.

