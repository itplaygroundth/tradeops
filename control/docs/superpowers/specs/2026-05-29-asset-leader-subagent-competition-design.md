# Asset Leader + Sub-agent Competition Framework

**Date:** 2026-05-29
**Scope:** Phase 1 — Sub-agent competition per asset with Hermes LLM judgment

---

## Overview

แทนที่ genetic evolution แบบสุ่ม ระบบนี้ให้ AssetLeader แต่ละ symbol สร้าง Sub-agents 8 ตัวที่มี strategy config ต่างกัน แข่งกันหา best strategy ผ่าน backtest → Hermes เลือก winner → forward-test ยืนยัน → Hermes approve → apply สู่ production agent

---

## Architecture

```
CompetitionScheduler (ทุก 1 ชั่วโมง)
  │
  ▼ (per symbol)
AssetLeader.run_competition(symbol)
  │
  ├─ [Phase 1: Backtest — parallel]
  │   8 SubAgents, แต่ละตัว strategy_weights ต่างกัน
  │   fetch OHLCV 200 bars จาก MT5 bridge
  │   simulate trades → calc Sharpe ratio + PnL + win_rate
  │   asyncio.gather() — รันพร้อมกัน
  │
  ├─ [Phase 2: Hermes selects winner]
  │   POST http://127.0.0.1:20128/v1/chat/completions
  │   payload: scores[8] + market regime + session + account_state
  │   response: {winner_idx, reasoning, confidence}
  │
  ├─ [Phase 3: Forward-test top-3]
  │   Top-3 Sharpe ทำ paper trade 15 นาที บน real MT5 prices
  │   track: PnL, max_drawdown, trade_count
  │
  └─ [Phase 4: Hermes verifies & approves]
      POST Hermes พร้อม forward-test results
      response: {approved: bool, apply_config: dict, reason: str}
      ถ้า approved → update production ForexAgent.dna.strategy_weights
      ถ้า rejected → log reason, ใช้ weights เดิม
```

---

## Components

### 1. `SubAgent` — `src/engine/sub_agent.py`

**Purpose:** Run backtest + forward-test สำหรับ strategy config เดียว

**Interface:**
```python
class SubAgent:
    def __init__(self, symbol: str, strategy_config: dict, mt5_client: MT5Client)
    
    async def run_backtest(candles: list[dict]) -> BacktestResult
    # simulate trades บน historical OHLCV data
    # return: {sharpe, pnl, pnl_pct, win_rate, max_drawdown, trades}
    
    async def run_forward_test(duration_seconds: int = 900) -> ForwardTestResult
    # paper trade บน live prices N วินาที
    # return: {pnl, max_drawdown, trade_count, pnl_pct}
```

**Strategy configs (8 variants):**
| idx | ชื่อ | momentum | mean_rev | grid | llm |
|-----|------|----------|----------|------|-----|
| 0 | momentum-heavy | 0.70 | 0.10 | 0.10 | 0.10 |
| 1 | mean-rev-heavy | 0.10 | 0.70 | 0.10 | 0.10 |
| 2 | grid-heavy | 0.10 | 0.10 | 0.70 | 0.10 |
| 3 | balanced | 0.25 | 0.25 | 0.25 | 0.25 |
| 4 | momentum+mean | 0.40 | 0.40 | 0.10 | 0.10 |
| 5 | grid+sentiment | 0.10 | 0.10 | 0.45 | 0.35 |
| 6 | random-A | random seed 42 | | | |
| 7 | random-B | random seed 99 | | | |

**Backtest simulation logic:**
- ใช้ signal จาก `ForexSignalEngine` ที่มีอยู่แล้ว (reuse)
- ป้อน candles ทีละ bar → generate signal → simulate entry/exit ตาม SL/TP pips จาก DNA
- คำนวณ Sharpe: `mean(daily_returns) / std(daily_returns) * sqrt(252)`

---

### 2. `AssetLeader` — `src/engine/asset_leader.py`

**Purpose:** Orchestrate competition สำหรับ 1 symbol

**Interface:**
```python
class AssetLeader:
    def __init__(self, symbol: str, production_agent: ForexAgent,
                 mt5_client: MT5Client, hermes_client: HermesClient)
    
    async def run_competition() -> CompetitionResult
    # รัน 4 phases แล้ว return ผลลัพธ์
    
    def _apply_winner(config: dict)
    # update production_agent.dna.strategy_weights
```

---

### 3. `HermesClient` — `src/engine/hermes_client.py`

**Purpose:** REST client ไปหา Hermes API

**Hermes endpoint:** `http://127.0.0.1:20128/v1/chat/completions`
**Model:** `ClaudePro`

**Phase 2 prompt template:**
```
You are an expert forex trading strategy analyst.
Symbol: {symbol} | Regime: {regime} | Session: {session}
Account balance: ${balance} | Equity: ${equity}

Sub-agent backtest results (Sharpe ratio, higher = better):
{for each sub_agent: idx, strategy_name, sharpe, pnl_pct, win_rate, max_drawdown}

Select the best strategy for CURRENT market conditions.
Consider: regime fit, risk-adjusted returns, drawdown tolerance.

Respond in JSON: {"winner_idx": int, "reasoning": str, "confidence": float 0-1}
```

**Phase 4 prompt template:**
```
Forward-test results for top-3 strategies over 15 minutes of live trading:
{for each: strategy_name, pnl, max_drawdown, trade_count}

Should we apply the winner strategy to the production agent?
Consider: is the PnL positive? Is max_drawdown acceptable (<2%)? 

Respond in JSON: {"approved": bool, "apply_config": {strategy_weights dict}, "reason": str}
```

---

### 4. `CompetitionScheduler` — `src/engine/competition_scheduler.py`

**Purpose:** เรียก AssetLeader ทุก 1 ชั่วโมง สำหรับทุก symbol

**Integration กับ `ForexAgentManager`:**
- เพิ่ม `competition_scheduler` เป็น attribute ของ `ForexAgentManager`
- เรียก `scheduler.tick()` ใน `on_tick()` loop ที่มีอยู่แล้ว
- ใช้ interval แยกจาก evolution cycle (ไม่แทนที่ — รันควบคู่)

---

## Files

| File | Action |
|------|--------|
| `src/engine/sub_agent.py` | New |
| `src/engine/asset_leader.py` | New |
| `src/engine/hermes_client.py` | New |
| `src/engine/competition_scheduler.py` | New |
| `src/engine/agent_manager.py` | Modify — wire scheduler |

---

## Data Structures

```python
@dataclass
class BacktestResult:
    sharpe: float
    pnl: float
    pnl_pct: float
    win_rate: float
    max_drawdown: float
    trades: int
    strategy_config: dict

@dataclass
class CompetitionResult:
    symbol: str
    winner_config: dict
    winner_sharpe: float
    hermes_reasoning: str
    hermes_confidence: float
    forward_pnl: float
    approved: bool
    applied: bool
    timestamp: float
```

---

## Error Handling

- Hermes unreachable → fallback to top Sharpe winner (algorithmic only)
- MT5 offline → skip competition, keep current weights
- Forward-test returns 0 trades → re-run with longer duration (30 นาที), ถ้ายังไม่มีสัญญาณ → skip apply
- Competition result บันทึกลง `live_state.json` ใต้ `summary.last_competition` สำหรับ dashboard

---

## Out of Scope (Phase 2)

- Hermes generate strategy configs (จุดที่ 3) — phase 2
- Multi-asset Leader coordination — phase 2
- Telegram notification เมื่อ apply winner — phase 2
