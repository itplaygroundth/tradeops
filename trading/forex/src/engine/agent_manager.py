"""
Agent Manager — coordinates the multi-agent trading loop, paper position simulation,
live position syncing, and dashboard state management.
"""
import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import List, Dict, Optional

from engine.dna import create_population
from engine.agent import ForexAgent
from engine.signals import ForexSignalEngine
from engine.risk_guardian import ForexRiskGuardian, RiskResult, AccountRiskMonitor
from engine.risk_guardian import MICRO_MODE
from engine.evolution import evolve, EVOLUTION_INTERVAL
from mt5_bridge.client import MT5Client
from engine.competition_scheduler import CompetitionScheduler
from engine.asset_leader import AssetLeader
from engine.hermes_client import HermesClient, HermesError
from engine.leader_asset_supervisor import LeaderAssetSupervisor
from engine.performance_guard import PerformanceGuard
from engine.position_dedup_guard import PositionDedupGuard
from engine.strategy_performance_guard import StrategyPerformanceGuard
from engine.regime_service import RegimeService
from engine.timeframe_filter import MultiTimeframeFilter
from engine.weekend_reopen_guard import WeekendReopenGuard
from engine.xau_pullback_short import XauPullbackShortFilter
from engine.agent_execution_policy import AgentExecutionPolicy
from storage.trading_journal import is_exit_deal, deal_reason_label
from storage.trade_event_outbox import TradeEventOutbox
from mt5_bridge.pip_calc import get_pip_size

logger = logging.getLogger("agent_manager")

# Absolute path so the file lands where the dashboard server serves it
# (mtai/dashboard), regardless of the process CWD.
STATE_FILE = Path(__file__).resolve().parent.parent.parent / "dashboard" / "live_state.json"
RESET_CUTOFF_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "trading_reset.json"
DEFAULT_SHADOW_GUARD_POLICY_PATH = (
    Path(__file__).resolve().parents[4] / "strategy_lab" / "handoff" / "shadow_guard_policy.json"
)


def _atomic_write_state(state: dict, *, indent=None) -> None:
    """Write STATE_FILE atomically (tmp + os.replace).

    Plain write_text() truncates then writes, so a concurrent reader — the
    dashboard server, or the supervisor reading from its worker thread — can
    observe a half-written file and fail json.loads(). os.replace() is an
    atomic rename on POSIX, so readers always see a complete old-or-new file.
    """
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = STATE_FILE.with_name(f"{STATE_FILE.name}.{os.getpid()}.{time.time_ns()}.tmp")
    tmp_path.write_text(json.dumps(state, indent=indent))
    os.replace(tmp_path, STATE_FILE)

SOFT_TP_ENABLED = str(os.getenv("SOFT_TP_ENABLED", "true")).lower() in ("1", "true", "yes", "on")
SOFT_TP_SPREAD_MULTIPLIER = float(os.getenv("SOFT_TP_SPREAD_MULTIPLIER", "1.25"))
SOFT_TP_MIN_BUFFER = {
    "XAU": float(os.getenv("SOFT_TP_MIN_BUFFER_XAU", "0.30")),
    "JPY": float(os.getenv("SOFT_TP_MIN_BUFFER_JPY", "0.010")),
    "FX": float(os.getenv("SOFT_TP_MIN_BUFFER_FX", "0.00010")),
}

TRAILING_STOP_ENABLED = str(os.getenv("TRAILING_STOP_ENABLED", "true")).lower() in ("1", "true", "yes", "on")
TRAILING_START_R = float(os.getenv("TRAILING_START_R", "1.0"))
TRAILING_DISTANCE_R = float(os.getenv("TRAILING_DISTANCE_R", "0.5"))
TRAILING_MIN_STEP = {
    "XAU": float(os.getenv("TRAILING_MIN_STEP_XAU", "0.10")),
    "JPY": float(os.getenv("TRAILING_MIN_STEP_JPY", "0.005")),
    "FX": float(os.getenv("TRAILING_MIN_STEP_FX", "0.00005")),
}
MANAGED_MAGIC = int(os.getenv("MTAI_MAGIC", "20260101"))
DAILY_PROFIT_TARGET_USD = float(os.getenv("MTAI_DAILY_PROFIT_TARGET_USD", "20.0"))
# Micro-mode override: daily target in cents for cent accounts
DAILY_PROFIT_TARGET_CENTS = float(os.getenv("MTAI_DAILY_PROFIT_TARGET_CENTS", "500"))
DAILY_LOSS_STOP_USD = float(os.getenv("MTAI_DAILY_LOSS_STOP_USD", "10.0"))
DAILY_LOSS_STOP_CENTS = float(os.getenv("MTAI_DAILY_LOSS_STOP_CENTS", "500"))
ADAPTIVE_CAUTION_DD = float(os.getenv("ADAPTIVE_CAUTION_DD", "0.015"))
ADAPTIVE_DEFENSE_DD = float(os.getenv("ADAPTIVE_DEFENSE_DD", "0.03"))
ADAPTIVE_FLOATING_LOSS_CAUTION_USD = float(os.getenv("ADAPTIVE_FLOATING_LOSS_CAUTION_USD", "5.0"))
ADAPTIVE_FLOATING_LOSS_DEFENSE_USD = float(os.getenv("ADAPTIVE_FLOATING_LOSS_DEFENSE_USD", "10.0"))
ADAPTIVE_LOT_MULTIPLIERS = {
    "NORMAL": float(os.getenv("ADAPTIVE_LOT_NORMAL", "1.0")),
    "CAUTION": float(os.getenv("ADAPTIVE_LOT_CAUTION", "0.5")),
    "DEFENSE": float(os.getenv("ADAPTIVE_LOT_DEFENSE", "0.25")),
    "HARD_STOP": 0.0,
}

class ForexAgentManager:
    def __init__(self, mt5_client: MT5Client, paper_mode: bool = True, agent_count: int = 25):
        self.mt5 = mt5_client
        self.paper_mode = paper_mode

        self.signal_engine = ForexSignalEngine()
        self.risk_guardian = ForexRiskGuardian()
        self.account_risk_monitor = AccountRiskMonitor(managed_magic=MANAGED_MAGIC)
        self.performance_guard = PerformanceGuard()
        from storage.history_db import last_open_ts_by_symbol
        self.position_dedup_guard = PositionDedupGuard(managed_magic=MANAGED_MAGIC, db_lookup=last_open_ts_by_symbol)
        self.strategy_performance_guard = StrategyPerformanceGuard()
        self.regime_service = RegimeService(getattr(self.mt5, "get_ohlcv", None))
        self.timeframe_filter = MultiTimeframeFilter()
        self.weekend_reopen_guard = WeekendReopenGuard()
        self.xau_pullback_short = XauPullbackShortFilter()
        self.agent_execution_policy = AgentExecutionPolicy()

        dnas = create_population(agent_count)
        self.agents: List[ForexAgent] = [
            ForexAgent(dna, self.signal_engine, self.risk_guardian, paper_mode)
            for dna in dnas
        ]

        self._tick_count = 0
        self._tick_counts_by_symbol = {}
        self._last_evolution_time = time.time()
        self._next_agent_id = agent_count
        self._account_balance = 1000.0
        self._account_equity = 1000.0
        self._account_currency = "USD"  # set from MT5 account; "USC" = cent account
        self._account_margin_free = None
        self._account_leverage = None
        self._initial_capital = 1000.0
        self._latest_prices = {}
        self._equity_curve = []
        self._daily_pnl = {}
        self._order_history = []
        self._entry_audit = []
        self._hard_stop_closed_tickets = set()
        self._manual_entries_paused = False
        self._manual_pause_reason = ""
        self._last_block_log = {}
        self._signal_stability = {}
        if "PYTEST_CURRENT_TEST" in os.environ and "FOREX_SHADOW_GUARD_POLICY" not in os.environ:
            self._shadow_guard_policy_path = Path("__pytest_no_shadow_guard_policy__.json")
        else:
            self._shadow_guard_policy_path = Path(os.getenv("FOREX_SHADOW_GUARD_POLICY", str(DEFAULT_SHADOW_GUARD_POLICY_PATH)))
        self.trade_event_outbox = None
        if "PYTEST_CURRENT_TEST" not in os.environ:
            self.trade_event_outbox = TradeEventOutbox(
                "mtai",
                Path(__file__).resolve().parent.parent.parent / "data" / "trade_event_outbox.db",
            )
        # Symbol/strategy/regime attribution tracking for walk-forward analysis
        self._attribution = {
            "by_symbol": {},
            "by_strategy": {},
            "by_timeframe": {},
            "by_regime": {},
            "by_symbol_strategy": {},
            "by_symbol_regime": {},
        }
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
        self._competition_semaphore = asyncio.Semaphore(1)
        self.leader_asset_supervisor = LeaderAssetSupervisor()
        self._leader_asset_supervisor_interval = float(os.getenv("LEADER_ASSET_SUPERVISOR_INTERVAL", "180"))
        self._last_leader_asset_supervisor_time = 0.0
        self._leader_asset_supervisor_task = None

    @staticmethod
    def _symbol_group(symbol: str) -> str:
        value = symbol.upper()
        if "XAU" in value or "GOLD" in value:
            return "XAU"
        if "JPY" in value:
            return "JPY"
        return "FX"

    @staticmethod
    def _position_side(pos: dict) -> str:
        side = pos.get("type")
        if side == 0:
            return "BUY"
        if side == 1:
            return "SELL"
        return str(side or "").upper()

    def _soft_tp_buffer(self, symbol: str, bid: float, ask: float) -> float:
        spread = max(float(ask) - float(bid), 0.0)
        group = self._symbol_group(symbol)
        return max(spread * SOFT_TP_SPREAD_MULTIPLIER, SOFT_TP_MIN_BUFFER[group])

    @staticmethod
    def _position_magic(pos: dict) -> int:
        try:
            return int(pos.get("magic") or 0)
        except Exception:
            return 0

    def _managed_positions(self, positions: List[dict]) -> List[dict]:
        return [pos for pos in positions if self._position_magic(pos) == MANAGED_MAGIC]

    async def _refresh_account_risk(
        self,
        positions: Optional[List[dict]] = None,
        account: Optional[dict] = None,
        close_on_hard: bool = True,
    ):
        if self.paper_mode:
            return self.account_risk_monitor.current

        try:
            if account is None:
                account = await self.mt5.get_account()
            if positions is None:
                positions = await self.mt5.get_positions()
        except Exception as e:
            logger.warning(f"[AccountRisk] Failed to refresh account risk: {e}")
            return self.account_risk_monitor.current

        self._account_balance = float(account.get("balance") or self._account_balance)
        self._account_equity = float(account.get("equity") or self._account_equity)
        self._account_currency = account.get("currency", self._account_currency)
        self._account_margin_free = account.get("margin_free", self._account_margin_free)
        self._account_leverage = account.get("leverage", self._account_leverage)

        today = int(time.time() / 86400)
        state = self.account_risk_monitor.evaluate(account, positions, current_day=today, now=time.time())
        self.risk_guardian.set_open_positions(state.open_positions)

        if close_on_hard and state.requires_hard_stop:
            await self._close_managed_positions_for_hard_stop(positions, state.reason)
        return state

    async def _close_managed_positions_for_hard_stop(self, positions: List[dict], reason: str):
        for pos in self._managed_positions(positions):
            ticket = pos.get("ticket")
            if not ticket or ticket in self._hard_stop_closed_tickets:
                continue
            try:
                result = await self.mt5.close_position(int(ticket))
                self._hard_stop_closed_tickets.add(ticket)
                logger.error(f"[AccountRisk] HARD_STOP closed ticket={ticket} reason={reason} result={result}")
            except Exception as e:
                logger.warning(f"[AccountRisk] HARD_STOP failed to close ticket={ticket}: {e}")

    async def _apply_live_exit_management(self, positions: List[dict]):
        if self.paper_mode:
            return

        agents_by_ticket = {agent._open_ticket: agent for agent in self.agents if agent.is_in_trade}
        for pos in positions:
            ticket = pos.get("ticket")
            if not ticket:
                continue
            magic = int(pos.get("magic") or 0)
            if magic and magic != MANAGED_MAGIC:
                continue
            agent = agents_by_ticket.get(ticket)
            symbol = pos.get("symbol") or (agent.dna.symbol if agent else "")
            side = self._position_side(pos) or (agent._open_side if agent else "")
            try:
                tick = await self.mt5.get_price(symbol)
            except Exception as e:
                logger.debug(f"[LIVE EXIT] Failed to get tick for {symbol}: {e}")
                continue

            close_price = tick.bid if side == "BUY" else tick.ask
            entry = float(pos.get("price_open") or (agent._open_entry if agent else 0.0) or 0.0)
            sl = float(pos.get("sl") or (agent._open_sl if agent else 0.0) or 0.0)
            tp = float(pos.get("tp") or (agent._open_tp if agent else 0.0) or 0.0)
            if not entry or not close_price:
                continue

            if SOFT_TP_ENABLED and tp:
                buffer = self._soft_tp_buffer(symbol, tick.bid, tick.ask)
                should_close = close_price >= (tp - buffer) if side == "BUY" else close_price <= (tp + buffer)
                if should_close:
                    try:
                        result = await self.mt5.close_position(ticket)
                        logger.info(
                            f"[SOFT TP] Closed {symbol} {side} ticket={ticket} "
                            f"close_side_price={close_price:.5f} tp={tp:.5f} buffer={buffer:.5f} result={result}"
                        )
                    except Exception as e:
                        logger.warning(f"[SOFT TP] Failed to close ticket {ticket}: {e}")
                    continue

            if not TRAILING_STOP_ENABLED or not sl:
                continue

            risk_distance = abs(entry - sl)
            if risk_distance <= 0:
                continue
            favorable = (close_price - entry) if side == "BUY" else (entry - close_price)
            if favorable < risk_distance * TRAILING_START_R:
                continue

            trail_distance = risk_distance * TRAILING_DISTANCE_R
            candidate_sl = close_price - trail_distance if side == "BUY" else close_price + trail_distance
            group = self._symbol_group(symbol)
            min_step = TRAILING_MIN_STEP[group]
            improves = candidate_sl > sl + min_step if side == "BUY" else candidate_sl < sl - min_step
            if not improves:
                continue

            try:
                result = await self.mt5.modify_position(ticket, sl=candidate_sl, tp=tp)
                if agent:
                    agent._open_sl = candidate_sl
                logger.info(
                    f"[TRAILING SL] {symbol} {side} ticket={ticket} "
                    f"SL {sl:.5f}->{candidate_sl:.5f} close_side_price={close_price:.5f} result={result}"
                )
            except Exception as e:
                logger.warning(f"[TRAILING SL] Failed to modify ticket {ticket}: {e}")

    async def _load_recent_history(self, hours: int = 24, limit: int = 200):
        """Loads recent deals from MT5 bridge and adds them to the order history."""
        try:
            deals = await self.mt5.get_recent_deals(hours=hours, limit=limit)
            reset_cutoff = 0.0
            try:
                if RESET_CUTOFF_FILE.exists():
                    reset_cutoff = float(json.loads(RESET_CUTOFF_FILE.read_text()).get("cutoff_ts") or 0)
            except Exception:
                reset_cutoff = 0.0
            if reset_cutoff > 0:
                deals = [
                    deal for deal in deals
                    if float(deal.get("time") or 0) >= reset_cutoff
                ]
            inserted_count = 0
            updated_count = 0
            daily_pnl_backfill = {}
            for d in deals:
                entry_code = d.get("entry")
                is_exit = is_exit_deal(entry_code)
                ticket = d.get("position") or d.get("ticket")
                comment = d.get("comment", "MT5")
                ts = d.get("time", int(time.time()))
                pnl = float(d.get("profit") or 0.0) + float(d.get("commission") or 0.0) + float(d.get("swap") or 0.0)
                entry = {
                    "deal_ticket": d.get("ticket"),
                    "timestamp": ts,
                    "agent": comment,
                    "symbol": d.get("symbol"),
                    "ticket": ticket,
                    "volume": d.get("volume"),
                    "price": d.get("price"),
                    "pnl": pnl,
                    "commission": d.get("commission"),
                    "swap": d.get("swap"),
                    "type": "closed" if is_exit else "live",
                    "status": "closed" if is_exit else "placed",
                    "deal_entry": entry_code,
                    "deal_reason": d.get("reason"),
                    "exit_reason": deal_reason_label(d.get("reason"), comment) if is_exit else "",
                    "magic": d.get("magic"),
                }
                # insert newest first
                self._order_history.insert(0, entry)
                if len(self._order_history) > 500:
                    self._order_history.pop()
                # persist to DB
                try:
                    from storage.history_db import upsert_order
                    if upsert_order(entry):
                        inserted_count += 1
                    else:
                        updated_count += 1
                except Exception:
                    pass
                if is_exit:
                    day = time.strftime("%Y-%m-%d", time.localtime(ts))
                    daily_pnl_backfill[day] = round(daily_pnl_backfill.get(day, 0.0) + pnl, 2)
            for day, pnl in daily_pnl_backfill.items():
                self._daily_pnl[day] = pnl
            if deals:
                logger.info(
                    f"[HistoryBackfill] processed={len(deals)} inserted={inserted_count} "
                    f"updated={updated_count} daily_pnl={daily_pnl_backfill}"
                )
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
        symbol_tick_count = self._tick_counts_by_symbol.get(symbol, 0) + 1
        # Keep legacy tests/tools that pre-seed _tick_count working until callers migrate.
        if len(self._tick_counts_by_symbol) == 0 and self._tick_count > symbol_tick_count:
            symbol_tick_count = self._tick_count
        self._tick_counts_by_symbol[symbol] = symbol_tick_count

        # Check paper positions if paper mode is active
        if self.paper_mode:
            await self._check_paper_positions(symbol, price)

        # Process agent signals every 10 ticks per symbol
        if symbol_tick_count % 10 == 0:
            regime, _ = await self.regime_service.get(symbol)
            await self._process_agents(symbol, price, regime=regime)

        # Sync live positions from MT5 every 30 ticks
        if self._tick_count % 30 == 0:
            if not self.paper_mode:
                await self._sync_positions()
            self._write_state()

        # Update account balance and equity info every 60 ticks
        if self._tick_count % 60 == 0:
            await self._update_account()
            self._schedule_leader_asset_supervisor()

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
        async with self._competition_semaphore:
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
                state = {}
                if STATE_FILE.exists():
                    try:
                        state = json.loads(STATE_FILE.read_text())
                    except Exception:
                        state = {}
                self._merge_competition_summary(state, self._competition_entry(result))
                self._merge_runtime_guard_summary(state)
                _atomic_write_state(state)
                self._schedule_leader_asset_supervisor()
            except Exception:
                logger.exception("Failed to write competition result to live state")

    def _schedule_leader_asset_supervisor(self):
        now = time.time()
        if self._leader_asset_supervisor_interval > 0:
            if now - self._last_leader_asset_supervisor_time < self._leader_asset_supervisor_interval:
                return
        task = self._leader_asset_supervisor_task
        if task is not None and not task.done():
            return
        self._last_leader_asset_supervisor_time = now
        try:
            self._leader_asset_supervisor_task = asyncio.get_event_loop().create_task(
                self._run_leader_asset_supervisor_bg()
            )
        except Exception:
            logger.exception("Failed to schedule leader asset supervisor")

    async def _run_leader_asset_supervisor_bg(self):
        try:
            proposal = await asyncio.to_thread(self.leader_asset_supervisor.run)
            state = {}
            if STATE_FILE.exists():
                try:
                    state = json.loads(STATE_FILE.read_text())
                except Exception:
                    state = {}
            state.setdefault("summary", {})["leader_asset_supervisor"] = proposal
            self._merge_runtime_guard_summary(state)
            _atomic_write_state(state)
        except Exception:
            logger.exception("Leader asset supervisor failed")

    def _competition_entry(self, result) -> Dict:
        # Forward-test PnL is the primary proof for the best live leader.
        # Sharpe is kept as a tiny tie-breaker so low-PnL leaders do not beat
        # better live forward performance just because their backtest Sharpe was high.
        leader_score = float(result.forward_pnl) + (float(result.winner_sharpe) * 0.001)
        if result.llm_error:
            leader_score -= 0.001
        return {
            "symbol": result.symbol,
            "regime": result.regime,
            "winner_sharpe": result.winner_sharpe,
            "winner_config": result.winner_config,
            "leader_score": round(leader_score, 6),
            "selection_source": result.selection_source,
            "llm_error": result.llm_error,
            "deterministic_winner_idx": result.deterministic_winner_idx,
            "llm_winner_idx": result.llm_winner_idx,
            "proposal_status": result.proposal_status,
            "proposal_reason": result.proposal_reason,
            "proposal_source": result.proposal_source,
            "approved": result.approved,
            "applied": result.applied,
            "forward_pnl": result.forward_pnl,
            "timestamp": result.timestamp,
        }

    def _merge_competition_summary(self, state: Dict, entry: Dict):
        summary = state.setdefault("summary", {})
        summary["last_competition"] = entry

        history = summary.get("competition_history") or []
        if not isinstance(history, list):
            history = []
        history.append(entry)
        history = sorted(history, key=lambda item: item.get("timestamp", 0), reverse=True)[:50]
        summary["competition_history"] = history

        by_symbol = summary.get("competition_by_symbol") or {}
        if not isinstance(by_symbol, dict):
            by_symbol = {}
        current = by_symbol.get(entry["symbol"])
        if not current or entry.get("timestamp", 0) >= current.get("timestamp", 0):
            by_symbol[entry["symbol"]] = entry
        summary["competition_by_symbol"] = by_symbol

        candidates = [item for item in history if item.get("applied") or item.get("approved")]
        if not candidates:
            candidates = history
        if candidates:
            summary["best_leader_asset"] = max(
                candidates,
                key=lambda item: (
                    item.get("forward_pnl", 0),
                    item.get("leader_score", 0),
                    item.get("winner_sharpe", 0),
                ),
            )

    def _merge_runtime_guard_summary(self, state: Dict):
        summary = state.setdefault("summary", {})
        try:
            summary["performance_guard"] = self.performance_guard.refresh()
        except Exception as exc:
            fallback = self.performance_guard.summary()
            fallback["refresh_error"] = str(exc)
            summary["performance_guard"] = fallback
        summary["position_dedup_guard"] = self.position_dedup_guard.summary()
        summary["strategy_performance_guard"] = self.strategy_performance_guard.summary()
        summary["regime_service"] = self.regime_service.summary()
        summary["timeframe_filter"] = self.timeframe_filter.summary()
        summary["xau_pullback_short"] = self.xau_pullback_short.summary()
        summary["weekend_reopen_guard"] = self.weekend_reopen_guard.summary()
        summary["agent_execution_policy"] = self.agent_execution_policy.summary()
        summary["entry_audit"] = self._entry_audit[:100]
        summary["signal_quality"] = self._signal_quality_summary()
        summary["trade_recommendations"] = self._trade_recommendations()
        summary["control"] = self.control_status()

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
                    try:
                        _strat = max(agent.dna.strategy_weights, key=lambda k: agent.dna.strategy_weights[k])
                        self.strategy_performance_guard.record(_strat, pnl)
                    except Exception:
                        pass

                    logger.info(
                        f"[PAPER CLOSE] {agent.dna.name} closed trade on {symbol}. "
                        f"Entry={agent._open_entry:.5f}, Exit={exit_price:.5f}, "
                        f"PnL=${pnl:.2f} ({pnl_pct:+.2f}%)"
                    )

                    closed_entry = {
                        "timestamp": time.time(),
                        "agent": agent.dna.name,
                        "symbol": symbol,
                        "ticket": agent._open_ticket,
                        "action": "CLOSE",
                        "side": agent._open_side,
                        "volume": getattr(agent, "_open_lot", 0.0),
                        "entry_price": agent._open_entry,
                        "price": exit_price,
                        "pnl": round(pnl, 2),
                        "pnl_pct": round(pnl_pct, 4),
                        "strategy": max(agent.dna.strategy_weights, key=lambda key: agent.dna.strategy_weights[key]),
                        "timeframe": agent.dna.timeframe,
                        "reason": "stop_loss" if sl_hit else "take_profit",
                        "type": "paper",
                        "status": "closed",
                    }
                    self._record_closed_trade(closed_entry)

                    # Reset agent state
                    agent._open_ticket = None
                    agent._open_entry = 0.0
                    agent._open_side = ""
                    agent._open_sl = 0.0
                    agent._open_tp = 0.0
                    agent._open_risk_amount = 0.0

    async def _apply_weekend_reopen_guard(self, positions: List[dict]) -> set:
        closed_tickets = set()
        if self.paper_mode:
            return closed_tickets
        managed = self._managed_positions(positions)

        pre_close = self.weekend_reopen_guard.evaluate_pre_close(managed, now=time.time())
        if pre_close.status in ("closing", "blocking", "active"):
            logger.warning(
                f"[WeekendPreCloseGuard] {pre_close.status}: {pre_close.reason} "
                f"close_tickets={pre_close.close_tickets} block_until={pre_close.block_entries_until}"
            )
        for ticket in pre_close.close_tickets:
            try:
                result = await self.mt5.close_position(ticket)
                closed_tickets.add(ticket)
                logger.error(f"[WeekendPreCloseGuard] closed ticket={ticket} result={result}")
            except Exception as e:
                logger.warning(f"[WeekendPreCloseGuard] failed to close ticket={ticket}: {e}")

        symbols = sorted({str(pos.get("symbol") or "") for pos in managed if pos.get("symbol")})
        for symbol in symbols:
            try:
                tick = await self.mt5.get_price(symbol)
            except Exception as e:
                logger.warning(f"[WeekendReopenGuard] Failed to get tick for {symbol}: {e}")
                continue

            decision = self.weekend_reopen_guard.evaluate_symbol(
                symbol=symbol,
                bid=tick.bid,
                ask=tick.ask,
                positions=managed,
                now=time.time(),
                market_ts=tick.timestamp,
            )
            if decision.status != "ok":
                logger.warning(
                    f"[WeekendReopenGuard] {symbol} {decision.status}: {decision.reason} "
                    f"spread={decision.spread} gap={decision.gap} adverse_gap={decision.adverse_gap}"
                )
            for ticket in decision.close_tickets:
                try:
                    result = await self.mt5.close_position(ticket)
                    closed_tickets.add(ticket)
                    logger.error(f"[WeekendReopenGuard] auto-closed ticket={ticket} result={result}")
                except Exception as e:
                    logger.warning(f"[WeekendReopenGuard] failed to auto-close ticket={ticket}: {e}")
        return closed_tickets

    async def _sync_positions(self):
        """Syncs active live positions on MT5 to update agent states."""
        try:
            positions = await self.mt5.get_positions()
            closed_tickets = await self._apply_weekend_reopen_guard(positions)
            if closed_tickets:
                positions = [pos for pos in positions if pos.get("ticket") not in closed_tickets]
            self._adopt_live_positions(positions)
            await self._apply_live_exit_management(positions)
            await self._refresh_account_risk(positions=positions)
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
                self._record_closed_trade({
                    "timestamp": time.time(),
                    "agent": agent.dna.name,
                    "symbol": agent.dna.symbol,
                    "ticket": ticket,
                    "pnl": 0.0,
                    "pnl_pct": 0.0,
                    "type": "closed",
                    "status": "closed",
                    "action": "CLOSE",
                    "side": agent._open_side,
                    "entry_price": agent._open_entry,
                    "price": 0.0,
                    "strategy": max(agent.dna.strategy_weights, key=lambda key: agent.dna.strategy_weights[key]),
                    "timeframe": agent.dna.timeframe,
                    "reason": "broker_close_pnl_unavailable",
                })
            else:
                pnl = history.get("pnl", 0.0)
                pnl_pct = (pnl / self._account_balance) * 100 if self._account_balance else 0.0
                agent.record_trade_result(pnl, pnl_pct)
                self.risk_guardian.on_position_closed(pnl)
                try:
                    _strat = max(agent.dna.strategy_weights, key=lambda k: agent.dna.strategy_weights[k])
                    self.strategy_performance_guard.record(_strat, pnl)
                except Exception:
                    pass
                logger.info(
                    f"[LIVE CLOSE] {agent.dna.name} closed trade on {agent.dna.symbol} (ticket {ticket}). "
                    f"PnL=${pnl:.2f} ({pnl_pct:+.2f}%)"
                )
                closed_entry = {
                    "timestamp": time.time(),
                    "agent": agent.dna.name,
                    "symbol": agent.dna.symbol,
                    "ticket": ticket,
                    "pnl": pnl,
                    "pnl_pct": pnl_pct,
                    "type": "closed",
                    "status": "closed",
                    "action": "CLOSE",
                    "side": agent._open_side,
                    "entry_price": agent._open_entry,
                    "price": history.get("exit_price") or history.get("price") or 0.0,
                    "volume": history.get("volume") or 0.0,
                    "strategy": max(agent.dna.strategy_weights, key=lambda key: agent.dna.strategy_weights[key]),
                    "timeframe": agent.dna.timeframe,
                    "reason": history.get("reason") or history.get("exit_reason") or "broker_close",
                }
                self._record_closed_trade(closed_entry)

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

    def _adopt_live_positions(self, positions: List[dict]):
        """Restore ownership of managed MT5 positions after a process restart."""
        owned_tickets = {
            agent._open_ticket for agent in self.agents if agent.is_in_trade
        }
        for position in self._managed_positions(positions):
            ticket = position.get("ticket")
            symbol = str(position.get("symbol") or "")
            if not ticket or ticket in owned_tickets or not symbol:
                continue
            agent = next(
                (
                    candidate for candidate in self.agents
                    if not candidate.is_in_trade and candidate.dna.symbol == symbol
                ),
                None,
            )
            if agent is None:
                logger.warning(
                    "[PositionAdopt] no idle agent for ticket=%s symbol=%s",
                    ticket,
                    symbol,
                )
                continue
            agent._open_ticket = ticket
            agent._open_entry = float(position.get("price_open") or 0.0)
            agent._open_side = self._position_side(position)
            agent._open_sl = float(position.get("sl") or 0.0)
            agent._open_tp = float(position.get("tp") or 0.0)
            agent._open_risk_amount = 0.0
            owned_tickets.add(ticket)
            logger.warning(
                "[PositionAdopt] restored ticket=%s symbol=%s agent=%s",
                ticket,
                symbol,
                agent.dna.name,
            )

    def _leader_asset_gate(self, symbol: str) -> Dict:
        default_gate = {
            "leader_asset": None,
            "is_leader": False,
            "min_confidence": 50,
            "max_agents": 3,
            "status": "inactive",
            "reason": "leader asset proposal unavailable",
        }
        try:
            proposal = self.leader_asset_supervisor.read_latest_proposal()
        except Exception:
            return default_gate
        if not proposal or proposal.get("status") != "accepted":
            if proposal:
                default_gate["status"] = str(proposal.get("status", "inactive"))
                default_gate["reason"] = str(proposal.get("reason", default_gate["reason"]))
            return default_gate
        leader = proposal.get("leader_asset")
        if not leader:
            return default_gate
        is_leader = symbol == leader
        return {
            "leader_asset": leader,
            "is_leader": is_leader,
            "min_confidence": 50 if is_leader else 65,
            "max_agents": 3 if is_leader else 1,
            "status": "accepted",
            "confidence": proposal.get("confidence", 0.0),
            "reason": proposal.get("reason", ""),
        }

    async def _process_agents(self, symbol: str, price: float, regime: str = None):
        """Evaluates entry signals and executes trades for idle agents assigned to a symbol."""
        if self._manual_entries_paused:
            logger.warning(f"[Control] {symbol} entries paused: {self._manual_pause_reason or 'manual pause'}")
            return
        shadow_guard = self._shadow_guard_decision(symbol, regime)
        if not shadow_guard["allowed"]:
            self._log_blocked(
                f"shadow_guard:{symbol}:{shadow_guard['regime']}",
                f"[ShadowGuard] {symbol} entries blocked: {shadow_guard['reason']}",
            )
            self._record_entry_audit({
                "timestamp": time.time(),
                "status": "blocked",
                "symbol": symbol,
                "block_stage": "shadow_guard_policy",
                "reason": shadow_guard["reason"],
                "regime": shadow_guard["regime"],
                "signal": {
                    "regime": shadow_guard["regime"],
                    "source": shadow_guard["source"],
                    "policy_path": str(self._shadow_guard_policy_path),
                },
            })
            return
        agents_for_symbol = [a for a in self.agents if a.dna.symbol == symbol and not a.is_in_trade]
        gate = self._leader_asset_gate(symbol)
        account_risk = await self._refresh_account_risk() if not self.paper_mode else self.account_risk_monitor.current
        if account_risk.blocks_entries:
            self._log_blocked(
                f"account_risk:{account_risk.mode}:{account_risk.reason}",
                f"[AccountRisk] entries blocked: {account_risk.mode} {account_risk.reason}",
            )
            return
        if not self.paper_mode and account_risk.mode == "WARNING":
            self._log_blocked(
                f"account_risk_warning:{account_risk.reason}",
                f"[AccountRisk] entries blocked on WARNING: {account_risk.reason}",
            )
            return
        if self._daily_profit_target_reached():
            today = time.strftime("%Y-%m-%d", time.localtime())
            pnl = self._daily_pnl.get(today, 0.0)
            logger.warning(
                f"[DailyTarget] entries blocked: daily realized PnL {pnl:.2f} "
                f">= target {self._daily_target_in_account_units():.2f}"
            )
            return
        if self._daily_loss_stop_reached():
            today = time.strftime("%Y-%m-%d", time.localtime())
            pnl = self._daily_pnl.get(today, 0.0)
            logger.warning(
                f"[DailyLossStop] entries blocked: daily realized PnL {pnl:.2f} "
                f"<= -{self._daily_loss_stop_in_account_units():.2f}"
            )
            return

        adaptive = self._adaptive_guard(account_risk)
        if adaptive["mode"] == "HARD_STOP":
            self._log_blocked(
                f"adaptive:{adaptive['mode']}:{adaptive['reason']}",
                f"[AdaptiveGuard] entries blocked: {adaptive['reason']}",
            )
            return

        max_agents = gate["max_agents"]
        min_confidence = gate["min_confidence"]
        if adaptive["mode"] == "DEFENSE":
            max_agents = min(max_agents, 1)
            min_confidence = min(95, min_confidence + 10)
        elif adaptive["mode"] == "CAUTION":
            min_confidence = min(95, min_confidence + 5)
        live_open_positions = account_risk.open_positions
        live_positions = []
        if not self.paper_mode:
            try:
                live_positions = await self.mt5.get_positions()
            except Exception as e:
                logger.warning(f"[PositionDedup] Failed to fetch positions: {e}")
                return

        selection = self.agent_execution_policy.select(symbol, agents_for_symbol, max_agents=max_agents)
        executors = [
            agent for agent in agents_for_symbol
            if self.agent_execution_policy.permission_for(selection, agent).allowed
        ]

        for agent in executors:
            permission = self.agent_execution_policy.permission_for(selection, agent)
            dominant_strategy = max(agent.dna.strategy_weights, key=lambda k: agent.dna.strategy_weights[k])
            audit = {
                "timestamp": time.time(),
                "status": "evaluating",
                "symbol": symbol,
                "agent": agent.dna.name,
                "agent_id": agent.dna.id,
                "strategy": dominant_strategy,
                "regime": regime,
                "agent_timeframe": agent.dna.timeframe,
                "execution_permission": permission.to_dict(),
                "leader_gate": gate,
                "adaptive_guard": adaptive,
                "min_confidence": min_confidence,
            }
            if not self.paper_mode:
                blocked, reason = self.weekend_reopen_guard.blocks_entries(symbol)
                if blocked:
                    logger.warning(f"[WeekendReopenGuard] {agent.dna.name} {symbol} blocked: {reason}")
                    audit.update({"status": "blocked", "block_stage": "weekend_reopen_guard", "reason": reason})
                    self._record_entry_audit(audit)
                    continue
            perf = self.performance_guard.evaluate(symbol, agent.dna.name)
            audit["performance_guard"] = perf.__dict__ if hasattr(perf, "__dict__") else {"allowed": perf.allowed, "reason": perf.reason}
            if not perf.allowed:
                logger.warning(f"[PerformanceGuard] {agent.dna.name} {symbol} blocked: {perf.reason}")
                audit.update({"status": "blocked", "block_stage": "performance_guard", "reason": perf.reason})
                self._record_entry_audit(audit)
                continue
            strat_guard = self.strategy_performance_guard.evaluate(dominant_strategy)
            audit["strategy_performance_guard"] = {"allowed": strat_guard.allowed, "reason": strat_guard.reason, "cooldown_remaining_seconds": strat_guard.cooldown_remaining_seconds}
            if not strat_guard.allowed:
                logger.warning(f"[StrategyPerfGuard] {agent.dna.name} {symbol} {dominant_strategy} blocked: {strat_guard.reason}")
                audit.update({"status": "blocked", "block_stage": "strategy_performance_guard", "reason": strat_guard.reason})
                self._record_entry_audit(audit)
                continue
            signal = agent.generate_signal(price, regime=regime)
            audit["base_signal"] = dict(signal)
            pullback_entry = None
            if not self.paper_mode and self.xau_pullback_short.supports(symbol):
                pullback_entry = await self.xau_pullback_short.evaluate(self.mt5, symbol, price)
                audit["pullback_entry"] = pullback_entry.__dict__ if hasattr(pullback_entry, "__dict__") else {}
                if pullback_entry.allowed:
                    if signal["action"] in ("HOLD", pullback_entry.action):
                        signal = {
                            "action": pullback_entry.action,
                            "confidence": max(int(signal.get("confidence") or 0), pullback_entry.confidence),
                            "reason": f"{pullback_entry.reason}; base={signal.get('reason', '')}",
                        }
                    else:
                        self._log_blocked(
                            f"pullback_entry:{symbol}:opposite:{pullback_entry.action}",
                            (
                                f"[PullbackEntry] {agent.dna.name} {symbol} {signal['action']} blocked: "
                                f"pullback setup favors {pullback_entry.action}"
                            ),
                        )
                        audit.update({
                            "status": "blocked",
                            "block_stage": "pullback_entry",
                            "reason": f"pullback setup favors {pullback_entry.action}",
                            "final_signal": dict(signal),
                        })
                        self._record_entry_audit(audit)
                        continue
                elif signal["action"] != "HOLD":
                    self._log_blocked(
                        f"pullback_entry:{symbol}:{pullback_entry.reason}",
                        f"[PullbackEntry] {agent.dna.name} {symbol} {signal['action']} blocked: {pullback_entry.reason}",
                    )
                    audit.update({
                        "status": "blocked",
                        "block_stage": "pullback_entry",
                        "reason": pullback_entry.reason,
                        "final_signal": dict(signal),
                    })
                    self._record_entry_audit(audit)
                    continue
            audit["final_signal"] = dict(signal)
            if signal["action"] == "HOLD" or signal["confidence"] < min_confidence:
                audit.update({
                    "status": "blocked",
                    "block_stage": "signal_confidence",
                    "reason": f"{signal['action']} confidence {signal['confidence']} < {min_confidence}",
                })
                self._record_entry_audit(audit)
                continue
            if not self.paper_mode:
                stability = self._update_signal_stability(agent, symbol, signal)
                audit["signal_stability"] = stability
                if not stability["stable"]:
                    reason = "signal {} stable {}/2".format(stability["action"], stability["count"])
                    audit.update({"status": "blocked", "block_stage": "signal_stability", "reason": reason})
                    self._record_entry_audit(audit)
                    continue
            action = "BUY" if signal["action"] == "LONG" else "SELL"
            audit["action"] = action

            if not self.paper_mode:
                dedup_kwargs = {}
                if pullback_entry and pullback_entry.allowed:
                    dedup_kwargs = {
                        "max_per_symbol": pullback_entry.basket_max_positions,
                        "max_per_symbol_side": pullback_entry.basket_max_positions,
                        "cooldown_seconds": pullback_entry.basket_cooldown_seconds,
                    }
                dedup = self.position_dedup_guard.evaluate(symbol, action, live_positions, **dedup_kwargs)
                audit["position_dedup_guard"] = dedup.__dict__ if hasattr(dedup, "__dict__") else {"allowed": dedup.allowed, "reason": dedup.reason}
                if not dedup.allowed:
                    logger.warning(f"[PositionDedup] {agent.dna.name} {symbol} {action} blocked: {dedup.reason}")
                    audit.update({"status": "blocked", "block_stage": "position_dedup_guard", "reason": dedup.reason})
                    self._record_entry_audit(audit)
                    continue
                mtf = await (self.timeframe_filter.evaluate_mean_reversion(self.mt5, symbol, agent.dna.timeframe) if dominant_strategy == "mean_reversion" else self.timeframe_filter.evaluate(self.mt5, symbol, action, agent.dna.timeframe))
                audit["timeframe_filter"] = mtf.__dict__ if hasattr(mtf, "__dict__") else {"allowed": mtf.allowed, "reason": mtf.reason}
                if not mtf.allowed:
                    logger.warning(f"[MTF] {agent.dna.name} {symbol} {action} blocked: {mtf.reason}")
                    audit.update({"status": "blocked", "block_stage": "timeframe_filter", "reason": mtf.reason})
                    self._record_entry_audit(audit)
                    continue

            # Risk validation
            today = int(time.time() / 86400)
            day_key = time.strftime("%Y-%m-%d", time.localtime())
            target_profit_remaining = max(self._daily_target_in_account_units() - self._daily_pnl.get(day_key, 0.0), 0.0)
            
            # Simple mock lookup to pass to dynamic risk / lot sizing without server dependency in tests
            def get_price_func(sym):
                return price

            risk_result = self.risk_guardian.validate(
                symbol=symbol,
                action=action,
                entry_price=price,
                sl_pips=agent.dna.sl_pips,
                tp_pips=agent.dna.tp_pips,
                account_balance=self._account_balance,
                account_equity=self._account_equity,
                current_day=today,
                get_price_func=get_price_func,
                account_currency=self._account_currency,
                open_positions=live_open_positions if not self.paper_mode else None,
                account_margin_free=self._account_margin_free if not self.paper_mode else None,
                account_leverage=self._account_leverage if not self.paper_mode else None,
                target_profit_remaining=target_profit_remaining,
                risk_multiplier=adaptive["lot_multiplier"],
            )

            audit["risk_guardian"] = {
                "allowed": risk_result.allowed,
                "reason": risk_result.reason,
                "lot_size": risk_result.lot_size,
                "risk_amount": risk_result.risk_amount,
                "sl_price": risk_result.sl_price,
                "tp_price": risk_result.tp_price,
            }
            if not risk_result.allowed:
                logger.debug(f"[{agent.dna.name}] blocked: {risk_result.reason}")
                audit.update({"status": "blocked", "block_stage": "risk_guardian", "reason": risk_result.reason})
                self._record_entry_audit(audit)
                continue

            if not self.paper_mode:
                pre_order = await self._pre_order_revalidation(agent, symbol, action, signal, dominant_strategy, risk_result, audit, regime=regime)
                audit["pre_order_revalidation"] = pre_order
                if not pre_order.get("allowed"):
                    reason = pre_order.get("reason")
                    logger.warning(f"[PreOrder] {agent.dna.name} {symbol} {action} blocked: {reason}")
                    audit.update({"status": "blocked", "block_stage": "pre_order_revalidation", "reason": reason})
                    self._record_entry_audit(audit)
                    continue

            # Execute
            audit.update({"status": "approved", "reason": "all entry guards passed"})
            if self.paper_mode:
                await self._paper_execute(agent, signal, price, risk_result, audit=audit)
            else:
                await self._live_execute(agent, signal, price, risk_result, audit=audit)
                if agent._open_ticket:
                    audit.update({"status": "placed", "ticket": agent._open_ticket})
                    self._record_entry_audit(audit)
                    live_open_positions += 1
                    live_positions.append({
                        "ticket": agent._open_ticket,
                        "symbol": symbol,
                        "type": action,
                        "magic": MANAGED_MAGIC,
                    })
                    self.position_dedup_guard.record_open(symbol)

    def _update_signal_stability(self, agent, symbol: str, signal: dict) -> Dict:
        action = str(signal.get("action") or "HOLD")
        key = (symbol, agent.dna.name)
        now = time.time()
        current = self._signal_stability.get(key, {})
        previous_action = current.get("action")
        count = int(current.get("count") or 0) + 1 if previous_action == action else 1
        self._signal_stability[key] = {"action": action, "count": count, "updated_at": now, "previous_action": previous_action}
        return {"action": action, "count": count, "stable": action != "HOLD" and count >= 2, "previous_action": previous_action}

    async def _pre_order_revalidation(self, agent, symbol: str, action: str, signal: dict, dominant_strategy: str, risk: RiskResult, audit: Dict, regime: str = None) -> Dict:
        try:
            positions = await self.mt5.get_positions()
            account_risk = await self._refresh_account_risk(positions=positions, close_on_hard=False)
        except Exception as e:
            return {"allowed": False, "reason": f"pre-order account/position refresh failed: {e}"}
        if account_risk.blocks_entries or account_risk.mode == "WARNING":
            return {"allowed": False, "reason": f"pre-order account risk {account_risk.mode}: {account_risk.reason}"}
        dedup = self.position_dedup_guard.evaluate(symbol, action, positions)
        if not dedup.allowed:
            return {"allowed": False, "reason": f"pre-order dedup: {dedup.reason}"}
        try:
            tick = await self.mt5.get_price(symbol)
        except Exception as e:
            return {"allowed": False, "reason": f"pre-order price unavailable: {e}"}
        pip_size = get_pip_size(symbol)
        spread_pips = max(float(tick.ask) - float(tick.bid), 0.0) / pip_size if pip_size else 0.0
        max_spread = 45.0 if self._symbol_group(symbol) == "XAU" else (3.0 if self._symbol_group(symbol) == "JPY" else 2.5)
        if spread_pips > max_spread:
            return {"allowed": False, "reason": f"pre-order spread {spread_pips:.2f}pip > {max_spread:.2f}pip"}
        fresh_price = (float(tick.bid) + float(tick.ask)) / 2.0
        fresh_signal = agent.generate_signal(fresh_price, regime=regime)
        if fresh_signal.get("action") != signal.get("action"):
            return {"allowed": False, "reason": "pre-order signal changed {} -> {}".format(signal.get("action"), fresh_signal.get("action")), "fresh_signal": fresh_signal}
        try:
            self.timeframe_filter.invalidate(symbol)
            mtf = await (self.timeframe_filter.evaluate_mean_reversion(self.mt5, symbol, agent.dna.timeframe) if dominant_strategy == "mean_reversion" else self.timeframe_filter.evaluate(self.mt5, symbol, action, agent.dna.timeframe))
        except Exception as e:
            return {"allowed": False, "reason": f"pre-order MTF failed: {e}"}
        if not mtf.allowed:
            return {"allowed": False, "reason": f"pre-order MTF: {mtf.reason}", "mtf": mtf.__dict__}
        return {"allowed": True, "reason": "pre-order checks passed", "spread_pips": spread_pips, "fresh_signal": fresh_signal, "mtf": mtf.__dict__}

    def control_status(self) -> Dict:
        return {
            "entries_paused": self._manual_entries_paused,
            "pause_reason": self._manual_pause_reason,
            "paper_mode": self.paper_mode,
            "account_risk_mode": self.account_risk_monitor.current.mode,
            "account_risk_reason": self.account_risk_monitor.current.reason,
            "daily_pnl": self._daily_pnl,
            "daily_profit_target": self._daily_target_in_account_units(),
            "daily_loss_stop": self._daily_loss_stop_in_account_units(),
            "mads_defensive_policy": self.risk_guardian.external_policy(),
        }

    def set_risk_policy(self, mode: str, risk_scale: float, max_positions: int) -> Dict:
        policy = self.risk_guardian.set_external_policy(mode, risk_scale, max_positions)
        if policy["risk_scale"] <= 0 or policy["max_positions"] <= 0:
            self.pause_entries(f"MADS {policy['mode']} defensive policy")
        logger.warning(f"[Control] MADS defensive policy applied: {policy}")
        return self.control_status()

    def pause_entries(self, reason: str = "manual control") -> Dict:
        self._manual_entries_paused = True
        self._manual_pause_reason = reason or "manual control"
        logger.warning(f"[Control] entries paused: {self._manual_pause_reason}")
        return self.control_status()

    def resume_entries(self) -> Dict:
        self._manual_entries_paused = False
        self._manual_pause_reason = ""
        logger.warning("[Control] entries resumed")
        return self.control_status()

    def _log_blocked(self, key: str, message: str, interval_seconds: int = 60):
        now = time.time()
        last = self._last_block_log.get(key, 0.0)
        if now - last >= interval_seconds:
            self._last_block_log[key] = now
            logger.warning(message)

    def _shadow_guard_decision(self, symbol: str, regime: str = None) -> Dict:
        policy = self._load_shadow_guard_policy()
        blocked = self._shadow_guard_blocked_regimes(policy)
        if not blocked:
            return {"allowed": True, "reason": "no shadow guard blocked regimes", "regime": regime or "unknown", "source": "none"}
        candidates = []
        if regime:
            candidates.append(("runtime_regime", regime))
        for timeframe in ("M15", "H1"):
            try:
                hist = self.signal_engine.get_history(symbol, timeframe)
                if getattr(hist, "count", 0) >= 20:
                    heuristic, _ = hist.market_regime()
                    candidates.append((f"history_{timeframe}", heuristic))
            except Exception:
                logger.debug("shadow guard history regime failed for %s %s", symbol, timeframe, exc_info=True)
        for source, candidate in candidates:
            normalised = self._normalise_shadow_regime(candidate)
            if normalised in blocked:
                return {
                    "allowed": False,
                    "reason": f"regime {candidate} blocked by shadow guard policy",
                    "regime": normalised,
                    "source": source,
                }
        return {"allowed": True, "reason": "regime allowed by shadow guard policy", "regime": regime or "unknown", "source": "runtime_regime"}

    def _load_shadow_guard_policy(self) -> Dict:
        try:
            if not self._shadow_guard_policy_path.exists():
                return {}
            return json.loads(self._shadow_guard_policy_path.read_text())
        except Exception:
            logger.warning("Failed to load shadow guard policy: %s", self._shadow_guard_policy_path, exc_info=True)
            return {}

    @classmethod
    def _shadow_guard_blocked_regimes(cls, policy: Dict) -> set:
        raw = policy.get("no_trade_regimes") or policy.get("enforcement", {}).get("block_new_entries_when_regime_in") or []
        return {cls._normalise_shadow_regime(item) for item in raw}

    @staticmethod
    def _normalise_shadow_regime(regime) -> str:
        value = str(regime or "unknown").strip().lower().replace("-", "_").replace(" ", "_")
        aliases = {
            "high_vol": "high_volatility",
            "highvol": "high_volatility",
            "high_volatility": "high_volatility",
            "highvolatility": "high_volatility",
            "volatile": "high_volatility",
            "volatility": "high_volatility",
            "high": "high_volatility",
            "sideway": "sideways",
            "sideways": "sideways",
            "range": "sideways",
            "ranging": "sideways",
            "trend_up": "trend",
            "trend_down": "trend",
            "trending": "trend",
        }
        return aliases.get(value, value)

    def _record_entry_audit(self, audit: Dict):
        try:
            entry = dict(audit or {})
            entry.setdefault("timestamp", time.time())
            self._entry_audit.insert(0, entry)
            if len(self._entry_audit) > 200:
                self._entry_audit.pop()
        except Exception:
            pass

    def _signal_quality_summary(self) -> Dict:
        cutoff = time.time() - 86400
        audits = [
            dict(item)
            for item in self._entry_audit
            if float(item.get("timestamp") or 0.0) >= cutoff
        ]
        by_stage: Dict[str, int] = {}
        by_symbol: Dict[str, int] = {}
        by_strategy: Dict[str, int] = {}
        for item in audits:
            stage = str(item.get("block_stage") or item.get("status") or "unknown")
            symbol = str(item.get("symbol") or "UNKNOWN")
            strategy = str(item.get("strategy") or "unknown")
            by_stage[stage] = by_stage.get(stage, 0) + 1
            by_symbol[symbol] = by_symbol.get(symbol, 0) + 1
            by_strategy[strategy] = by_strategy.get(strategy, 0) + 1
        signal_only = [
            item for item in self._order_history
            if str(item.get("type") or "").lower() == "signal_only"
            and float(item.get("timestamp") or 0.0) >= cutoff
        ]
        min_forward_samples = int(os.getenv("SIGNAL_QUALITY_MIN_FORWARD_SAMPLES", "20"))
        ready = len(signal_only) >= min_forward_samples and not self._manual_entries_paused
        return {
            "mode": "signal_only_forward_test",
            "window_hours": 24,
            "audit_events": len(audits),
            "signal_only_candidates": len(signal_only),
            "by_block_stage": by_stage,
            "by_symbol": by_symbol,
            "by_strategy": by_strategy,
            "min_forward_samples": min_forward_samples,
            "ready_for_execution": False,
            "reason": (
                "execution locked until forward signal sample reaches "
                f"{min_forward_samples} and expectancy review is positive"
            ) if not ready else "manual review required before execution unlock",
        }

    def _trade_recommendations(self) -> Dict:
        min_confidence = int(os.getenv("FOREX_RECOMMENDATION_MIN_CONFIDENCE", "55"))
        recent_audits = list(self._entry_audit[:200])
        mtf_summary = self.timeframe_filter.summary()
        mtf_latest = mtf_summary.get("latest", {}) if isinstance(mtf_summary, dict) else {}
        symbols = sorted({agent.dna.symbol for agent in self.agents})
        recommendations = []
        symbol_rows = []

        for symbol in symbols:
            agents = [agent for agent in self.agents if agent.dna.symbol == symbol and not agent.is_in_trade]
            latest_mtf = dict(mtf_latest.get(symbol) or {})
            symbol_candidates = []
            for agent in agents:
                strategy = max(agent.dna.strategy_weights, key=lambda key: agent.dna.strategy_weights[key])
                try:
                    price_snapshot = self._latest_prices.get(symbol) or {}
                    current_price = float(price_snapshot.get("price") or 0.0)
                    signal = dict(agent.generate_signal(current_price))
                except Exception as exc:
                    signal = {"action": "HOLD", "confidence": 0, "reason": f"signal unavailable: {exc}"}
                action = str(signal.get("action") or "HOLD")
                confidence = int(signal.get("confidence") or 0)
                if action == "HOLD" or confidence < min_confidence:
                    continue
                order_action = "BUY" if action == "LONG" else "SELL"
                primary_trend = latest_mtf.get("primary_trend", "")
                higher_trend = latest_mtf.get("higher_trend", "")
                primary_tf = latest_mtf.get("primary_timeframe") or agent.dna.timeframe
                higher_tf = latest_mtf.get("higher_timeframe") or ""
                mtf_aligned = (
                    (order_action == "BUY" and primary_trend == "up" and higher_trend == "up")
                    or (order_action == "SELL" and primary_trend == "down" and higher_trend == "down")
                    or (
                        strategy == "mean_reversion"
                        and primary_trend == "range"
                        and higher_trend == "range"
                    )
                )
                if not mtf_aligned:
                    continue
                symbol_candidates.append({
                    "symbol": symbol,
                    "action": order_action,
                    "signal_action": action,
                    "timeframe": primary_tf,
                    "higher_timeframe": higher_tf,
                    "strategy": strategy,
                    "confidence": confidence,
                    "reason": signal.get("reason") or "agent signal",
                    "mtf": {
                        "primary_trend": primary_trend,
                        "higher_trend": higher_trend,
                    },
                    "execution_mode": (
                        "signal_only"
                        if os.getenv("DISABLE_ORDERS", "false").lower() in ("1", "true", "yes", "on")
                        else ("paper" if self.paper_mode else "demo")
                    ),
                    "executable": False,
                    "execution_note": "orders are disabled until forward review is positive",
                })

            best = sorted(symbol_candidates, key=lambda item: item["confidence"], reverse=True)[:3]
            if best:
                recommendations.extend(best)
            latest_blocks = [
                item for item in recent_audits
                if item.get("symbol") == symbol
            ][:5]
            symbol_rows.append({
                "symbol": symbol,
                "best": best[0] if best else None,
                "alternatives": best[1:],
                "status": "candidate_found" if best else "no_signal",
                "message": (
                    "candidate found; execution remains locked by signal-only mode"
                    if best else "no signal found across available timeframes"
                ),
                "timeframe_context": latest_mtf,
                "recent_blocks": [
                    {
                        "stage": item.get("block_stage") or item.get("status"),
                        "strategy": item.get("strategy"),
                        "reason": item.get("reason"),
                        "timeframe": item.get("timeframe"),
                    }
                    for item in latest_blocks
                ],
            })

        best_overall = sorted(recommendations, key=lambda item: item["confidence"], reverse=True)[:5]
        return {
            "mode": "advisory",
            "min_confidence": min_confidence,
            "ready_for_execution": False,
            "best_overall": best_overall,
            "symbols": symbol_rows,
            "message": (
                "no signal found in any timeframe"
                if not best_overall else
                "recommendations are advisory; live execution is locked until forward review passes"
            ),
        }

    async def _paper_execute(self, agent: ForexAgent, signal: dict, price: float, risk: RiskResult, audit: Optional[dict] = None):
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
                "audit": audit or {},
            }
            if audit is not None:
                audit.update({"status": "placed", "ticket": agent._open_ticket})
                self._record_entry_audit(audit)
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

    async def _live_execute(self, agent: ForexAgent, signal: dict, price: float, risk: RiskResult, audit: Optional[dict] = None):
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
            if result.get("status") == "skipped" or result.get("reason") == "orders_disabled":
                logger.warning(f"[SignalOnly] {agent.dna.name} {action} {agent.dna.symbol} skipped: orders disabled")
                order = {
                    "timestamp": time.time(),
                    "agent": agent.dna.name,
                    "symbol": agent.dna.symbol,
                    "action": action,
                    "volume": risk.lot_size,
                    "price": price,
                    "sl": risk.sl_price,
                    "tp": risk.tp_price,
                    "type": "signal_only",
                    "status": "blocked",
                    "ticket": None,
                    "reason": "orders_disabled",
                    "audit": audit or {},
                }
                self._order_history.insert(0, order)
                if len(self._order_history) > 500:
                    self._order_history.pop()
                if audit is not None:
                    audit.update({"status": "blocked", "block_stage": "signal_only", "reason": "orders_disabled"})
                    self._record_entry_audit(audit)
                return
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
                    "audit": audit or {},
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
            if audit is not None:
                audit.update({"status": "failed", "block_stage": "live_execute", "reason": str(e)})
                self._record_entry_audit(audit)

    async def _update_account(self):
        """Refreshes account balance and equity details from MT5."""
        if self.paper_mode:
            return
        try:
            account = await self.mt5.get_account()
            await self._refresh_account_risk(account=account)
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
        previous_competition_summary = {}
        if STATE_FILE.exists():
            try:
                previous_state = json.loads(STATE_FILE.read_text())
                previous_summary = previous_state.get("summary", {})
                previous_competition_summary = {
                    key: previous_summary.get(key)
                    for key in (
                        "last_competition",
                        "competition_history",
                        "competition_by_symbol",
                        "best_leader_asset",
                        "leader_asset_supervisor",
                    )
                    if previous_summary.get(key)
                }
            except Exception:
                previous_competition_summary = {}

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
        summary.update(previous_competition_summary)
        summary["account_risk"] = self.account_risk_monitor.current.to_dict()
        summary["adaptive_guard"] = self._adaptive_guard(self.account_risk_monitor.current)
        self._merge_runtime_guard_summary({"summary": summary})

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
        _atomic_write_state(state, indent=2)
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

    def _record_closed_trade(self, trade: dict):
        trade["canonical_trade_id"] = self._canonical_trade_id(trade)
        self._order_history.insert(0, trade)
        if len(self._order_history) > 500:
            self._order_history.pop()
        try:
            from storage.history_db import insert_order
            insert_order(trade)
        except Exception:
            pass
        if self.trade_event_outbox is None:
            return
        try:
            trade["canonical_trade_id"] = self._canonical_trade_id(trade)
            trade["event_id"] = self.trade_event_outbox.emit("trade.closed", trade)
        except Exception as error:
            logger.warning("Failed to enqueue trade.closed event: %s", error)

    @staticmethod
    def _canonical_trade_id(trade: dict) -> str:
        symbol = trade.get("symbol") or "UNKNOWN"
        ticket = trade.get("ticket") or trade.get("order_id") or trade.get("position_id") or "no-ticket"
        timestamp = float(trade.get("timestamp") or time.time())
        timestamp = int(timestamp * 1000) / 1000
        pnl = float(trade.get("pnl") or 0.0)
        return f"{symbol}:{ticket}:{timestamp:.3f}:{pnl:.2f}"

    def _record_trade_pnl(self, ts: float, pnl: float):
        day = time.strftime("%Y-%m-%d", time.localtime(ts))
        self._daily_pnl[day] = round(self._daily_pnl.get(day, 0.0) + pnl, 2)

    def _daily_profit_target_reached(self, now: Optional[float] = None) -> bool:
        ts = time.time() if now is None else now
        day = time.strftime("%Y-%m-%d", time.localtime(ts))
        target = self._daily_target_in_account_units()
        return self._daily_pnl.get(day, 0.0) >= target

    def _daily_loss_stop_reached(self, now: Optional[float] = None) -> bool:
        ts = time.time() if now is None else now
        day = time.strftime("%Y-%m-%d", time.localtime(ts))
        stop = self._daily_loss_stop_in_account_units()
        return self._daily_pnl.get(day, 0.0) <= -stop

    def _daily_target_in_account_units(self) -> float:
        """Return daily profit target in account-currency units.

        On cent accounts (USC) ``_daily_pnl`` is already in cents, so we must
        compare against a cent target — not the USD target, which would stop
        trading after only 20 *cents* of profit.
        """
        from mt5_bridge.pip_calc import is_cent_currency
        if is_cent_currency(self._account_currency):
            return DAILY_PROFIT_TARGET_CENTS
        return DAILY_PROFIT_TARGET_USD

    def _daily_loss_stop_in_account_units(self) -> float:
        from mt5_bridge.pip_calc import is_cent_currency
        if is_cent_currency(self._account_currency):
            return DAILY_LOSS_STOP_CENTS
        return DAILY_LOSS_STOP_USD

    def _adaptive_guard(self, account_risk=None) -> Dict:
        account_risk = account_risk or self.account_risk_monitor.current
        mode = "NORMAL"
        reason = "OK"
        if getattr(account_risk, "blocks_entries", False) or getattr(account_risk, "mode", "") == "HARD_STOP":
            mode = "HARD_STOP"
            reason = getattr(account_risk, "reason", "") or getattr(account_risk, "mode", "HARD_STOP")
        elif getattr(account_risk, "mode", "") == "WARNING":
            mode = "DEFENSE"
            reason = getattr(account_risk, "reason", "") or "account warning"
        else:
            peak_dd = float(getattr(account_risk, "peak_drawdown_pct", 0.0) or 0.0) / 100.0
            floating_pnl = float(getattr(account_risk, "floating_pnl", 0.0) or 0.0)
            if peak_dd >= ADAPTIVE_DEFENSE_DD or floating_pnl <= -ADAPTIVE_FLOATING_LOSS_DEFENSE_USD:
                mode = "DEFENSE"
                reason = "drawdown/floating loss reached defense threshold"
            elif peak_dd >= ADAPTIVE_CAUTION_DD or floating_pnl <= -ADAPTIVE_FLOATING_LOSS_CAUTION_USD:
                mode = "CAUTION"
                reason = "drawdown/floating loss reached caution threshold"
        return {
            "mode": mode,
            "reason": reason,
            "lot_multiplier": ADAPTIVE_LOT_MULTIPLIERS.get(mode, 1.0),
        }
