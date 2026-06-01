# Crypto AI Trading System — Design Spec

**Date:** 2026-06-01  
**Status:** Approved  
**Project root:** `/home/alfred/crypto-ai/`

---

## Goal

Build a new multi-agent crypto trading system from scratch, using the AI Trading dashboard (5004/mtai) as the design template. Replace Forex/MT5 with multi-exchange crypto (Binance + Bybit). Stop `ai-trading-live` before starting.

---

## Architecture Overview

```
Binance WebSocket ─┐
                   ├─→ ExchangeRouter ─→ SignalEngine ─→ N CryptoAgents ─→ OrderExecutor
Bybit WebSocket  ──┘         │                                                    │
                             └─────────────────── live_state.json ────────────────┘
                                                         │
                                              HTTP API server :3006
                                                         │
                                              React Dashboard :3007 (dev)
```

**3 independent subagents implement in parallel:**
- **Backend** — `src/exchange/` + `src/storage/` + `src/run.py`
- **Algorithm** — `src/engine/`
- **Frontend** — `dashboard-ui/`

---

## Project Structure

```
/home/alfred/crypto-ai/
├── src/
│   ├── exchange/
│   │   ├── __init__.py
│   │   ├── base.py          # Abstract ExchangeFeed interface
│   │   ├── binance.py       # BinanceFeed (WebSocket + REST)
│   │   ├── bybit.py         # BybitFeed (WebSocket + REST)
│   │   └── router.py        # ExchangeRouter — selects feed, paper mode
│   ├── engine/
│   │   ├── __init__.py
│   │   ├── price_history.py # PriceHistory rolling buffer (port from mtai)
│   │   ├── signals.py       # CryptoSignalEngine (technical + LLM)
│   │   ├── agent.py         # CryptoAgent + DNA
│   │   ├── evolution.py     # GA evolution (port from mtai)
│   │   ├── asset_leader.py  # AssetLeader competition (port from mtai)
│   │   └── risk_guardian.py # RiskGuardian USDT-based (port from mtai)
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── history_db.py    # SQLite trade history (port from mtai)
│   │   └── pubsub.py        # SSE pub/sub (port from mtai)
│   └── run.py               # Entrypoint + HTTP API server :3006
├── dashboard-ui/            # Vite + React (clone from mtai/dashboard-ui)
│   ├── src/
│   │   ├── App.jsx
│   │   ├── App.css
│   │   ├── components/
│   │   │   ├── Header.jsx         # fox logo + "Ai เทรด ..เด้อ CRYPTO" + exchange switcher
│   │   │   ├── StatCards.jsx
│   │   │   ├── TickerPanel.jsx    # dynamic pair list + % change
│   │   │   ├── ChartTabs.jsx      # Asset+Graph / Order Book tabs
│   │   │   ├── TvChart.jsx        # lightweight-charts candlestick
│   │   │   ├── OrderBook.jsx      # open positions table
│   │   │   ├── TopAgents.jsx      # right mini panel
│   │   │   ├── AgentGrid.jsx
│   │   │   ├── TradeHistory.jsx
│   │   │   └── PairManager.jsx    # add/remove pairs UI
│   │   └── hooks/
│   │       └── useLiveState.js
│   └── vite.config.js       # proxy /api → :3006, host 0.0.0.0, port 3007
├── tests/
│   ├── test_exchange_router.py
│   ├── test_signal_engine.py
│   ├── test_agent.py
│   └── test_risk_guardian.py
├── .env.example             # BINANCE_API_KEY, BYBIT_API_KEY, EXCHANGE=binance, MODE=paper
└── README.md
```

---

## Backend Spec

### ExchangeFeed Interface (`src/exchange/base.py`)

```python
class ExchangeFeed(ABC):
    async def subscribe(self, pairs: list[str]) -> None: ...
    async def get_price(self, symbol: str) -> Tick: ...
    async def get_ohlcv(self, symbol: str, timeframe: str, count: int) -> list[dict]: ...
    async def place_order(self, symbol, side, qty, sl, tp) -> dict: ...
    async def get_positions(self) -> list[dict]: ...
    async def get_recent_deals(self, hours: int, limit: int) -> list[dict]: ...
    @property
    def name(self) -> str: ...  # "binance" | "bybit"
```

### ExchangeRouter (`src/exchange/router.py`)

- Holds one active feed (Binance or Bybit)
- `paper_mode=True`: intercepts `place_order` → simulates fills locally
- Switch exchange via `POST /api/exchange {"exchange": "bybit"}`
- Tick callbacks fire `on_tick(symbol, price, volume, ts)`

### BinanceFeed (`src/exchange/binance.py`)

- WebSocket: `wss://stream.binance.com:9443/stream?streams=btcusdt@aggTrade/...`
- REST: `https://api.binance.com/api/v3/klines` for OHLCV
- Auth: `BINANCE_API_KEY` + `BINANCE_API_SECRET` env vars (paper mode needs no auth)

### BybitFeed (`src/exchange/bybit.py`)

- WebSocket: `wss://stream.bybit.com/v5/public/spot`
- REST: `https://api.bybit.com/v5/market/kline`
- Auth: `BYBIT_API_KEY` + `BYBIT_API_SECRET` env vars

### HTTP API (`src/run.py`)

| Route | Method | Description |
|-------|--------|-------------|
| `/live_state.json` | GET | Full state snapshot (agents, summary, prices) |
| `/api/mode` | GET/POST | Get or set paper/live mode |
| `/api/exchange` | GET/POST | Get or set active exchange (binance/bybit) |
| `/api/pairs` | GET/POST/DELETE | List, add, remove trading pairs |
| `/api/ohlcv/:symbol` | GET | OHLCV candles `?timeframe=M15&count=200` |
| `/api/order_history` | GET | Paginated trade history |
| `/api/order_history/stream` | GET | SSE stream of new trades |
| `/api/positions` | GET | Open positions |
| `/api/account` | GET | Balance + equity |

---

## Algorithm Spec

### CryptoSignalEngine (`src/engine/signals.py`)

Port from `mtai/src/engine/signals.py` with changes:
- **Remove** session filter (crypto trades 24/7)
- **Keep** technical indicators: RSI, momentum, SMA crossover, MACD
- **Keep** LLM sentiment via bcproxy `http://192.168.1.166:3333`
- **Add** `breakout_atr_signal` and `order_flow_signal` from ai-trading-live
- Signal threshold: confidence ≥ 50 to fire

### CryptoAgent DNA (`src/engine/agent.py`)

```python
@dataclass
class AgentDNA:
    name: str                      # e.g. "CX-BTC-007"
    symbol: str                    # e.g. "BTCUSDT"
    strategy_weights: dict         # {momentum, mean_reversion, grid_scalp, breakout_atr, ...}
    sl_pips: float                 # stop loss distance
    tp_pips: float                 # take profit distance
    fitness: float = 0.0
```

### Dynamic Pair Allocation (GA)

- Evolution runs every 60 minutes
- Fitness = cumulative PnL % over last N trades
- Crossover + mutation reassigns `agent.dna.symbol` to higher-fitness pairs
- Pairs pool = active pairs from `/api/pairs`
- Agents with 0 trades on a pair for 2+ evolution cycles → migrated to better pair

### RiskGuardian (`src/engine/risk_guardian.py`)

Port from `mtai/src/engine/risk_guardian.py` with changes:
- Position sizing in USDT (not lots)
- `MAX_RISK_PCT = 0.01` (1% per trade)
- `MAX_CONCURRENT_POSITIONS = 3` per pair
- `DAILY_DRAWDOWN_LIMIT = 0.05` (5%)
- No pip calc — use price distance % directly

---

## Frontend Spec

### Layout B — Components

**Header.jsx**
- fox_logo.jpg (circle, gold ring) + "Ai เทรด ..เด้อ" + subtext "CRYPTO"
- Exchange Switcher: `[BINANCE] [BYBIT]` toggle buttons
- PAPER/LIVE badge
- Uptime clock

**TickerPanel.jsx** (left panel)
- Dynamic list of active pairs + 24h % change
- Active pair highlighted gold
- "＋ Add pair" button → PairManager modal

**ChartTabs.jsx** (center)
- Tab 1: Asset & Graph (TvChart)
- Tab 2: Order Book (open positions table)

**TvChart.jsx**
- Fetch from `/api/ohlcv/:symbol`
- Poll latest candle every 3s (same as mtai)

**TopAgents.jsx** (right mini panel, new)
- Top 5 agents by PnL%
- Name + symbol + PnL colored green/red

**StatCards.jsx**
- PnL %, Active Agents, Total Trades, Win Rate

**Bottom terminal tabs:** Trade History / AI Agents / Infrastructure

### Theme
- Identical CSS variables to 5004 (dark gold, `#0a0a0f` bg)
- fox_brand.jpg sidebar background
- Font: Inter + Noto Sans Thai

---

## Pre-implementation Step

Before any subagent starts coding:
1. Stop `ai-trading-live` (kill 3 processes)
2. `mkdir -p /home/alfred/crypto-ai`
3. Copy relevant files from mtai as starting point

---

## Non-Goals (explicitly out of scope)

- Telegram notifications (can add later)
- LLM-driven order sizing
- Backtesting engine
- Multiple portfolios
- CEX margin/futures (spot only for now)

---

## Success Criteria

- Dashboard loads at http://localhost:3007 with live prices from Binance
- Paper trades execute when signal confidence ≥ 50
- Exchange switch Binance ↔ Bybit works from dashboard without restart
- Add/remove pairs from dashboard takes effect within 1 tick cycle
- GA evolution runs every 60 min and reassigns agents to better pairs
- All 4 test suites pass
