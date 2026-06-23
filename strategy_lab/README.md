# TradeOps Strategy Lab

Strategy Lab is the research gate before a strategy can enter demo/testnet execution.
It validates strategy proposals, runs reproducible backtests, writes reports, and
updates the strategy registry without touching the live engines.

Run a crypto backtest from Binance public OHLCV:

```bash
python3 -m strategy_lab.run_backtest \
  --proposal strategy_lab/strategies/btc_eth_trend_pullback_v1.json \
  --symbol BTCUSDT \
  --fetch-binance \
  --network production \
  --count 500 \
  --out strategy_lab/reports/btcusdt_report.json \
  --registry strategy_lab/registry/approved_strategies.json
```

Exit code is non-zero when the strategy fails the forward-test gate. That is an
expected result for weak strategies; inspect `gate_reasons` in the report.

