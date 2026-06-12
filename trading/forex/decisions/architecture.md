# Architecture Decisions — MTAI Forex AI Trading

## ADR-001: MT5 API Server บน Windows (แยก machine)

**Decision:** รัน `mt5_api_server.py` บน Windows machine แยก ไม่ใช่ Wine บน Linux

**Reason:**
- MetaTrader5 Python library รองรับ Windows เท่านั้น (native COM)
- Wine + MT5 unstable ใน production
- HTTP API bridge ทำให้ Linux engine ไม่ผูกกับ OS ของ MT5

**Trade-off:** ต้องมี Windows machine เพิ่ม (อาจใช้ Windows VM บน same host)

---

## ADR-002: 25 Agents (ไม่ใช่ 100 อย่าง crypto)

**Decision:** ลดจาก 100 → 25 agents

**Reason:**
- Forex position limit จาก Risk Guardian: max 3 concurrent positions
- 100 agents สร้าง signal ที่ส่วนใหญ่ถูก block → waste compute
- Forex trades ต่อ agent น้อยกว่า crypto (~1-3 trades/day vs 10-20 trades/day)
- Evolution warm-up ต้องการ 30 trades → 25 agents ใช้เวลาพอเหมาะ

---

## ADR-003: Symbol Specialization (1 agent = 1 symbol)

**Decision:** แต่ละ agent specialise ใน **symbol เดียว** ไม่ใช่ trade ทุก symbol

**Reason:**
- Forex symbols มี personality ต่างกัน (XAUUSD volatile, EURUSD liquid, USDJPY session-dependent)
- Agent ที่ learn เฉพาะ XAUUSD จะดีกว่า agent generic
- ลด complexity: agent ไม่ต้องเลือก symbol + strategy พร้อมกัน

**Implementation:**
- `ForexAgentDNA.symbol` = fixed ตอน create
- Evolution preserve symbol distribution (ต้องมี agent ทุก symbol)

---

## ADR-004: ลบ Polymarket, ใช้ Session-Based Macro

**Decision:** แทน `polymarket_macro` ด้วย `forex_macro.py` (session + economic calendar)

**Reason:**
- Polymarket ไม่มี forex markets
- Forex macro signal = session timing + high-impact news
- Phase 1: rule-based session detection (ไม่ต้อง API)
- Phase 2 (future): connect ForexFactory/investing.com economic calendar API

---

## ADR-005: pip-based SL/TP (ไม่ใช่ % of price)

**Decision:** SL/TP เก็บเป็น pips ไม่ใช่ % จาก entry

**Reason:**
- Forex convention คือ pips
- pip value ต่างกันต่อ symbol (USDJPY pip = 0.01, EURUSD = 0.0001)
- Risk Guardian คำนวณ lot size จาก pip risk ได้ตรงกว่า % based

---

## ADR-006: Algorithm Reuse Strategy

**Decision:** ใช้ algorithm เดิมจาก `ai-trading-live` โดยตรง ไม่เขียนใหม่

| Module | Action |
|--------|--------|
| `PriceHistory` | Copy ทั้งหมด — ไม่แก้บรรทัดเดียว |
| `mean_reversion` | Copy — ไม่แก้ |
| `grid_scalp` | Copy — ไม่แก้ |
| `lstm_momentum` | Copy — ไม่แก้ |
| `evolution.py` logic | Copy + forex DNA |
| `llm_sentiment` prompt | เปลี่ยน context string |
| `polymarket_macro` | ทิ้ง → เขียนใหม่เป็น forex_macro |
| Binance WebSocket | ทิ้ง → MT5Feed |
| CCXT Binance executor | ทิ้ง → MT5Client |

---

## ADR-007: Paper Mode First

**Decision:** เริ่ม paper mode ก่อน — ไม่ส่ง live order จนกว่าจะผ่าน 2 สัปดาห์ paper

**Reason:**
- Forex leverage สูง → loss จริงเร็วกว่า crypto
- Algorithm ยังไม่ผ่าน walk-forward test บน forex data
- MT5 API server ยังไม่ tested ใน production

**Live criteria:**
- Paper mode profit 2+ สัปดาห์ต่อเนื่อง
- Win rate > 40%
- Max drawdown < 5%
- Sharpe > 1.0

---

## Project File Structure (Final)

```
/home/alfred/mtai/
├── README.md
├── PLAN.md
├── phases/
│   ├── phase-1-mt5-bridge.md
│   ├── phase-2-signal-engine.md
│   ├── phase-3-risk-engine.md
│   ├── phase-4-agent-system.md
│   └── phase-5-dashboard.md
├── decisions/
│   └── architecture.md          ← this file
└── src/
    ├── run.py                    ← entry point
    ├── mt5_bridge/
    │   ├── __init__.py
    │   ├── client.py             ← HTTP client → MT5 API server
    │   ├── feed.py               ← WebSocket price stream
    │   ├── pip_calc.py           ← pip value + lot sizing
    │   └── windows_server/
    │       ├── mt5_api_server.py ← รันบน Windows
    │       └── requirements.txt
    ├── engine/
    │   ├── __init__.py
    │   ├── price_history.py      ← copied จาก ai-trading-live (ไม่แก้)
    │   ├── signals.py            ← ForexSignalEngine
    │   ├── forex_macro.py        ← แทน polymarket_macro
    │   ├── dna.py                ← ForexAgentDNA
    │   ├── agent.py              ← ForexAgent
    │   ├── risk_guardian.py      ← ForexRiskGuardian
    │   ├── dynamic_risk.py       ← regime-based risk params
    │   ├── evolution.py          ← genetic algorithm
    │   └── agent_manager.py     ← main trading loop
    ├── config/
    │   └── settings.yaml         ← MT5 server URL, symbols, risk params
    ├── dashboard/
    │   └── index.html            ← simple dashboard
    ├── tests/
    │   ├── test_mt5_bridge.py
    │   ├── test_signals.py
    │   ├── test_risk.py
    │   └── test_integration.py
    └── scripts/
        └── mtai.service          ← systemd service
```
