# MTAI — MT5/Forex AI Trading System

ระบบ AI Trading สำหรับ Forex ผ่าน MetaTrader 5 + Exness  
สถาปัตยกรรมดัดแปลงจาก ai-trading-live (Binance) → Forex

## Project Structure

```
/home/alfred/mtai/
├── README.md                    ← this file
├── PLAN.md                      ← master implementation plan
├── phases/
│   ├── phase-1-mt5-bridge.md    ← MT5 data feed + execution bridge
│   ├── phase-2-signal-engine.md ← port algorithm จาก ai-trading-live
│   ├── phase-3-risk-engine.md   ← risk guardian + forex-specific rules
│   ├── phase-4-agent-system.md  ← multi-agent evolution
│   └── phase-5-dashboard.md     ← dashboard + monitoring
└── decisions/
    └── architecture.md          ← key design decisions
```

## Quick Start (after implementation)

```bash
cd /home/alfred/mtai/src
python3 run.py --mode paper     # paper trade
python3 run.py --mode live      # live trade (Exness account)
```

## Source Reference

Algorithm ported จาก: `/home/alfred/Siam-Synapse/ai-trading-live/`
- `engine/signals.py` → `mtai/engine/signals.py`
- `engine/agent.py` → `mtai/engine/agent.py`
- `engine/evolution.py` → `mtai/engine/evolution.py`
- `engine/paper_trade.py` → `mtai/engine/paper_trade.py`
