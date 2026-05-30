"""
Agent Manager — coordinates the multi-agent trading loop, paper position simulation,
live position syncing, and dashboard state management.
"""
import asyncio
import json
import logging
import time
from pathlib import Path
from typing import List, Dict, Optional

from engine.dna import create_population
from engine.agent import ForexAgent
from engine.signals import ForexSignalEngine
from engine.risk_guardian import ForexRiskGuardian, RiskResult
from engine.evolution import evolve, EVOLUTION_INTERVAL
from mt5_bridge.client import MT5Client
from engine.competition_scheduler import CompetitionScheduler
from engine.asset_leader import AssetLeader
from engine.hermes_client import HermesClient, HermesError

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
        self._initial_capital = 1000.0
        self._latest_prices = {}
        self._equity_curve = []
        self._daily_pnl = {}
        self._order_history = []
        # initialize history DB
        try:
            from storage.history_db import init_db, query_orders
            init_db()
            # preload recent items from DB into memory
            try:
                recent = query_orders(offset=0, limit=200)
                for it in recent.get("items", []):
                    self._order_history.append(it)
            except Exception:
                pass
        except Exception:
            pass
        # If running live, attempt to preload recent MT5 deal history
        if not self.paper_mode:
            try:
                # schedule background load of recent history
                import asyncio
                asyncio.get_event_loop().create_task(self._load_recent_history())
            except Exception:
                pass

        # Competition scheduler & Hermes client (for sub-agent competitions)
        symbols = list({dna.symbol for dna in dnas}) if dnas else []
        try:
            self.competition_scheduler = CompetitionScheduler(symbols, interval_seconds=3600)
        except Exception:
            self.competition_scheduler = None

        try:
            self.hermes_client = HermesClient()
        except Exception:
            self.hermes_client = None

    async def _load_recent_history(self, hours: int = 24, limit: int = 200):
        """Loads recent deals from MT5 bridge and adds them to the order history."""
        try:
            deals = await self.mt5.get_recent_deals(hours=hours, limit=limit)
            for d in deals:
                entry = {
                    "timestamp": d.get("time", int(time.time())),
                    "agent": d.get("comment", "MT5"),
                    "symbol": d.get("symbol"),
                    "ticket": d.get("ticket"),
                    "volume": d.get("volume"),
                    "price": d.get("price"),
                    "pnl": d.get("profit"),
                    "type": "live",
                    "status": "closed" if not d.get("entry", True) else "placed",
                }
                # insert newest first
                self._order_history.insert(0, entry)
                if len(self._order_history) > 500:
                    self._order_history.pop()
                # persist to DB
                try:
                    from storage.history_db import insert_order
                    insert_order(entry)
                except Exception:
                    pass
            # write initial state so UI can show history immediately
            try:
                self._write_state()
            except Exception:
                pass
        except Exception as e:
            logger.warning(f"Failed to load recent MT5 history: {e}")

    async def on_tick(self, tick: dict):
        """Processes incoming tick data."""
        symbol = tick["symbol"]
        price = tick["price"]
        volume = tick.get("volume", 1.0)
        ts = tick.get("timestamp", time.time())

        # Update signal engine history
        self.signal_engine.record_tick(symbol, price, volume, ts)
        self._record_price(symbol, price)
        self._append_equity_point(ts)
        self._tick_count += 1

        # Check paper positions if paper mode is active
        if self.paper_mode:
            await self._check_paper_positions(symbol, price)

        # Process agent signals every 10 ticks per symbol
        if self._tick_count % 10 == 0:
            await self._process_agents(symbol, price)

        # Sync live positions from MT5 every 30 ticks
        if self._tick_count % 30 == 0:
            if not self.paper_mode:
                await self._sync_positions()
            self._write_state()

        # Update account balance and equity info every 60 ticks
        if self._tick_count % 60 == 0:
            await self._update_account()

        # Run evolution cycle if interval is reached
        if time.time() - self._last_evolution_time >= EVOLUTION_INTERVAL:
            self._run_evolution()
            self._last_evolution_time = time.time()

        # Competition scheduler: run per-symbol competition in background when due
        try:
            if getattr(self, "competition_scheduler", None) and self.competition_scheduler.tick(symbol):
                # find a production agent for this symbol (pick first matching)
                prod = next((a for a in self.agents if a.dna.symbol == symbol), None)
                asyncio.get_event_loop().create_task(self._run_competition_bg(symbol, prod))
        except Exception:
            logger.exception("Competition scheduling failed")

    async def _run_competition_bg(self, symbol: str, production_agent: Optional[ForexAgent]):
        try:
            leader = AssetLeader(symbol, production_agent, self.mt5, self.hermes_client)
            result = await leader.run_competition()
        except HermesError as e:
            logger.warning(f"Hermes error during competition for {symbol}: {e}")
            return
        except Exception as e:
            logger.exception(f"Competition failed for {symbol}: {e}")
            return

        # write result into live_state summary for dashboard
        try:
            # load current state if exists
            state = {}
            if STATE_FILE.exists():
                try:
                    state = json.loads(STATE_FILE.read_text())
                except Exception:
                    state = {}
            state.setdefault("summary", {})["last_competition"] = {
                "symbol": result.symbol,
                "winner_sharpe": result.winner_sharpe,
                "approved": result.approved,
                "applied": result.applied,
                "forward_pnl": result.forward_pnl,
                "timestamp": result.timestamp,
            }
            STATE_FILE.write_text(json.dumps(state))
        except Exception:
            logger.exception("Failed to write competition result to live state")

    async def _check_paper_positions(self, symbol: str, price: float):
        """Simulates SL/TP trigger evaluations for paper trading positions."""
        for agent in self.agents:
            if agent.dna.symbol == symbol and agent.is_in_trade:
                direction = 1 if agent._open_side == "BUY" else -1
                sl_hit = False
                tp_hit = False

                if agent._open_side == "BUY":
                    if price <= agent._open_sl:
                        sl_hit = True
                    elif price >= agent._open_tp:
                        tp_hit = True
                else:  # SELL
                    if price >= agent._open_sl:
                        sl_hit = True
                    elif price <= agent._open_tp:
                        tp_hit = True

                if sl_hit or tp_hit:
                    # Close trade
                    exit_price = agent._open_sl if sl_hit else agent._open_tp
                    price_diff = exit_price - agent._open_entry
                    sl_dist = abs(agent._open_entry - agent._open_sl)

                    if sl_dist > 0:
                        pnl = agent._open_risk_amount * (direction * price_diff) / sl_dist
                    else:
                        pnl = -agent._open_risk_amount if sl_hit else agent._open_risk_amount

                    pnl_pct = (pnl / self._account_balance) * 100

                    # Adjust account balance for paper mode PnL tracking
                    self._account_balance += pnl
                    self._account_equity = self._account_balance
                    self._record_trade_pnl(time.time(), pnl)

                    agent.record_trade_result(pnl, pnl_pct)
                    self.risk_guardian.on_position_closed(pnl)

                    logger.info(
                        f"[PAPER CLOSE] {agent.dna.name} closed trade on {symbol}. "
                        f"Entry={agent._open_entry:.5f}, Exit={exit_price:.5f}, "
                        f"PnL=${pnl:.2f} ({pnl_pct:+.2f}%)"
                    )

                    # Reset agent state
                    agent._open_ticket = None
                    agent._open_entry = 0.0
                    agent._open_side = ""
                    agent._open_sl = 0.0
                    agent._open_tp = 0.0
                    agent._open_risk_amount = 0.0

    async def _sync_positions(self):
        """Syncs active live positions on MT5 to update agent states."""
        try:
            positions = await self.mt5.get_positions()
            active_tickets = {pos["ticket"] for pos in positions}
        except Exception as e:
            logger.warning(f"Failed to fetch active positions for sync: {e}")
            return

        for agent in self.agents:
            if not agent.is_in_trade:
                continue
            ticket = agent._open_ticket
            if ticket in active_tickets:
                continue

            # Position appears to be closed — fetch deal history for PnL
            try:
                history = await self.mt5.get_deal_history(ticket)
            except Exception as e:
                logger.warning(f"Failed to get deal history for ticket {ticket}: {e}. Closing with 0 PnL.")
                pnl = 0.0
                pnl_pct = 0.0
                agent.record_trade_result(pnl, pnl_pct)
                self.risk_guardian.on_position_closed(pnl)
            else:
                pnl = history.get("pnl", 0.0)
                pnl_pct = (pnl / self._account_balance) * 100 if self._account_balance else 0.0
                agent.record_trade_result(pnl, pnl_pct)
                self.risk_guardian.on_position_closed(pnl)
                logger.info(
                    f"[LIVE CLOSE] {agent.dna.name} closed trade on {agent.dna.symbol} (ticket {ticket}). "
                    f"PnL=${pnl:.2f} ({pnl_pct:+.2f}%)"
                )
                # record closure in order history
                try:
                    closed_entry = {
                        "timestamp": time.time(),
                        "agent": agent.dna.name,
                        "symbol": agent.dna.symbol,
                        "ticket": ticket,
                        "pnl": pnl,
                        "type": "closed",
                    }
                    self._order_history.insert(0, closed_entry)
                    if len(self._order_history) > 500:
                        self._order_history.pop()
                    try:
                        from storage.history_db import insert_order
                        insert_order(closed_entry)
                    except Exception:
                        pass
                except Exception:
                    pass

            # record PnL into daily/equity tracking
            try:
                self._record_trade_pnl(time.time(), pnl)
            except Exception:
                pass

            # Reset agent state
            agent._open_ticket = None
            agent._open_entry = 0.0
            agent._open_side = ""
            agent._open_sl = 0.0
            agent._open_tp = 0.0
            agent._open_risk_amount = 0.0

    async def _process_agents(self, symbol: str, price: float):
        """Evaluates entry signals and executes trades for idle agents assigned to a symbol."""
        agents_for_symbol = [a for a in self.agents if a.dna.symbol == symbol and not a.is_in_trade]

        for agent in agents_for_symbol[:3]:  # max 3 signals per symbol per tick
            signal = agent.generate_signal(price)
            if signal["action"] == "HOLD" or signal["confidence"] < 50:
                continue

            # Risk validation
            today = int(time.time() / 86400)
            
            # Simple mock lookup to pass to dynamic risk / lot sizing without server dependency in tests
            async def get_price_func(sym):
                return price

            risk_result = self.risk_guardian.validate(
                symbol=symbol,
                action="BUY" if signal["action"] == "LONG" else "SELL",
                entry_price=price,
                sl_pips=agent.dna.sl_pips,
                tp_pips=agent.dna.tp_pips,
                account_balance=self._account_balance,
                account_equity=self._account_equity,
                current_day=today,
                get_price_func=get_price_func
            )

            if not risk_result.allowed:
                logger.debug(f"[{agent.dna.name}] blocked: {risk_result.reason}")
                continue

            # Execute
            if self.paper_mode:
                await self._paper_execute(agent, signal, price, risk_result)
            else:
                await self._live_execute(agent, signal, price, risk_result)

    async def _paper_execute(self, agent: ForexAgent, signal: dict, price: float, risk: RiskResult):
        """Simulates order execution for paper mode."""
        action = "BUY" if signal["action"] == "LONG" else "SELL"
        logger.info(
            f"[PAPER] {agent.dna.name} {action} {agent.dna.symbol} "
            f"lot={risk.lot_size} SL={risk.sl_price:.5f} TP={risk.tp_price:.5f}"
        )
        agent._open_ticket = int(time.time() * 1000)  # unique fake ticket
        agent._open_entry = price
        agent._open_side = action
        agent._open_sl = risk.sl_price
        agent._open_tp = risk.tp_price
        agent._open_risk_amount = risk.risk_amount
        self.risk_guardian.on_position_opened()
        # Record order in history (paper)
        try:
            order = {
                "timestamp": time.time(),
                "agent": agent.dna.name,
                "symbol": agent.dna.symbol,
                "action": action,
                "volume": risk.lot_size,
                "price": agent._open_entry,
                "sl": agent._open_sl,
                "tp": agent._open_tp,
                "type": "paper",
                "status": "open",
            }
            self._order_history.insert(0, order)
            if len(self._order_history) > 500:
                self._order_history.pop()
            # persist to DB
            try:
                from storage.history_db import insert_order
                insert_order(order)
            except Exception:
                pass
        except Exception:
            pass

    async def _live_execute(self, agent: ForexAgent, signal: dict, price: float, risk: RiskResult):
        """Sends order execution request to MT5."""
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
            agent._open_sl = risk.sl_price
            agent._open_tp = risk.tp_price
            agent._open_risk_amount = risk.risk_amount
            self.risk_guardian.on_position_opened()
            logger.info(f"[LIVE] {agent.dna.name} order placed: {result}")
            # Record order in history (live)
            try:
                ticket = result.get("order_id") or result.get("ticket")
                order = {
                    "timestamp": time.time(),
                    "agent": agent.dna.name,
                    "symbol": agent.dna.symbol,
                    "action": action,
                    "volume": risk.lot_size,
                    "price": agent._open_entry,
                    "sl": agent._open_sl,
                    "tp": agent._open_tp,
                    "type": "live",
                    "status": "placed",
                    "ticket": ticket,
                }
                self._order_history.insert(0, order)
                if len(self._order_history) > 500:
                    self._order_history.pop()
                # persist to DB
                try:
                    from storage.history_db import insert_order
                    insert_order(order)
                except Exception:
                    pass
            except Exception:
                pass
        except Exception as e:
            logger.error(f"[LIVE] Order failed for {agent.dna.name}: {e}")

    async def _update_account(self):
        """Refreshes account balance and equity details from MT5."""
        if self.paper_mode:
            return
        try:
            account = await self.mt5.get_account()
            self._account_balance = account["balance"]
            self._account_equity = account["equity"]
        except Exception as e:
            logger.warning(f"Account update failed: {e}")

    def _run_evolution(self):
        """Runs the evolution algorithm to mutate/recombine DNA parameters."""
        logger.info("[Evolution] Starting evolution cycle...")
        agent_stats = [a.to_dict() for a in self.agents]
        dnas = [a.dna for a in self.agents]
        new_dnas, self._next_agent_id = evolve(dnas, agent_stats, self._next_agent_id)
        self.agents = [
            ForexAgent(dna, self.signal_engine, self.risk_guardian, self.paper_mode)
            for dna in new_dnas
        ]
        logger.info(f"[Evolution] Done — evolved {len(self.agents)} agents")

    def _write_state(self):
        """Writes current agent system state to JSON for dashboard visualization."""
        agent_entries = [a.to_dict() for a in self.agents]
        by_strategy = {}
        for agent, entry in zip(self.agents, agent_entries):
            strat = entry["strategy"]
            if strat not in by_strategy:
                by_strategy[strat] = {
                    "count": 0,
                    "avg_pnl_pct": 0.0,
                    "trades": 0,
                    "wins": 0,
                    "losses": 0,
                    "total_pnl": 0.0,
                    "win_rate": 0.0,
                }
            bucket = by_strategy[strat]
            bucket["count"] += 1
            bucket["trades"] += agent.trades_count
            bucket["wins"] += agent.wins
            bucket["losses"] += agent.losses
            bucket["total_pnl"] += agent.total_pnl
            bucket["avg_pnl_pct"] += agent.total_pnl_pct

        for bucket in by_strategy.values():
            bucket["avg_pnl_pct"] = round(bucket["avg_pnl_pct"] / bucket["count"] if bucket["count"] else 0.0, 2)
            bucket["win_rate"] = round((bucket["wins"] / bucket["trades"] * 100) if bucket["trades"] else 0.0, 1)
            bucket.pop("wins", None)
            bucket.pop("losses", None)

        total_pnl = round(sum(a.total_pnl for a in self.agents), 2)
        total_trades = sum(a.trades_count for a in self.agents)
        total_wins = sum(a.wins for a in self.agents)
        total_losses = sum(a.losses for a in self.agents)
        avg_win_rate = round((total_wins / total_trades * 100) if total_trades else 0.0, 1)
        summary = {
            "total_agents": len(self.agents),
            "active_agents": sum(1 for a in self.agents if a.is_in_trade),
            "total_pnl": total_pnl,
            "total_pnl_pct": round(sum(a.total_pnl_pct for a in self.agents), 2),
            "total_equity": round(self._account_equity, 2),
            "total_trades": total_trades,
            "winners": total_wins,
            "losers": total_losses,
            "total_initial_capital": self._initial_capital,
            "avg_win_rate": avg_win_rate,
            "top5": sorted(agent_entries, key=lambda x: x.get("pnl_pct", 0), reverse=True)[:5],
            "by_strategy": by_strategy,
            "prices": self._latest_prices,
            "trade_journal": {
                "equity_curve": self._equity_curve,
                "daily_pnl": self._daily_pnl,
            },
            "wallet": {
                "usdt_value": round(self._account_equity, 2),
                "status": "connected" if self._account_equity > 0 else "off",
            },
            "regime": {"current_regime": "MIXED"},
            "paper_trade": {
                "statistics": {
                    "total_orders_filled": total_trades,
                    "total_orders_placed": total_trades,
                    "total_fees_collected": 0.0,
                    "sharpe_ratio": 0.0,
                    "win_rate": avg_win_rate,
                    "profit_factor": 0.0,
                    "total_pnl": total_pnl,
                },
                "positions_summary": {
                    "total_long_positions": 0,
                    "total_short_positions": 0,
                    "total_long_pnl": 0.0,
                    "total_short_pnl": 0.0,
                },
                "order_book": {
                    "BTCUSDT": {},
                    "ETHUSDT": {},
                    "SOLUSDT": {},
                },
                "recent_trades": [],
                "pnl_by_source": {
                    "trade": {"net_pnl": total_pnl, "win_rate": avg_win_rate},
                    "dca": {"net_pnl": 0.0, "win_rate": 0.0},
                    "rebalance": {"net_pnl": 0.0, "win_rate": 0.0},
                },
            },
            "market_context": {"arena": {}},
            "discovered_strategies": {"by_strategy": {}},
            "source_comparison": {},
        }

        state = {
            "timestamp": time.time(),
            "paper_mode": self.paper_mode,
            "account": {
                "balance": self._account_balance,
                "equity": self._account_equity,
            },
            "agents": agent_entries,
            "order_history": self._order_history[:200],
            "summary": summary,
        }
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, indent=2))
        # Persist full order history to disk for durability
        try:
            data_dir = Path("data")
            data_dir.mkdir(parents=True, exist_ok=True)
            hist_file = data_dir / "order_history.json"
            # normalize entries: ensure agent field exists (derive from comment when possible)
            norm = []
            for e in self._order_history:
                ee = dict(e)
                if not ee.get("agent") and ee.get("comment"):
                    c = ee.get("comment")
                    if isinstance(c, str) and c.startswith("MTAI-"):
                        ee["agent"] = c.split("MTAI-", 1)[1]
                    else:
                        ee["agent"] = c
                norm.append(ee)
            hist_file.write_text(json.dumps(norm, indent=2))
        except Exception:
            pass

    def _record_price(self, symbol: str, price: float):
        prev = self._latest_prices.get(symbol, {}).get("price")
        change_pct = None
        if prev and prev > 0:
            change_pct = round(((price - prev) / prev) * 100, 3)
        self._latest_prices[symbol] = {
            "price": round(price, 4),
            "change_pct": change_pct,
        }

    def _append_equity_point(self, ts: float):
        point = {
            "timestamp": ts,
            "total_equity": round(self._account_equity, 2),
        }
        if not self._equity_curve or self._equity_curve[-1]["timestamp"] != ts:
            self._equity_curve.append(point)
            if len(self._equity_curve) > 240:
                self._equity_curve.pop(0)

    def _record_trade_pnl(self, ts: float, pnl: float):
        day = time.strftime("%Y-%m-%d", time.localtime(ts))
        self._daily_pnl[day] = round(self._daily_pnl.get(day, 0.0) + pnl, 2)
