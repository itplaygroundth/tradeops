# Research OS Dashboard

Standalone prototype dashboard for the TradeOps Research OS.

This project intentionally reuses the existing TradeOps control API for:

- Research OS status and actions
- Settings storage
- Telegram / LINE notification configuration
- Notification audit and daily trade summary triggers

## Run

```bash
PORT=5175 TRADEOPS_API_BASE=http://127.0.0.1:5001 npm start
```

Open:

```text
http://192.168.1.166:5175/
```

## Safety

- The dashboard does not place orders directly.
- Staged dispatch sends `confirm=STAGE_DEMO_TESTNET` only.
- Trade execution remains controlled by the existing TradeOps backend gates.
- Settings and notification secrets are not copied into this project; they are read and saved through the existing TradeOps API.

## Experiment Runs

The dashboard has a local experiment registry:

- `GET /api/experiments/proposals`
- `GET /api/experiments`
- `POST /api/experiments/run`

An experiment run executes:

1. Baseline backtest
2. Hyperparameter optimization
3. Synthetic stress tests for sideways, high-volatility, and crash regimes
4. Deterministic agent-style evaluation in Thai

Experiment artifacts are stored under:

```text
data/experiments/
data/experiments.jsonl
```
