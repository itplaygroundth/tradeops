# MTAI — Forex AI Trading System: Master Implementation Plan

> **Goal:** Port ระบบ AI Trading จาก Binance/Crypto → MetaTrader 5 + Exness Forex
> โดยใช้ algorithm เดิม (mean_reversion, momentum, grid_scalp) แต่เปลี่ยน data feed + execution layer

**Architecture:** 5-layer system — MT5 Bridge (data+exec) → Signal Engine → Risk Guardian → Multi-Agent Evolution → Dashboard

**Tech Stack:**
- `MetaTrader5` Python library (Windows/Wine bridge หรือ MT5 API server)
- Algorithm: ported จาก `ai-trading-live/engine/` (signals.py, agent.py, evolution.py)
- Risk: 1% per trade, R:R ≥ 1:2 (เหมือน crypto)
- Broker: Exness via MT5

---

## Phase Overview

| Phase | งาน | Priority | เวลาประมาณ |
|-------|-----|----------|------------|
| 1 | MT5 Bridge | 🔴 Critical | 2-3 วัน |
| 2 | Signal Engine (Forex) | 🔴 Critical | 2 วัน |
| 3 | Risk Engine | 🟡 High | 1 วัน |
| 4 | Multi-Agent Evolution | 🟡 High | 2 วัน |
| 5 | Dashboard + Monitoring | 🟢 Medium | 1 วัน |

---

## Phase 1: MT5 Bridge

> รายละเอียด: `phases/phase-1-mt5-bridge.md`

**เป้าหมาย:** แทน Binance WebSocket + CCXT ด้วย MT5 data feed + order execution

ไฟล์หลัก:
- `src/mt5_bridge/feed.py` — real-time tick/OHLCV จาก MT5
- `src/mt5_bridge/executor.py` — ส่ง order ผ่าน MT5
- `src/mt5_bridge/account.py` — balance, equity, margin

---

## Phase 2: Signal Engine (Forex)

> รายละเอียด: `phases/phase-2-signal-engine.md`

**เป้าหมาย:** Port algorithm จาก ai-trading-live ให้ทำงานกับ Forex symbols

ไฟล์หลัก:
- `src/engine/signals.py` — ported + forex-adjusted
- `src/engine/forex_macro.py` — แทน polymarket (ใช้ economic calendar)

---

## Phase 3: Risk Engine

> รายละเอียด: `phases/phase-3-risk-engine.md`

**เป้าหมาย:** Risk Guardian ที่รู้จัก pip value, spread, leverage

ไฟล์หลัก:
- `src/engine/risk_guardian.py` — pip-based position sizing

---

## Phase 4: Multi-Agent Evolution

> รายละเอียด: `phases/phase-4-agent-system.md`

**เป้าหมาย:** 25 agents วิ่งพร้อมกัน evolve strategy ที่ดีที่สุดสำหรับ Forex

ไฟล์หลัก:
- `src/engine/agent.py`
- `src/engine/evolution.py`

---

## Phase 5: Dashboard

> รายละเอียด: `phases/phase-5-dashboard.md`

**เป้าหมาย:** Dashboard แสดง live PnL, agent performance, open trades

ไฟล์หลัก:
- `src/dashboard_server.py`
- `dashboard-ui/` (React+Vite)
