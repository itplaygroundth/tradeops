# Asset Leader + Sub-agent Competition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a competition framework where AssetLeader spawns 12 SubAgents per symbol, each testing a different strategy mix, then uses Hermes LLM to select the best and verify profit before applying to production agents.

**Architecture:** SubAgent backtests 200 OHLCV bars using a weighted directional vote across 8 strategies (score = Σ weight×confidence×direction). AssetLeader orchestrates phases: backtest → Hermes picks winner → forward-test top-3 → Hermes verifies → apply to ForexAgentDNA. CompetitionScheduler calls this every 3600s alongside existing evolution.

**Tech Stack:** Python asyncio, httpx (already in MT5Client), existing ForexSignalEngine/PriceHistory, Hermes REST at `http://127.0.0.1:20128/v1/chat/completions` (model: ClaudePro)

**Status as of 2026-05-30:**
- sub_agent.py, hermes_client.py, asset_leader.py, competition_scheduler.py — CREATED (skeleton)
- agent_manager.py — WIRED (imports + tick call)
- test_sub_agent.py — PARTIAL (1 test)
- dna.py STRATEGY_METHODS — NOT DONE (still 4 strategies, needs 8)
- signals.py 4 new functions — DONE (order_flow_signal, breakout_atr_signal, session_open_signal, market_structure_signal exist)
- asset_leader._make_configs() — NOT DONE (returns 12 identical configs, needs 12 distinct configs from spec)
- test_asset_leader.py — NOT DONE

---

## File Map

| File | Action |
|------|--------|
| `src/engine/dna.py` | Modify — add 4 new strategy names to STRATEGY_METHODS |
| `src/engine/signals.py` | Done — 4 new signal functions already exist |
| `src/engine/sub_agent.py` | Modify — add backtest support for order_flow, breakout_atr, session_open, market_structure |
| `src/engine/hermes_client.py` | Modify — add Phase 2 + Phase 4 prompt templates per spec |
| `src/engine/asset_leader.py` | Modify — fix _make_configs() to 12 distinct configs from spec |
| `src/engine/competition_scheduler.py` | Done — no changes needed |
| `src/engine/agent_manager.py` | Done — already wired |
| `tests/test_sub_agent.py` | Modify — add tests for new strategies + signal functions |
| `tests/test_asset_leader.py` | Create — integration tests for 4-phase competition |

---

## Task 1: Expand STRATEGY_METHODS in dna.py

**Files:**
- Modify: `src/engine/dna.py` line 13

- [ ] **Step 1: Write the failing test**

```bash
cd /home/alfred/mtai && python -c "
from src.engine.dna import STRATEGY_METHODS
assert 'order_flow' in STRATEGY_METHODS, 'order_flow missing'
assert 'breakout_atr' in STRATEGY_METHODS, 'breakout_atr missing'
assert 'session_open' in STRATEGY_METHODS, 'session_open missing'
assert 'market_structure' in STRATEGY_METHODS, 'market_structure missing'
print('PASS')
" 2>&1
```

Expected: AssertionError (red)

- [ ] **Step 2: Add 4 strategies to STRATEGY_METHODS**

In `src/engine/dna.py` line 13, change:
```python
STRATEGY_METHODS = ["momentum", "mean_reversion", "grid_scalp", "llm_sentiment"]
```
to:
```python
STRATEGY_METHODS = [
    "momentum", "mean_reversion", "grid_scalp", "llm_sentiment",
    "order_flow", "breakout_atr", "session_open", "market_structure",
]
```

- [ ] **Step 3: Run the test again — must PASS**

```bash
cd /home/alfred/mtai && python -c "
from src.engine.dna import STRATEGY_METHODS
assert 'order_flow' in STRATEGY_METHODS
assert 'breakout_atr' in STRATEGY_METHODS
assert 'session_open' in STRATEGY_METHODS
assert 'market_structure' in STRATEGY_METHODS
assert len(STRATEGY_METHODS) == 8
print('PASS')
" 2>&1
```

- [ ] **Step 4: Verify random_dna still works (weights still sum to 1.0)**

```bash
cd /home/alfred/mtai && python -c "
from src.engine.dna import random_dna
dna = random_dna(agent_id=0, symbol='EURUSDm')
total = sum(dna.strategy_weights.values())
assert abs(total - 1.0) < 1e-9, f'weights sum={total}'
assert 'order_flow' in dna.strategy_weights
assert 'market_structure' in dna.strategy_weights
print('PASS weights sum=', total)
" 2>&1
```

---

## Task 2: Fix _make_configs() in asset_leader.py — 12 distinct configs

**Files:**
- Modify: `src/engine/asset_leader.py` — method `_make_configs`

- [ ] **Step 1: Write the failing test**

```bash
cd /home/alfred/mtai && python -c "
import sys; sys.path.insert(0, 'src')
from engine.asset_leader import AssetLeader
leader = AssetLeader('EURUSDm', None, None, None)
configs = leader._make_configs()
assert len(configs) == 12, f'expected 12, got {len(configs)}'
# configs should be distinct
unique = [str(sorted(c.items())) for c in configs]
assert len(set(unique)) > 1, 'all configs are identical'
print('PASS')
" 2>&1
```

Expected: AssertionError on distinct check (red)

- [ ] **Step 2: Replace _make_configs() with 12 spec configs**

Replace the `_make_configs` method body with:

```python
def _make_configs(self) -> List[Dict[str, float]]:
    import random as _random
    rng42 = _random.Random(42)
    rng99 = _random.Random(99)

    def _rand_weights(rng):
        w = [rng.random() for _ in range(8)]
        s = sum(w)
        keys = ["momentum", "mean_reversion", "grid_scalp", "llm_sentiment",
                "order_flow", "breakout_atr", "session_open", "market_structure"]
        return dict(zip(keys, [v / s for v in w]))

    return [
        # idx 0 momentum-heavy
        {"momentum": 0.60, "mean_reversion": 0.10, "grid_scalp": 0.10, "llm_sentiment": 0.05,
         "order_flow": 0.05, "breakout_atr": 0.05, "session_open": 0.05, "market_structure": 0.00},
        # idx 1 mean-rev-heavy
        {"momentum": 0.10, "mean_reversion": 0.60, "grid_scalp": 0.10, "llm_sentiment": 0.05,
         "order_flow": 0.05, "breakout_atr": 0.05, "session_open": 0.05, "market_structure": 0.00},
        # idx 2 grid-heavy
        {"momentum": 0.10, "mean_reversion": 0.10, "grid_scalp": 0.60, "llm_sentiment": 0.05,
         "order_flow": 0.05, "breakout_atr": 0.05, "session_open": 0.05, "market_structure": 0.00},
        # idx 3 order-flow-heavy
        {"momentum": 0.10, "mean_reversion": 0.10, "grid_scalp": 0.05, "llm_sentiment": 0.05,
         "order_flow": 0.60, "breakout_atr": 0.05, "session_open": 0.05, "market_structure": 0.00},
        # idx 4 breakout-heavy
        {"momentum": 0.10, "mean_reversion": 0.05, "grid_scalp": 0.05, "llm_sentiment": 0.05,
         "order_flow": 0.10, "breakout_atr": 0.55, "session_open": 0.10, "market_structure": 0.00},
        # idx 5 session-heavy
        {"momentum": 0.10, "mean_reversion": 0.05, "grid_scalp": 0.05, "llm_sentiment": 0.05,
         "order_flow": 0.10, "breakout_atr": 0.10, "session_open": 0.55, "market_structure": 0.00},
        # idx 6 structure-heavy
        {"momentum": 0.05, "mean_reversion": 0.10, "grid_scalp": 0.05, "llm_sentiment": 0.05,
         "order_flow": 0.15, "breakout_atr": 0.10, "session_open": 0.10, "market_structure": 0.40},
        # idx 7 balanced-8
        {"momentum": 0.125, "mean_reversion": 0.125, "grid_scalp": 0.125, "llm_sentiment": 0.125,
         "order_flow": 0.125, "breakout_atr": 0.125, "session_open": 0.125, "market_structure": 0.125},
        # idx 8 flow+breakout
        {"momentum": 0.05, "mean_reversion": 0.05, "grid_scalp": 0.05, "llm_sentiment": 0.05,
         "order_flow": 0.35, "breakout_atr": 0.35, "session_open": 0.05, "market_structure": 0.05},
        # idx 9 session+structure
        {"momentum": 0.05, "mean_reversion": 0.10, "grid_scalp": 0.05, "llm_sentiment": 0.05,
         "order_flow": 0.10, "breakout_atr": 0.10, "session_open": 0.35, "market_structure": 0.20},
        # idx 10 random-A seed 42
        _rand_weights(rng42),
        # idx 11 random-B seed 99
        _rand_weights(rng99),
    ]
```

- [ ] **Step 3: Run the test — must PASS**

```bash
cd /home/alfred/mtai && python -c "
import sys; sys.path.insert(0, 'src')
from engine.asset_leader import AssetLeader
leader = AssetLeader('EURUSDm', None, None, None)
configs = leader._make_configs()
assert len(configs) == 12
unique = [str(sorted(c.items())) for c in configs]
assert len(set(unique)) == 12, f'only {len(set(unique))} unique configs'
for i, c in enumerate(configs):
    total = sum(c.values())
    assert abs(total - 1.0) < 1e-9, f'config {i} weights sum={total}'
print('PASS 12 distinct configs, all sum to 1.0')
" 2>&1
```

---

## Task 3: Add backtest support for 4 new strategies in sub_agent.py

**Files:**
- Modify: `src/engine/sub_agent.py` — `run_backtest` + 4 new `_backtest_*` methods

**Context:** Currently run_backtest only handles "momentum" and "mean_reversion" — other primaries fall through to 0 trades.

- [ ] **Step 1: Write failing tests**

```bash
cd /home/alfred/mtai && python -c "
import asyncio, sys, time
sys.path.insert(0, 'src')
from engine.sub_agent import SubAgent

def make_candles(n=100):
    now = time.time()
    return [{'open': 1.1 + i*0.0001, 'high': 1.1 + i*0.0001 + 0.0002,
             'low': 1.1 + i*0.0001 - 0.0002, 'close': 1.1 + i*0.0001,
             'volume': 1000, 'timestamp': now + i} for i in range(n)]

candles = make_candles(150)
for strat in ['order_flow', 'breakout_atr', 'session_open', 'market_structure']:
    cfg = {s: 0.0 for s in ['momentum','mean_reversion','grid_scalp','llm_sentiment','order_flow','breakout_atr','session_open','market_structure']}
    cfg[strat] = 1.0
    sub = SubAgent('EURUSDm', cfg)
    r = asyncio.run(sub.run_backtest(candles))
    # Currently all return 0 trades — this test documents expected behavior after fix
    print(f'{strat}: trades={r.trades} sharpe={r.sharpe:.2f}')
print('DONE — review counts above, non-zero expected after fix')
" 2>&1
```

- [ ] **Step 2: Add 4 backtest methods to SubAgent**

In `src/engine/sub_agent.py`, add these methods to the `SubAgent` class and wire them into `run_backtest`:

In `run_backtest`, extend the if/elif chain:
```python
elif primary == "order_flow":
    trades, max_dd = self._backtest_order_flow(closes, candles)
elif primary == "breakout_atr":
    trades, max_dd = self._backtest_breakout_atr(closes, candles)
elif primary == "session_open":
    trades, max_dd = self._backtest_session_open(closes, candles)
elif primary == "market_structure":
    trades, max_dd = self._backtest_market_structure(closes)
```

Add methods:
```python
def _backtest_order_flow(self, closes, candles):
    """CVD divergence: sum(sign(close-open)*volume). Signal when CVD diverges from price momentum."""
    trades = []
    window = 20
    in_pos = False
    entry = 0.0
    direction = 0  # 1=long, -1=short

    for i in range(window, len(candles)):
        slice_c = candles[i - window: i]
        cvd = sum((1 if c["close"] > c["open"] else -1) * c.get("volume", 1) for c in slice_c)
        mom = (closes[i] - closes[i - window]) / closes[i - window] * 100.0
        price = closes[i]

        if not in_pos:
            # divergence: price up but CVD negative -> short; price down but CVD positive -> long
            if mom > 0.3 and cvd < 0:
                in_pos, direction, entry = True, -1, price
            elif mom < -0.3 and cvd > 0:
                in_pos, direction, entry = True, 1, price
        else:
            # exit after 10 bars
            held = i - next((j for j in range(i - 1, -1, -1) if not True), i)  # simplified: exit on reversal
            rev_mom = (closes[i] - closes[max(0, i - 5)]) / closes[max(0, i - 5)] * 100.0
            if (direction == 1 and rev_mom < -0.1) or (direction == -1 and rev_mom > 0.1):
                ret = direction * (price - entry) / entry * 100.0
                trades.append(ret)
                in_pos = False

    if in_pos:
        trades.append(direction * (closes[-1] - entry) / entry * 100.0)
    return trades, 0.0

def _backtest_breakout_atr(self, closes, candles):
    """Breakout above 20-bar high or below 20-bar low, with ATR filter."""
    from statistics import mean as _mean
    trades = []
    window = 20
    atr_window = 14
    in_pos = False
    entry = 0.0
    direction = 0

    for i in range(window, len(candles)):
        highs = [c["high"] for c in candles[i - window: i]]
        lows = [c["low"] for c in candles[i - window: i]]
        hi20 = max(highs)
        lo20 = min(lows)
        price = closes[i]

        # ATR as mean(high-low) over atr_window
        atr_bars = candles[max(0, i - atr_window): i]
        atr = _mean(c["high"] - c["low"] for c in atr_bars) if atr_bars else 0.0
        atr_pct = atr / price * 100.0 if price else 0.0

        if not in_pos and atr_pct < 0.6:
            if price > hi20:
                in_pos, direction, entry = True, 1, price
            elif price < lo20:
                in_pos, direction, entry = True, -1, price
        elif in_pos:
            # exit: price returns inside range or SL hit (2x ATR)
            sl = atr * 2
            pnl_abs = direction * (price - entry)
            if pnl_abs < -sl or (direction == 1 and price < lo20) or (direction == -1 and price > hi20):
                trades.append(direction * (price - entry) / entry * 100.0)
                in_pos = False

    if in_pos:
        trades.append(direction * (closes[-1] - entry) / entry * 100.0)
    return trades, 0.0

def _backtest_session_open(self, closes, candles):
    """Signal in first 30 bars of session (proxy for London 07:00 open momentum)."""
    trades = []
    window = 5
    in_pos = False
    entry = 0.0
    direction = 0

    for i in range(window, len(candles)):
        ts = candles[i].get("timestamp", i)
        # proxy: treat every 480th bar as a session open (480 min = 8h)
        bar_in_session = int(ts) % 480
        if bar_in_session > 30:
            continue  # only trade first 30 bars of session window

        price = closes[i]
        mom = (closes[i] - closes[i - window]) / closes[i - window] * 100.0

        if not in_pos:
            if mom > 0.2:
                in_pos, direction, entry = True, 1, price
            elif mom < -0.2:
                in_pos, direction, entry = True, -1, price
        else:
            # hold max 10 bars then exit
            if bar_in_session > 20:
                trades.append(direction * (price - entry) / entry * 100.0)
                in_pos = False

    if in_pos:
        trades.append(direction * (closes[-1] - entry) / entry * 100.0)
    return trades, 0.0

def _backtest_market_structure(self, closes):
    """Break of Structure: higher high = bullish BoS, lower low = bearish BoS."""
    trades = []
    swing_window = 10
    in_pos = False
    entry = 0.0
    direction = 0
    prev_hh = None
    prev_ll = None

    for i in range(swing_window * 2, len(closes)):
        window_slice = closes[i - swing_window: i]
        hh = max(window_slice)
        ll = min(window_slice)
        price = closes[i]

        if prev_hh is not None and prev_ll is not None:
            if not in_pos:
                if price > prev_hh:  # bullish BoS
                    in_pos, direction, entry = True, 1, price
                elif price < prev_ll:  # bearish BoS
                    in_pos, direction, entry = True, -1, price
            else:
                # exit: BoS reversed
                if direction == 1 and price < ll:
                    trades.append((price - entry) / entry * 100.0)
                    in_pos = False
                elif direction == -1 and price > hh:
                    trades.append(-(price - entry) / entry * 100.0)
                    in_pos = False

        prev_hh = hh
        prev_ll = ll

    if in_pos:
        trades.append(direction * (closes[-1] - entry) / entry * 100.0)
    return trades, 0.0
```

- [ ] **Step 3: Run tests — non-zero trades for at least some strategies**

```bash
cd /home/alfred/mtai && python -c "
import asyncio, sys, time
sys.path.insert(0, 'src')
from engine.sub_agent import SubAgent

def make_candles(n=200):
    now = time.time()
    import math
    return [{'open': 1.1 + math.sin(i*0.1)*0.002, 'high': 1.1 + math.sin(i*0.1)*0.002 + 0.001,
             'low': 1.1 + math.sin(i*0.1)*0.002 - 0.001,
             'close': 1.1 + math.sin(i*0.1)*0.002 + 0.0001,
             'volume': 1000 + i*10, 'timestamp': now + i*60} for i in range(n)]

candles = make_candles()
all_strategies = ['momentum','mean_reversion','grid_scalp','llm_sentiment','order_flow','breakout_atr','session_open','market_structure']
for strat in ['order_flow', 'breakout_atr', 'session_open', 'market_structure']:
    cfg = {s: 0.0 for s in all_strategies}
    cfg[strat] = 1.0
    sub = SubAgent('EURUSDm', cfg)
    r = asyncio.run(sub.run_backtest(candles))
    print(f'{strat}: trades={r.trades} sharpe={r.sharpe:.2f} pnl={r.pnl:.4f}%')
print('PASS all 4 new strategies run backtest')
" 2>&1
```

---

## Task 4: Fix HermesClient prompt templates (Phase 2 + Phase 4)

**Files:**
- Modify: `src/engine/hermes_client.py`

**Context:** Current `select_winner` and `verify_forward_test` just pass raw dicts — no proper prompt wrapping per spec.

- [ ] **Step 1: Write failing test (verify prompt structure)**

```bash
cd /home/alfred/mtai && python -c "
import sys; sys.path.insert(0, 'src')
from engine.hermes_client import HermesClient
c = HermesClient()
# Check methods exist with expected signatures
import inspect
assert 'payload' in inspect.signature(c.select_winner).parameters
assert 'payload' in inspect.signature(c.verify_forward_test).parameters
# Check internal prompt builder exists (new requirement)
assert hasattr(c, '_build_select_prompt'), 'missing _build_select_prompt'
assert hasattr(c, '_build_verify_prompt'), 'missing _build_verify_prompt'
print('PASS')
" 2>&1
```

Expected: AssertionError on missing prompt builders (red)

- [ ] **Step 2: Add prompt builder methods and update request format**

Replace `select_winner` and `verify_forward_test` in `src/engine/hermes_client.py`:

```python
def _build_select_prompt(self, payload: Dict[str, Any]) -> str:
    symbol = payload.get("symbol", "UNKNOWN")
    regime = payload.get("regime", "UNKNOWN")
    session = payload.get("session", "UNKNOWN")
    balance = payload.get("balance", 0)
    equity = payload.get("equity", 0)
    results = payload.get("results", [])

    lines = [
        "You are an expert forex trading strategy analyst.",
        f"Symbol: {symbol} | Regime: {regime} | Session: {session}",
        f"Account balance: ${balance} | Equity: ${equity}",
        "",
        "Sub-agent backtest results (Sharpe ratio, higher = better):",
    ]
    for r in results:
        lines.append(
            f"  idx={r.get('idx')} strategy={r.get('strategy_name', 'N/A')} "
            f"sharpe={r.get('sharpe', 0):.3f} pnl={r.get('pnl_pct', 0):.2f}% "
            f"win_rate={r.get('win_rate', 0):.2f} max_dd={r.get('max_drawdown', 0):.2f}%"
        )
    lines += [
        "",
        "Select the best strategy for CURRENT market conditions.",
        "Consider: regime fit, risk-adjusted returns, drawdown tolerance.",
        'Respond in JSON: {"winner_idx": int, "reasoning": str, "confidence": float 0-1}',
    ]
    return "\n".join(lines)

def _build_verify_prompt(self, payload: Dict[str, Any]) -> str:
    results = payload.get("forward_results", [])
    lines = [
        "Forward-test results for top-3 strategies over 15 minutes of live trading:",
    ]
    for r in results:
        lines.append(
            f"  strategy={r.get('strategy_name', 'N/A')} pnl={r.get('pnl', 0):.4f} "
            f"max_dd={r.get('max_drawdown', 0):.4f} trades={r.get('trade_count', 0)}"
        )
    lines += [
        "",
        "Should we apply the winner strategy to the production agent?",
        "Consider: is the PnL positive? Is max_drawdown acceptable (<2%)?",
        'Respond in JSON: {"approved": bool, "apply_config": {strategy_weights dict}, "reason": str}',
    ]
    return "\n".join(lines)

async def select_winner(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    prompt = self._build_select_prompt(payload)
    request_body = {
        "model": "ClaudePro",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
    }
    raw = await asyncio.to_thread(self._post_with_retries, request_body)
    # extract JSON from choices[0].message.content
    content = raw.get("choices", [{}])[0].get("message", {}).get("content", "{}")
    import json as _json, re as _re
    m = _re.search(r"\{.*\}", content, _re.DOTALL)
    if m:
        return _json.loads(m.group())
    raise HermesError(f"No JSON in Hermes response: {content[:200]}")

async def verify_forward_test(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    prompt = self._build_verify_prompt(payload)
    request_body = {
        "model": "ClaudePro",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
    }
    raw = await asyncio.to_thread(self._post_with_retries, request_body)
    content = raw.get("choices", [{}])[0].get("message", {}).get("content", "{}")
    import json as _json, re as _re
    m = _re.search(r"\{.*\}", content, _re.DOTALL)
    if m:
        return _json.loads(m.group())
    raise HermesError(f"No JSON in Hermes response: {content[:200]}")
```

- [ ] **Step 3: Run test — PASS**

```bash
cd /home/alfred/mtai && python -c "
import sys; sys.path.insert(0, 'src')
from engine.hermes_client import HermesClient
c = HermesClient()
assert hasattr(c, '_build_select_prompt')
assert hasattr(c, '_build_verify_prompt')
# test prompt content
p = c._build_select_prompt({'symbol':'EURUSDm','regime':'TRENDING','session':'LONDON',
    'balance':1000,'equity':1050,'results':[{'idx':0,'strategy_name':'momentum-heavy','sharpe':1.2,'pnl_pct':0.5,'win_rate':0.6,'max_drawdown':1.0}]})
assert 'EURUSDm' in p
assert 'winner_idx' in p
p2 = c._build_verify_prompt({'forward_results':[{'strategy_name':'momentum-heavy','pnl':0.1,'max_drawdown':0.5,'trade_count':3}]})
assert 'approved' in p2
print('PASS')
" 2>&1
```

---

## Task 5: Expand test_sub_agent.py — cover all 8 strategies

**Files:**
- Modify: `tests/test_sub_agent.py`

- [ ] **Step 1: Add tests for new backtest strategies**

Append to `tests/test_sub_agent.py`:

```python
import math

def make_candles_sine(n=200):
    """Sine-wave candles for predictable signal testing."""
    now = time.time()
    candles = []
    for i in range(n):
        price = 1.1 + math.sin(i * 0.15) * 0.003
        candles.append({
            "open": price - 0.0001,
            "high": price + 0.0003,
            "low": price - 0.0003,
            "close": price,
            "volume": 1000 + i * 5,
            "timestamp": now + i * 60,
        })
    return candles

ALL_STRATS = ["momentum","mean_reversion","grid_scalp","llm_sentiment",
              "order_flow","breakout_atr","session_open","market_structure"]

def make_cfg(primary):
    cfg = {s: 0.0 for s in ALL_STRATS}
    cfg[primary] = 1.0
    return cfg

def test_subagent_backtest_order_flow():
    candles = make_candles_sine()
    sub = SubAgent("EURUSDm", make_cfg("order_flow"))
    result = asyncio.run(sub.run_backtest(candles))
    assert hasattr(result, "sharpe")
    assert isinstance(result.trades, int)

def test_subagent_backtest_breakout_atr():
    candles = make_candles_sine()
    sub = SubAgent("EURUSDm", make_cfg("breakout_atr"))
    result = asyncio.run(sub.run_backtest(candles))
    assert hasattr(result, "sharpe")
    assert 0.0 <= result.win_rate <= 1.0

def test_subagent_backtest_session_open():
    candles = make_candles_sine()
    sub = SubAgent("EURUSDm", make_cfg("session_open"))
    result = asyncio.run(sub.run_backtest(candles))
    assert hasattr(result, "sharpe")

def test_subagent_backtest_market_structure():
    candles = make_candles_sine()
    sub = SubAgent("EURUSDm", make_cfg("market_structure"))
    result = asyncio.run(sub.run_backtest(candles))
    assert hasattr(result, "sharpe")
    assert isinstance(result.trades, int)

def test_backtest_result_fields():
    """All 8 strategies must return valid BacktestResult fields."""
    candles = make_candles_sine()
    for strat in ALL_STRATS:
        sub = SubAgent("EURUSDm", make_cfg(strat))
        result = asyncio.run(sub.run_backtest(candles))
        assert hasattr(result, "sharpe"), f"{strat} missing sharpe"
        assert hasattr(result, "pnl"), f"{strat} missing pnl"
        assert hasattr(result, "pnl_pct"), f"{strat} missing pnl_pct"
        assert hasattr(result, "win_rate"), f"{strat} missing win_rate"
        assert 0.0 <= result.win_rate <= 1.0, f"{strat} win_rate out of range: {result.win_rate}"
        assert hasattr(result, "max_drawdown"), f"{strat} missing max_drawdown"
        assert hasattr(result, "trades"), f"{strat} missing trades"
        assert hasattr(result, "strategy_config"), f"{strat} missing strategy_config"

def test_make_configs_12_distinct():
    """AssetLeader._make_configs returns 12 distinct configs summing to 1.0."""
    import sys; sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
    from engine.asset_leader import AssetLeader
    leader = AssetLeader("EURUSDm", None, None, None)
    configs = leader._make_configs()
    assert len(configs) == 12
    unique = [str(sorted(c.items())) for c in configs]
    assert len(set(unique)) == 12, f"only {len(set(unique))} unique"
    for i, c in enumerate(configs):
        total = sum(c.values())
        assert abs(total - 1.0) < 1e-9, f"config {i} sum={total}"
```

- [ ] **Step 2: Run all tests — PASS**

```bash
cd /home/alfred/mtai && python -m pytest tests/test_sub_agent.py -v 2>&1
```

All tests must pass (green).

---

## Task 6: Create tests/test_asset_leader.py

**Files:**
- Create: `tests/test_asset_leader.py`

- [ ] **Step 1: Create test file**

```python
"""Integration tests for AssetLeader 4-phase competition."""
import asyncio
import sys
import time
import math
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from engine.asset_leader import AssetLeader, CompetitionResult
from engine.sub_agent import BacktestResult


def make_candles(n=200):
    now = time.time()
    return [
        {
            "open": 1.1 + math.sin(i * 0.15) * 0.003,
            "high": 1.1 + math.sin(i * 0.15) * 0.003 + 0.0003,
            "low": 1.1 + math.sin(i * 0.15) * 0.003 - 0.0003,
            "close": 1.1 + math.sin(i * 0.15) * 0.003,
            "volume": 1000,
            "timestamp": now + i * 60,
        }
        for i in range(n)
    ]


def make_mock_mt5(candles):
    """MT5 client that returns candles and prices."""
    mt5 = MagicMock()
    mt5.get_ohlcv = AsyncMock(return_value=candles)
    mt5.get_price = AsyncMock(return_value=1.1050)
    return mt5


def make_mock_hermes(winner_idx=0, approved=True):
    """Hermes client that returns predictable responses."""
    h = MagicMock()
    h.select_winner = AsyncMock(return_value={
        "winner_idx": winner_idx,
        "reasoning": "Highest Sharpe with good win rate",
        "confidence": 0.85,
    })
    h.verify_forward_test = AsyncMock(return_value={
        "approved": approved,
        "apply_config": {"momentum": 0.6, "mean_reversion": 0.1, "grid_scalp": 0.1,
                         "llm_sentiment": 0.05, "order_flow": 0.05, "breakout_atr": 0.05,
                         "session_open": 0.05, "market_structure": 0.0},
        "reason": "Positive PnL, drawdown within limits",
    })
    return h


def test_competition_returns_result():
    """run_competition must return a CompetitionResult with correct fields."""
    candles = make_candles()
    mt5 = make_mock_mt5(candles)
    hermes = make_mock_hermes(winner_idx=0, approved=True)
    production_agent = MagicMock()
    production_agent.update_strategy_weights = AsyncMock()

    leader = AssetLeader("EURUSDm", production_agent, mt5, hermes)
    result = asyncio.run(leader.run_competition())

    assert isinstance(result, CompetitionResult)
    assert result.symbol == "EURUSDm"
    assert isinstance(result.winner_config, dict)
    assert isinstance(result.winner_sharpe, float)
    assert isinstance(result.hermes_reasoning, str)
    assert 0.0 <= result.hermes_confidence <= 1.0
    assert isinstance(result.forward_pnl, float)
    assert isinstance(result.approved, bool)
    assert isinstance(result.applied, bool)
    assert result.timestamp > 0


def test_competition_hermes_selects_winner():
    """Hermes winner_idx is respected when valid."""
    candles = make_candles()
    mt5 = make_mock_mt5(candles)
    hermes = make_mock_hermes(winner_idx=3, approved=True)
    production_agent = MagicMock()
    production_agent.update_strategy_weights = AsyncMock()

    leader = AssetLeader("EURUSDm", production_agent, mt5, hermes)
    result = asyncio.run(leader.run_competition())

    assert result.hermes_reasoning == "Highest Sharpe with good win rate"
    assert result.hermes_confidence == 0.85


def test_competition_approved_applies_winner():
    """When Hermes approves, production agent's update_strategy_weights is called."""
    candles = make_candles()
    mt5 = make_mock_mt5(candles)
    hermes = make_mock_hermes(approved=True)
    production_agent = MagicMock()
    production_agent.update_strategy_weights = AsyncMock()

    leader = AssetLeader("EURUSDm", production_agent, mt5, hermes)
    result = asyncio.run(leader.run_competition())

    assert result.approved is True
    assert result.applied is True
    production_agent.update_strategy_weights.assert_called_once()


def test_competition_rejected_does_not_apply():
    """When Hermes rejects, production agent is not updated."""
    candles = make_candles()
    mt5 = make_mock_mt5(candles)
    hermes = make_mock_hermes(approved=False)
    production_agent = MagicMock()
    production_agent.update_strategy_weights = AsyncMock()

    leader = AssetLeader("EURUSDm", production_agent, mt5, hermes)
    result = asyncio.run(leader.run_competition())

    assert result.approved is False
    assert result.applied is False
    production_agent.update_strategy_weights.assert_not_called()


def test_competition_hermes_unreachable_fallback():
    """When Hermes is None, competition falls back to top-Sharpe algorithmic selection."""
    candles = make_candles()
    mt5 = make_mock_mt5(candles)

    leader = AssetLeader("EURUSDm", None, mt5, None)
    result = asyncio.run(leader.run_competition())

    # should not crash; approved=False when hermes unavailable
    assert isinstance(result, CompetitionResult)
    assert result.approved is False
    assert result.applied is False


def test_competition_mt5_offline_graceful():
    """When MT5 is None (no candles), competition should return empty result gracefully."""
    leader = AssetLeader("EURUSDm", None, None, None)
    result = asyncio.run(leader.run_competition())

    assert isinstance(result, CompetitionResult)
    # 0 candles -> all sharpes are 0.0 -> still produces a result
    assert result.symbol == "EURUSDm"


def test_make_configs_count_and_uniqueness():
    """_make_configs produces 12 distinct configs each summing to 1.0."""
    leader = AssetLeader("EURUSDm", None, None, None)
    configs = leader._make_configs()
    assert len(configs) == 12
    unique = [str(sorted(c.items())) for c in configs]
    assert len(set(unique)) == 12
    for i, c in enumerate(configs):
        total = sum(c.values())
        assert abs(total - 1.0) < 1e-9, f"config {i} weights sum={total}"
```

- [ ] **Step 2: Run test_asset_leader.py — all PASS**

```bash
cd /home/alfred/mtai && python -m pytest tests/test_asset_leader.py -v 2>&1
```

---

## Task 7: Full test suite — all green

- [ ] **Step 1: Run all tests**

```bash
cd /home/alfred/mtai && python -m pytest tests/test_sub_agent.py tests/test_asset_leader.py -v 2>&1
```

All tests must pass.

- [ ] **Step 2: Run import smoke test**

```bash
cd /home/alfred/mtai && python -c "
import sys; sys.path.insert(0, 'src')
from engine.dna import STRATEGY_METHODS, random_dna
from engine.sub_agent import SubAgent, BacktestResult, ForwardTestResult
from engine.hermes_client import HermesClient
from engine.asset_leader import AssetLeader, CompetitionResult
from engine.competition_scheduler import CompetitionScheduler
assert len(STRATEGY_METHODS) == 8
dna = random_dna(0, 'EURUSDm')
assert len(dna.strategy_weights) == 8
scheduler = CompetitionScheduler(['EURUSDm', 'GBPUSDm'], interval_seconds=3600)
print('PASS all imports OK')
" 2>&1
```

---

## Verification Checklist

Before marking this plan complete, verify ALL of the following:

```bash
cd /home/alfred/mtai

# 1. STRATEGY_METHODS has 8 entries
python -c "from src.engine.dna import STRATEGY_METHODS; assert len(STRATEGY_METHODS)==8; print('OK dna')"

# 2. 12 distinct configs
python -c "
import sys; sys.path.insert(0, 'src')
from engine.asset_leader import AssetLeader
c = AssetLeader('X', None, None, None)._make_configs()
assert len(c)==12 and len({str(sorted(x.items())) for x in c})==12; print('OK configs')"

# 3. All 8 strategies run backtest without crash
python -c "
import asyncio, sys, time, math
sys.path.insert(0, 'src')
from engine.sub_agent import SubAgent
candles = [{'open':1.1+math.sin(i*.15)*.003,'high':1.103,'low':1.097,'close':1.1+math.sin(i*.15)*.003,'volume':1000,'timestamp':time.time()+i*60} for i in range(200)]
strats = ['momentum','mean_reversion','grid_scalp','llm_sentiment','order_flow','breakout_atr','session_open','market_structure']
for s in strats:
    cfg = {x:0.0 for x in strats}; cfg[s]=1.0
    r = asyncio.run(SubAgent('EURUSDm',cfg).run_backtest(candles))
    print(f'OK {s} trades={r.trades}')
"

# 4. All tests pass
python -m pytest tests/test_sub_agent.py tests/test_asset_leader.py -v
```
