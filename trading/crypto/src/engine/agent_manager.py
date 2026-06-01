"""
Crypto Agent Manager — coordinates the multi-agent trading loop, paper position
simulation, live execution via the ExchangeRouter, and dashboard state export.

Contract (imported by the backend run.py):
    CryptoAgentManager(router, paper_mode=True, agent_count=25, pairs=None)
    async on_tick(symbol, price, volume, timestamp) -> None
    to_state_dict() -> {"summary", "agents", "prices", "order_history"}
    add_pair(symbol) / remove_pair(symbol)
    property pairs -> list[str]

This module never writes files — run.py owns state persistence.
"""
import asyncio
import logging
import time
from typing import List, Dict, Optional

from engine.dna import create_population, random_dna, CRYPTO_SYMBOLS
from engine.agent import CryptoAgent
from engine.signals import CryptoSignalEngine
from engine.risk_guardian import CryptoRiskGuardian, RiskResult
from engine.evolution import evolve, EVOLUTION_INTERVAL

logger = logging.getLogger("agent_manager")

DEFAULT_PAIRS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]


class CryptoAgentManager:
    def __init__(self, router, paper_mode: bool = True, agent_count: int = 25, pairs: list = None):
        self.router = router
        self.paper_mode = paper_mode
        self._pairs: List[str] = list(pairs) if pairs else list(DEFAULT_PAIRS)

        self.signal_engine = CryptoSignalEngine()
        self.risk_guardian = CryptoRiskGuardian()

        dnas = create_population(agent_count, pairs=self._pairs)
        self.agents: List[CryptoAgent] = [
            CryptoAgent(dna, self.signal_engine, self.risk_guardian, paper_mode)
            for dna in dnas
        ]

        self._tick_count = 0
        self._start_time = time.time()
        self._last_evolution_time = time.time()
        self._next_agent_id = agent_count
        self._account_balance = 1000.0
        self._account_equity = 1000.0
        self._initial_capital = 1000.0
        self._latest_prices: Dict[str, dict] = {}
        self._order_history: List[dict] = []

        # exchange name for dashboard (duck-typed)
        self._exchange_name = getattr(router, "exchange_name", "binance")

    # ── public properties ───────────────────────────────
    @property
    def pairs(self) -> List[str]:
        return self._pairs

    def add_pair(self, symbol: str) -> None:
        if symbol not in self._pairs:
            self._pairs.append(symbol)
            # spawn one fresh agent for the new pair
            dna = random_dna(self._next_agent_id, symbol=symbol)
            self._next_agent_id += 1
            self.agents.append(
                CryptoAgent(dna, self.signal_engine, self.risk_guardian, self.paper_mode)
            )
            logger.info(f"Added pair {symbol}")

    def remove_pair(self, symbol: str) -> None:
        if symbol in self._pairs:
            self._pairs.remove(symbol)
            logger.info(f"Removed pair {symbol}")

    # ── tick loop ───────────────────────────────────────
    async def on_tick(self, symbol: str, price: float, volume: float, timestamp: float) -> None:
        self.signal_engine.record_tick(symbol, price, volume, timestamp)
        self._record_price(symbol, price)
        self._tick_count += 1

        if self.paper_mode:
            self._check_paper_positions(symbol, price)

        # process agent signals every 10 ticks
        if self._tick_count % 10 == 0:
            await self._process_agents(symbol, price)

        # sync live positions every 30 ticks (run.py writes state separately)
        if self._tick_count % 30 == 0 and not self.paper_mode:
            await self._sync_positions()

        # evolution cycle
        if time.time() - self._last_evolution_time >= EVOLUTION_INTERVAL:
            self._run_evolution()
            self._last_evolution_time = time.time()

    def _check_paper_positions(self, symbol: str, price: float):
        """Simulate SL/TP triggers for paper positions."""
        for agent in self.agents:
            if agent.dna.symbol != symbol or not agent.is_in_trade:
                continue
            direction = 1 if agent._open_side == "BUY" else -1
            sl_hit = tp_hit = False
            if agent._open_side == "BUY":
                sl_hit = price <= agent._open_sl
                tp_hit = price >= agent._open_tp
            else:
                sl_hit = price >= agent._open_sl
                tp_hit = price <= agent._open_tp

            if not (sl_hit or tp_hit):
                continue

            exit_price = agent._open_sl if sl_hit else agent._open_tp
            price_diff = exit_price - agent._open_entry
            sl_dist = abs(agent._open_entry - agent._open_sl)
            if sl_dist > 0:
                pnl = agent._open_risk_amount * (direction * price_diff) / sl_dist
            else:
                pnl = -agent._open_risk_amount if sl_hit else agent._open_risk_amount

            pnl_pct = (pnl / self._account_balance) * 100 if self._account_balance else 0.0
            self._account_balance += pnl
            self._account_equity = self._account_balance

            agent.record_trade_result(pnl, pnl_pct)
            self.risk_guardian.on_position_closed(pnl)
            self._order_history.insert(0, {
                "timestamp": time.time(),
                "agent": agent.dna.name,
                "symbol": symbol,
                "action": "CLOSE",
                "price": exit_price,
                "pnl": round(pnl, 2),
                "type": "paper",
                "status": "closed",
            })
            self._trim_history()
            self._reset_agent(agent)

    async def _sync_positions(self):
        """Detect externally-closed live positions and record PnL."""
        try:
            positions = await self.router.get_positions()
            active = {p.get("ticket") for p in positions}
        except Exception as e:
            logger.warning(f"position sync failed: {e}")
            return
        for agent in self.agents:
            if not agent.is_in_trade:
                continue
            if agent._open_ticket in active:
                continue
            # closed externally — record flat (PnL unknown without deal history)
            agent.record_trade_result(0.0, 0.0)
            self.risk_guardian.on_position_closed(0.0)
            self._reset_agent(agent)

    async def _process_agents(self, symbol: str, price: float):
        idle = [a for a in self.agents if a.dna.symbol == symbol and not a.is_in_trade]
        today = int(time.time() / 86400)
        for agent in idle[:3]:  # max 3 signals per symbol per pass
            signal = agent.generate_signal(price)
            if signal["action"] == "HOLD" or signal["confidence"] < 50:
                continue
            risk = self.risk_guardian.validate(
                symbol=symbol,
                action="BUY" if signal["action"] == "LONG" else "SELL",
                entry_price=price,
                sl_pct=agent.dna.sl_pct,
                tp_pct=agent.dna.tp_pct,
                account_balance=self._account_balance,
                account_equity=self._account_equity,
                current_day=today,
            )
            if not risk.allowed:
                logger.debug(f"[{agent.dna.name}] blocked: {risk.reason}")
                continue
            if self.paper_mode:
                self._paper_execute(agent, signal, price, risk)
            else:
                await self._live_execute(agent, signal, price, risk)

    def _paper_execute(self, agent: CryptoAgent, signal: dict, price: float, risk: RiskResult):
        action = "BUY" if signal["action"] == "LONG" else "SELL"
        agent._open_ticket = int(time.time() * 1000) + agent.dna.id
        agent._open_entry = price
        agent._open_side = action
        agent._open_sl = risk.sl_price
        agent._open_tp = risk.tp_price
        agent._open_qty = risk.qty
        agent._open_risk_amount = risk.risk_amount
        self.risk_guardian.on_position_opened()
        self._order_history.insert(0, {
            "timestamp": time.time(),
            "agent": agent.dna.name,
            "symbol": agent.dna.symbol,
            "action": action,
            "qty": round(risk.qty, 6),
            "price": price,
            "sl": risk.sl_price,
            "tp": risk.tp_price,
            "type": "paper",
            "status": "open",
        })
        self._trim_history()

    async def _live_execute(self, agent: CryptoAgent, signal: dict, price: float, risk: RiskResult):
        action = "BUY" if signal["action"] == "LONG" else "SELL"
        try:
            result = await self.router.place_order(
                symbol=agent.dna.symbol,
                side=action,
                qty=risk.qty,
                sl=risk.sl_price,
                tp=risk.tp_price,
                comment=f"CX-{agent.dna.name}",
            )
        except Exception as e:
            logger.error(f"[LIVE] order failed for {agent.dna.name}: {e}")
            return
        agent._open_ticket = result.get("ticket")
        agent._open_entry = result.get("price", price)
        agent._open_side = action
        agent._open_sl = risk.sl_price
        agent._open_tp = risk.tp_price
        agent._open_qty = risk.qty
        agent._open_risk_amount = risk.risk_amount
        self.risk_guardian.on_position_opened()
        self._order_history.insert(0, {
            "timestamp": time.time(),
            "agent": agent.dna.name,
            "symbol": agent.dna.symbol,
            "action": action,
            "qty": round(risk.qty, 6),
            "price": agent._open_entry,
            "sl": risk.sl_price,
            "tp": risk.tp_price,
            "type": "live",
            "status": result.get("status", "placed"),
            "ticket": agent._open_ticket,
        })
        self._trim_history()

    def _run_evolution(self):
        logger.info("[Evolution] starting cycle")
        stats = [a.to_dict() for a in self.agents]
        dnas = [a.dna for a in self.agents]
        new_dnas, self._next_agent_id = evolve(dnas, stats, self._next_agent_id, pairs=self._pairs)
        self.agents = [
            CryptoAgent(dna, self.signal_engine, self.risk_guardian, self.paper_mode)
            for dna in new_dnas
        ]
        logger.info(f"[Evolution] done — {len(self.agents)} agents")

    # ── helpers ─────────────────────────────────────────
    def _reset_agent(self, agent: CryptoAgent):
        agent._open_ticket = None
        agent._open_entry = 0.0
        agent._open_side = ""
        agent._open_sl = 0.0
        agent._open_tp = 0.0
        agent._open_qty = 0.0
        agent._open_risk_amount = 0.0

    def _trim_history(self):
        if len(self._order_history) > 500:
            self._order_history = self._order_history[:500]

    def _record_price(self, symbol: str, price: float):
        prev = self._latest_prices.get(symbol, {}).get("mid")
        change_pct = round(((price - prev) / prev) * 100, 3) if prev else 0.0
        # synthetic 2bps spread for paper/dashboard display
        spread = price * 0.0001
        self._latest_prices[symbol] = {
            "mid": round(price, 4),
            "bid": round(price - spread, 4),
            "ask": round(price + spread, 4),
            "change_pct": change_pct,
        }

    # ── state export ────────────────────────────────────
    def to_state_dict(self) -> dict:
        agent_entries = [a.to_dict() for a in self.agents]
        total_trades = sum(a.trades_count for a in self.agents)
        winners = sum(a.wins for a in self.agents)
        losers = sum(a.losses for a in self.agents)
        open_positions = sum(1 for a in self.agents if a.is_in_trade)
        total_pnl = sum(a.total_pnl for a in self.agents)
        total_pnl_pct = round((self._account_equity - self._initial_capital) / self._initial_capital * 100, 2)

        summary = {
            "total_pnl_pct": total_pnl_pct,
            "total_pnl": round(total_pnl, 2),
            "total_equity": round(self._account_equity, 2),
            "total_trades": total_trades,
            "winners": winners,
            "losers": losers,
            "uptime_seconds": round(time.time() - self._start_time, 1),
            "open_positions": open_positions,
            "exchange": self._exchange_name,
            "mode": "paper" if self.paper_mode else "live",
            "total_agents": len(self.agents),
            "pairs": list(self._pairs),
        }

        return {
            "summary": summary,
            "agents": agent_entries,
            "prices": self._latest_prices,
            "order_history": self._order_history[:200],
        }
