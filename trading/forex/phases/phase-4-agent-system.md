# Phase 4: Multi-Agent Evolution System

> **Objective:** 25 agents วิ่งพร้อมกัน evolve forex strategy ที่ดีที่สุด  
> **Source:** ported จาก `ai-trading-live/engine/agent.py` + `evolution.py`  
> **Scale:** ลดจาก 100 → 25 agents (forex position limit + margin constraint)

---

## Agent Architecture (Forex)

```
25 Agents × 8 symbols = 200 potential signals/tick
         ↓ Risk Guardian filter
    max 3 concurrent open positions (total)
         ↓ MT5 Executor
    Real/Paper trades on Exness
```

### Forex Agent DNA

```python
@dataclass
class ForexAgentDNA:
    id: int
    symbol: str              # เพิ่ม: agent เชี่ยวชาญ symbol เดียว
    strategy_weights: dict   # เหมือนเดิม
    sl_pips: float           # เปลี่ยน: forex-specific
    tp_pips: float           # เปลี่ยน: forex-specific
    risk_pct: float          # 0.005-0.015
    timeframe: str           # "M15" | "H1" | "H4"
    session_bias: str        # "LONDON" | "NY" | "ASIA" | "ALL"
```

**Key difference จาก crypto:** แต่ละ agent specialise ใน **symbol เดียว** (ไม่ใช่ trade ทุก symbol)

---

## Task 4.1: Forex Agent DNA

**Files:**
- Create: `src/engine/dna.py`

```python
"""
Forex Agent DNA
ดัดแปลงจาก ai-trading-live/engine/dna.py

เพิ่ม:
- symbol specialization
- forex-specific parameters (sl_pips, tp_pips, timeframe, session_bias)
"""
import random
from dataclasses import dataclass, field
from typing import Dict

FOREX_SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD"]
TIMEFRAMES = ["M15", "H1", "H4"]
SESSIONS = ["LONDON", "NY", "ASIA", "ALL"]

STRATEGY_METHODS = ["momentum", "mean_reversion", "grid_scalp", "llm_sentiment"]

# Symbol-specific defaults (from backtests)
SYMBOL_DEFAULTS = {
    "EURUSD": {"sl_range": (10, 25), "tp_mult": (1.5, 3.0), "tf_bias": "M15"},
    "GBPUSD": {"sl_range": (15, 30), "tp_mult": (1.5, 2.5), "tf_bias": "M15"},
    "USDJPY": {"sl_range": (10, 20), "tp_mult": (1.5, 3.0), "tf_bias": "H1"},
    "XAUUSD": {"sl_range": (100, 250), "tp_mult": (1.5, 3.0), "tf_bias": "H1"},
    "AUDUSD": {"sl_range": (10, 20), "tp_mult": (1.5, 2.5), "tf_bias": "H1"},
    "USDCAD": {"sl_range": (10, 20), "tp_mult": (1.5, 2.5), "tf_bias": "H1"},
    "USDCHF": {"sl_range": (10, 20), "tp_mult": (1.5, 2.5), "tf_bias": "H1"},
    "NZDUSD": {"sl_range": (10, 20), "tp_mult": (1.5, 2.5), "tf_bias": "H4"},
}

@dataclass
class ForexAgentDNA:
    id: int
    name: str
    symbol: str
    strategy_weights: Dict[str, float] = field(default_factory=dict)
    sl_pips: float = 15.0
    tp_pips: float = 30.0
    risk_pct: float = 0.01
    timeframe: str = "M15"
    session_bias: str = "ALL"
    regime_bias: str = "any"   # "bull"|"bear"|"range"|"any"

def random_dna(agent_id: int, symbol: str = None, regime: str = "MIXED") -> ForexAgentDNA:
    """Generate random DNA สำหรับ agent"""
    if symbol is None:
        symbol = random.choice(FOREX_SYMBOLS)

    defaults = SYMBOL_DEFAULTS.get(symbol, SYMBOL_DEFAULTS["EURUSD"])
    sl_min, sl_max = defaults["sl_range"]
    tp_mult_min, tp_mult_max = defaults["tp_mult"]

    sl_pips = random.uniform(sl_min, sl_max)
    tp_pips = sl_pips * random.uniform(tp_mult_min, tp_mult_max)

    # Strategy weights (sum = 1.0)
    weights = {m: random.random() for m in STRATEGY_METHODS}
    total = sum(weights.values())
    weights = {k: v / total for k, v in weights.items()}

    # Regime-aware bias
    regime_map = {
        "TRENDING": "bull",
        "SIDEWAYS": "range",
        "HIGH_VOL": "range",
        "BEARISH": "bear",
        "BULLISH": "bull",
    }
    regime_bias = regime_map.get(regime, random.choice(["bull", "bear", "range", "any"]))

    return ForexAgentDNA(
        id=agent_id,
        name=f"FX-{symbol[:3]}-{agent_id:03d}",
        symbol=symbol,
        strategy_weights=weights,
        sl_pips=round(sl_pips, 1),
        tp_pips=round(tp_pips, 1),
        risk_pct=round(random.uniform(0.005, 0.012), 3),
        timeframe=random.choice(TIMEFRAMES),
        session_bias=random.choice(SESSIONS),
        regime_bias=regime_bias,
    )

def create_population(count: int = 25) -> list:
    """สร้าง initial population — distribute agents across symbols"""
    agents = []
    symbols_cycle = FOREX_SYMBOLS * (count // len(FOREX_SYMBOLS) + 1)
    for i in range(count):
        symbol = symbols_cycle[i]
        dna = random_dna(agent_id=i, symbol=symbol)
        agents.append(dna)
    return agents
```

---

## Task 4.2: Forex Agent

**Files:**
- Create: `src/engine/agent.py`

```python
"""
Forex Trading Agent
ดัดแปลงจาก ai-trading-live/engine/agent.py

เปลี่ยน:
1. ใช้ ForexAgentDNA (มี symbol, sl_pips, tp_pips)
2. Execute ผ่าน MT5Client แทน PaperTradeEngine
3. Position sizing ผ่าน ForexRiskGuardian
4. Paper mode = simulate (ไม่ส่ง order จริง)
"""
import logging
import random
import time
from typing import Optional

from engine.dna import ForexAgentDNA
from engine.signals import ForexSignalEngine
from engine.risk_guardian import ForexRiskGuardian, RiskResult

logger = logging.getLogger("agent")

class ForexAgent:
    def __init__(
        self,
        dna: ForexAgentDNA,
        signal_engine: ForexSignalEngine,
        risk_guardian: ForexRiskGuardian,
        paper_mode: bool = True,
    ):
        self.dna = dna
        self.signal_engine = signal_engine
        self.risk_guardian = risk_guardian
        self.paper_mode = paper_mode

        # Performance tracking
        self.trades_count = 0
        self.wins = 0
        self.losses = 0
        self.total_pnl = 0.0
        self.total_pnl_pct = 0.0

        # State
        self._open_ticket: Optional[int] = None  # MT5 ticket id
        self._open_entry: float = 0.0
        self._open_side: str = ""
        self._consecutive_losses = 0

    @property
    def win_rate(self) -> float:
        if self.trades_count == 0:
            return 0.0
        return self.wins / self.trades_count

    @property
    def is_in_trade(self) -> bool:
        return self._open_ticket is not None

    def generate_signal(self, price: float) -> dict:
        """Generate signal สำหรับ symbol ของ agent นี้"""
        symbol = self.dna.symbol

        # Dominant strategy
        dominant = max(self.dna.strategy_weights, key=lambda k: self.dna.strategy_weights[k])

        if dominant == "momentum":
            return self.signal_engine.technical_signal(symbol)
        elif dominant == "mean_reversion":
            # Invert momentum signal for mean reversion
            tech = self.signal_engine.technical_signal(symbol)
            if tech["action"] == "LONG":
                tech["action"] = "SHORT"
                tech["reason"] = "MR: " + tech["reason"]
            elif tech["action"] == "SHORT":
                tech["action"] = "LONG"
                tech["reason"] = "MR: " + tech["reason"]
            return tech
        elif dominant == "grid_scalp":
            return self._grid_signal(symbol, price)
        else:
            return self.signal_engine.technical_signal(symbol)

    def _grid_signal(self, symbol: str, price: float) -> dict:
        hist = self.signal_engine.get_history(symbol)
        sma20 = hist.sma(20)
        if not sma20:
            return {"action": "HOLD", "confidence": 0, "reason": "Grid: no SMA20"}
        vwap_dev = hist.vwap_deviation()
        deviation = vwap_dev if vwap_dev is not None else ((price - sma20) / sma20) * 100
        spacing = 0.08  # 0.08% threshold
        if deviation > spacing:
            return {"action": "SHORT", "confidence": 55, "reason": f"Grid: {deviation:.2f}% above mean"}
        elif deviation < -spacing:
            return {"action": "LONG", "confidence": 55, "reason": f"Grid: {abs(deviation):.2f}% below mean"}
        return {"action": "HOLD", "confidence": 25, "reason": f"Grid: {deviation:+.2f}%"}

    def record_trade_result(self, pnl: float, pnl_pct: float):
        """เรียกเมื่อ trade ปิด"""
        self.trades_count += 1
        self.total_pnl += pnl
        self.total_pnl_pct += pnl_pct
        if pnl > 0:
            self.wins += 1
            self._consecutive_losses = 0
        else:
            self.losses += 1
            self._consecutive_losses += 1

    def to_dict(self) -> dict:
        return {
            "id": self.dna.id,
            "name": self.dna.name,
            "symbol": self.dna.symbol,
            "strategy": max(self.dna.strategy_weights, key=lambda k: self.dna.strategy_weights[k]),
            "trades": self.trades_count,
            "win_rate": round(self.win_rate * 100, 1),
            "total_pnl": round(self.total_pnl, 2),
            "total_pnl_pct": round(self.total_pnl_pct, 2),
            "consecutive_losses": self._consecutive_losses,
            "in_trade": self.is_in_trade,
            "timeframe": self.dna.timeframe,
            "sl_pips": self.dna.sl_pips,
            "tp_pips": self.dna.tp_pips,
        }
```

---

## Task 4.3: Evolution Engine

**Files:**
- Create: `src/engine/evolution.py`

```python
"""
Evolution Engine สำหรับ Forex
ดัดแปลงจาก ai-trading-live/engine/evolution.py

Logic เหมือนเดิม:
- Fitness = 50% PnL + 30% WinRate + 20% Diversity
- Top 20% elite survive
- 30% mutations + 20% crossovers + 50% fresh blood
- Evolution cycle ทุก 3600s (1 hour)
- Warm-up: ต้องมี ≥ 30 trades ก่อน eligible

Forex-specific:
- Preserve symbol diversity (ต้องมี agent ทุก symbol)
- Session-aware mutations (ถ้า agent ชนะใน London → spawn London agents มากขึ้น)
"""
import copy
import random
import statistics
import time
from typing import List

from engine.dna import ForexAgentDNA, FOREX_SYMBOLS, random_dna

MIN_TRADES_BEFORE_JUDGMENT = 30  # forex trades น้อยกว่า crypto
EVOLUTION_INTERVAL = 3600        # 1 hour

def fitness_score(agent_dict: dict, pop_strategy_avg: dict) -> float:
    """คำนวณ fitness score (เหมือน ai-trading-live)"""
    pnl = max(agent_dict.get("total_pnl_pct", 0), -50)
    wr = agent_dict.get("win_rate", 0) / 100.0
    pnl_score = min(max((pnl + 50) / 100.0, 0), 1.0)

    # Diversity bonus
    weights = agent_dict.get("strategy_weights", {})
    diversity_sum = sum(abs(weights.get(k, 0) - pop_strategy_avg.get(k, 0)) for k in pop_strategy_avg)
    diversity_bonus = min(diversity_sum / max(len(pop_strategy_avg), 1) * 5, 1.0)

    return 0.5 * pnl_score + 0.3 * wr + 0.2 * diversity_bonus

def evolve(agents: List[ForexAgentDNA], agent_stats: List[dict], next_id_start: int) -> tuple:
    """
    Run one evolution cycle.
    Returns: (new_population, next_id)
    """
    if len(agents) < 5:
        return agents, next_id_start

    # Split: protected (< MIN_TRADES) vs ranked
    stats_map = {s["id"]: s for s in agent_stats}
    protected = [a for a in agents if stats_map.get(a.id, {}).get("trades", 0) < MIN_TRADES_BEFORE_JUDGMENT]
    ranked_pool = [a for a in agents if stats_map.get(a.id, {}).get("trades", 0) >= MIN_TRADES_BEFORE_JUDGMENT]

    if not ranked_pool:
        return agents, next_id_start

    # Calculate population strategy average
    all_weights = [a.strategy_weights for a in ranked_pool]
    strategies = list(all_weights[0].keys()) if all_weights else []
    pop_avg = {s: sum(w.get(s, 0) for w in all_weights) / len(all_weights) for s in strategies}

    # Score + rank
    scored = [(a, fitness_score(stats_map.get(a.id, {}), pop_avg)) for a in ranked_pool]
    scored.sort(key=lambda x: x[1], reverse=True)

    # Elite (top 20%)
    elite_count = max(1, len(scored) // 5)
    elite = [a for a, _ in scored[:elite_count]]

    next_id = next_id_start
    next_gen = []

    # Keep protected
    for a in protected:
        next_gen.append(a)

    # Keep elite (reassign IDs to avoid duplicates)
    for e in elite:
        new = copy.deepcopy(e)
        new.id = next_id
        new.name = f"FX-{new.symbol[:3]}-{next_id:03d}"
        next_id += 1
        next_gen.append(new)

    # Ensure symbol coverage — must have at least 1 agent per symbol
    covered_symbols = {a.symbol for a in next_gen}
    for sym in FOREX_SYMBOLS:
        if sym not in covered_symbols:
            fresh = random_dna(agent_id=next_id, symbol=sym)
            next_id += 1
            next_gen.append(fresh)
            covered_symbols.add(sym)

    # Fill remaining with mutations + crossovers + fresh blood
    target_count = len(agents)
    while len(next_gen) < target_count:
        roll = random.random()
        if roll < 0.3 and elite:
            # Mutation
            parent = random.choice(elite)
            child = copy.deepcopy(parent)
            child.id = next_id
            child.name = f"FX-{child.symbol[:3]}-{next_id:03d}"
            # Mutate weights
            for k in child.strategy_weights:
                child.strategy_weights[k] *= random.uniform(0.7, 1.3)
            total = sum(child.strategy_weights.values())
            child.strategy_weights = {k: v/total for k, v in child.strategy_weights.items()}
            # Mutate pips
            child.sl_pips = max(5, child.sl_pips * random.uniform(0.8, 1.2))
            child.tp_pips = max(child.sl_pips * 1.5, child.tp_pips * random.uniform(0.8, 1.2))
            next_id += 1
            next_gen.append(child)
        elif roll < 0.5 and len(elite) >= 2:
            # Crossover
            p1, p2 = random.sample(elite, 2)
            child_dna = random_dna(next_id, symbol=p1.symbol)
            # Blend weights
            for k in STRATEGY_METHODS if hasattr(child_dna, 'strategy_weights') else []:
                w1 = p1.strategy_weights.get(k, 0)
                w2 = p2.strategy_weights.get(k, 0)
                child_dna.strategy_weights[k] = (w1 + w2) / 2
            next_id += 1
            next_gen.append(child_dna)
        else:
            # Fresh blood
            sym = random.choice(FOREX_SYMBOLS)
            fresh = random_dna(next_id, symbol=sym)
            next_id += 1
            next_gen.append(fresh)

    return next_gen[:target_count], next_id
```

---

## Task 4.4: Agent Manager (main loop)

**Files:**
- Create: `src/engine/agent_manager.py`

```python
"""
Agent Manager — main trading loop
ดัดแปลงจาก ai-trading-live/engine/agent_manager.py

Loop:
1. Receive tick from MT5Feed
2. Record to signal engine  
3. Every N ticks → generate signals for each agent
4. Validate via RiskGuardian
5. Execute (paper or live) via MT5Client
6. Track PnL
7. Every 3600s → evolve population
"""
import asyncio
import json
import logging
import time
from pathlib import Path
from typing import List, Dict

from engine.dna import create_population
from engine.agent import ForexAgent
from engine.signals import ForexSignalEngine
from engine.risk_guardian import ForexRiskGuardian
from engine.evolution import evolve, EVOLUTION_INTERVAL
from mt5_bridge.client import MT5Client

logger = logging.getLogger("agent_manager")

STATE_FILE = Path("dashboard/live_state.json")

class ForexAgentManager:
    def __init__(self, mt5_client: MT5Client, paper_mode: bool = True, agent_count: int = 25):
        self.mt5 = mt5_client
        self.paper_mode = paper_mode

        self.signal_engine = ForexSignalEngine()
        self.risk_guardian = ForexRiskGuardian()

        dnas = create_population(agent_count)
        self.agents: List[ForexAgent] = [
            ForexAgent(dna, self.signal_engine, self.risk_guardian, paper_mode)
            for dna in dnas
        ]

        self._tick_count = 0
        self._last_evolution_time = time.time()
        self._next_agent_id = agent_count
        self._account_balance = 1000.0
        self._account_equity = 1000.0

    async def on_tick(self, tick: dict):
        """รับ tick จาก MT5Feed"""
        symbol = tick["symbol"]
        price = tick["price"]
        volume = tick.get("volume", 1.0)
        ts = tick.get("timestamp", time.time())

        self.signal_engine.record_tick(symbol, price, volume, ts)
        self._tick_count += 1

        # Process signals every 10 ticks per symbol
        if self._tick_count % 10 == 0:
            await self._process_agents(symbol, price)

        # Update account info every 60 ticks
        if self._tick_count % 60 == 0:
            await self._update_account()

        # Evolution every 3600s
        if time.time() - self._last_evolution_time >= EVOLUTION_INTERVAL:
            self._run_evolution()
            self._last_evolution_time = time.time()

        # Write dashboard state every 30 ticks
        if self._tick_count % 30 == 0:
            self._write_state()

    async def _process_agents(self, symbol: str, price: float):
        """Process agents ที่ trade symbol นี้"""
        agents_for_symbol = [a for a in self.agents if a.dna.symbol == symbol and not a.is_in_trade]

        for agent in agents_for_symbol[:3]:  # max 3 signals per symbol per tick
            signal = agent.generate_signal(price)
            if signal["action"] == "HOLD" or signal["confidence"] < 50:
                continue

            # Risk validation
            today = int(time.time() / 86400)
            risk_result = self.risk_guardian.validate(
                symbol=symbol,
                action="BUY" if signal["action"] == "LONG" else "SELL",
                entry_price=price,
                sl_pips=agent.dna.sl_pips,
                tp_pips=agent.dna.tp_pips,
                account_balance=self._account_balance,
                account_equity=self._account_equity,
                current_day=today,
            )

            if not risk_result.allowed:
                logger.debug(f"[{agent.dna.name}] blocked: {risk_result.reason}")
                continue

            # Execute
            if self.paper_mode:
                await self._paper_execute(agent, signal, price, risk_result)
            else:
                await self._live_execute(agent, signal, price, risk_result)

    async def _paper_execute(self, agent: ForexAgent, signal: dict, price: float, risk: "RiskResult"):
        """Simulate trade execution"""
        action = "BUY" if signal["action"] == "LONG" else "SELL"
        logger.info(
            f"[PAPER] {agent.dna.name} {action} {agent.dna.symbol} "
            f"lot={risk.lot_size} SL={risk.sl_price:.5f} TP={risk.tp_price:.5f}"
        )
        agent._open_ticket = int(time.time())  # fake ticket
        agent._open_entry = price
        agent._open_side = action
        self.risk_guardian.on_position_opened()

    async def _live_execute(self, agent: ForexAgent, signal: dict, price: float, risk: "RiskResult"):
        """Live execution via MT5"""
        action = "BUY" if signal["action"] == "LONG" else "SELL"
        try:
            result = await self.mt5.place_order(
                symbol=agent.dna.symbol,
                action=action,
                volume=risk.lot_size,
                sl=risk.sl_price,
                tp=risk.tp_price,
                comment=f"MTAI-{agent.dna.name}",
            )
            agent._open_ticket = result["order_id"]
            agent._open_entry = result["price"]
            agent._open_side = action
            self.risk_guardian.on_position_opened()
            logger.info(f"[LIVE] {agent.dna.name} order placed: {result}")
        except Exception as e:
            logger.error(f"[LIVE] Order failed for {agent.dna.name}: {e}")

    async def _update_account(self):
        try:
            account = await self.mt5.get_account()
            self._account_balance = account["balance"]
            self._account_equity = account["equity"]
        except Exception as e:
            logger.warning(f"Account update failed: {e}")

    def _run_evolution(self):
        logger.info("[Evolution] Starting evolution cycle...")
        agent_stats = [a.to_dict() for a in self.agents]
        dnas = [a.dna for a in self.agents]
        new_dnas, self._next_agent_id = evolve(dnas, agent_stats, self._next_agent_id)
        self.agents = [
            ForexAgent(dna, self.signal_engine, self.risk_guardian, self.paper_mode)
            for dna in new_dnas
        ]
        logger.info(f"[Evolution] Done — {len(self.agents)} agents")

    def _write_state(self):
        state = {
            "timestamp": time.time(),
            "paper_mode": self.paper_mode,
            "account": {
                "balance": self._account_balance,
                "equity": self._account_equity,
            },
            "agents": [a.to_dict() for a in self.agents],
            "summary": {
                "total_agents": len(self.agents),
                "active_agents": sum(1 for a in self.agents if a.is_in_trade),
                "total_pnl": sum(a.total_pnl for a in self.agents),
                "avg_win_rate": sum(a.win_rate for a in self.agents) / len(self.agents) * 100,
            }
        }
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, indent=2))
```

---

## Phase 4 Checklist

- [ ] `create_population(25)` สร้าง agents กระจาย 8 symbols
- [ ] `generate_signal()` return valid dict ทุก strategy
- [ ] Evolution ไม่สร้าง duplicate IDs
- [ ] Symbol coverage preserved หลัง evolution (ทุก symbol มี agent)
- [ ] Paper mode simulate ได้ไม่ error
- [ ] `_write_state()` เขียน `live_state.json` ได้

---

## Pitfalls

1. **25 agents ≠ 25 open positions** — Risk Guardian จำกัด 3 concurrent → agents ส่วนใหญ่จะ HOLD
2. **Symbol specialization ≠ no diversity** — evolution ต้อง preserve ≥1 agent ต่อ symbol ไม่งั้น symbols บางตัวไม่มีใน cover
3. **Forex trades น้อยกว่า crypto** — forex 1 trade/hr vs crypto 10 trades/hr → warm-up 30 trades ใช้เวลา 30+ ชม → evolution ช้ากว่า
4. **Paper mode ticket = fake int** — ต้อง check `is_in_trade` ด้วย `_open_ticket is not None` ไม่ใช่ ticket value
