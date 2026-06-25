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
import json
import logging
import os
import time
from pathlib import Path
from typing import List, Dict, Optional

from engine.dna import create_population, random_dna, CRYPTO_SYMBOLS, TIMEFRAMES
from engine.agent import CryptoAgent
from engine.signals import CryptoSignalEngine
from engine.risk_guardian import CryptoRiskGuardian, RiskResult, MIN_RR_RATIO
from engine.evolution import evolve, EVOLUTION_INTERVAL
from engine.strategy_performance_guard import StrategyPerformanceGuard
from engine.performance_guard import PairPerformanceGuard
from engine.position_dedup_guard import PositionDedupGuard
from engine.regime_service import RegimeService
from storage.trade_event_outbox import TradeEventOutbox

logger = logging.getLogger("agent_manager")

def _env_pairs(name: str = "CRYPTO_PAIRS") -> list[str]:
    raw = os.getenv(name, "BTCUSDT,ETHUSDT")
    pairs = [item.strip().upper() for item in raw.split(",") if item.strip()]
    return pairs or ["BTCUSDT", "ETHUSDT"]

DEFAULT_PAIRS = _env_pairs()
TREND_FOLLOW_STRATEGIES = {"momentum", "order_flow", "breakout_atr", "market_structure"}
MAX_SIGNALS_PER_SYMBOL = 3
ENTRY_STRATEGY_ALLOWLIST = {
    item.strip()
    for item in os.getenv("CRYPTO_ENTRY_STRATEGY_ALLOWLIST", "market_structure,momentum").split(",")
    if item.strip()
}
DEFENSE_STRATEGY_ALLOWLIST = {
    item.strip()
    for item in os.getenv("CRYPTO_DEFENSE_STRATEGY_ALLOWLIST", "market_structure").split(",")
    if item.strip()
}
STRATEGY_RISK_CAPS = {
    "grid_scalp": {"sl": 0.008, "tp": 0.012, "atr": 0.8},
    "mean_reversion": {"sl": 0.010, "tp": 0.016, "atr": 1.0},
    "order_flow": {"sl": 0.012, "tp": 0.020, "atr": 1.1},
    "momentum": {"atr": 1.2},
    "breakout_atr": {"atr": 1.4},
    "market_structure": {"atr": 1.2},
}
TIMEFRAME_SL_CAPS = {
    "M5": 0.008,
    "M15": 0.012,
    "H1": 0.015,
    "H4": 0.018,
}
TIMEFRAME_TP_CAPS = {
    "M5": 0.012,
    "M15": 0.020,
    "H1": 0.030,
    "H4": 0.050,
}
MIN_EFFECTIVE_SL_PCT = 0.003
BLOCK_LOG_INTERVAL_SECONDS = int(os.getenv("CRYPTO_BLOCK_LOG_INTERVAL_SECONDS", "60"))
SIGNAL_ONLY_EXECUTION_ENABLED = str(os.getenv("CRYPTO_SIGNAL_ONLY_EXECUTION_ENABLED", "true")).lower() in (
    "1",
    "true",
    "yes",
    "on",
)
FORCE_SIGNAL_ONLY = str(os.getenv("CRYPTO_FORCE_SIGNAL_ONLY", "true")).lower() in (
    "1",
    "true",
    "yes",
    "on",
)
SIGNAL_ONLY_HISTORY_INTERVAL_SECONDS = int(os.getenv("CRYPTO_SIGNAL_ONLY_HISTORY_INTERVAL_SECONDS", "300"))
DEFAULT_SHADOW_GUARD_POLICY_PATH = (
    Path(__file__).resolve().parents[4] / "strategy_lab" / "handoff" / "shadow_guard_policy.json"
)


class CryptoAgentManager:
    def __init__(self, router, paper_mode: bool = True, agent_count: int = 25, pairs: list = None,
                 runtime_mode: str = None):
        self.router = router
        self.paper_mode = paper_mode
        self.runtime_mode = runtime_mode or ("paper" if paper_mode else "live")
        self._pairs: List[str] = list(pairs) if pairs else list(DEFAULT_PAIRS)

        self.signal_engine = CryptoSignalEngine()
        self.risk_guardian = CryptoRiskGuardian()
        self.strategy_performance_guard = StrategyPerformanceGuard()
        self.pair_performance_guard = PairPerformanceGuard()
        self.position_dedup_guard = PositionDedupGuard()
        self.regime_service = RegimeService(getattr(self.router, "get_ohlcv", None))
        if "PYTEST_CURRENT_TEST" in os.environ and "CRYPTO_SHADOW_GUARD_POLICY" not in os.environ:
            self._shadow_guard_policy_path = Path("__pytest_no_shadow_guard_policy__.json")
        else:
            self._shadow_guard_policy_path = Path(os.getenv("CRYPTO_SHADOW_GUARD_POLICY", str(DEFAULT_SHADOW_GUARD_POLICY_PATH)))

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
        self._entry_audit: List[dict] = []
        self._manual_entries_paused = False
        self._manual_pause_reason = ""
        self._last_block_log: Dict[str, float] = {}
        self._last_signal_only_record: Dict[str, float] = {}
        self._credential_verified = bool(self.paper_mode)
        self._credential_error = ""
        self.trade_event_outbox = None
        if "PYTEST_CURRENT_TEST" not in os.environ:
            self.trade_event_outbox = TradeEventOutbox(
                "crypto-ai",
                Path(__file__).resolve().parent.parent.parent / "data" / "trade_event_outbox.db",
            )

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

    # ── warmup ──────────────────────────────────────────
    async def warmup(self) -> None:
        """Backfill candle histories with real OHLC klines so agents trade
        immediately instead of waiting hours for ticks to fill the buckets.

        Best-effort: any failure degrades to a cold start (ticks fill candles).
        """
        seeded = 0
        for symbol in self._pairs:
            for tf in TIMEFRAMES:
                try:
                    bars = await self.router.get_ohlcv(symbol, timeframe=tf, count=200)
                except Exception as e:
                    logger.warning(f"[Warmup] {symbol} {tf} backfill failed: {e}")
                    continue
                hist = self.signal_engine.get_history(symbol, tf)
                for b in bars:
                    vol = b.get("volume", 0.0)
                    taker_buy = b.get("taker_buy")  # None on feeds without it (Bybit)
                    if taker_buy is None:
                        buy_vol = sell_vol = None  # -> 50/50 split in seed_candle
                    else:
                        buy_vol = taker_buy
                        sell_vol = max(0.0, vol - taker_buy)
                    hist.seed_candle(
                        open_=b["open"], high=b["high"], low=b["low"],
                        close=b["close"], volume=vol,
                        timestamp=b.get("time", 0.0),
                        buy_vol=buy_vol, sell_vol=sell_vol,
                    )
                seeded += len(bars)
        logger.info(f"[Warmup] seeded {seeded} candles across {len(self._pairs)} pairs x {len(TIMEFRAMES)} TFs")
        if not self.paper_mode and bool(getattr(self.router, "live_trading_supported", False)):
            try:
                account = await self.router.get_account()
                self._credential_verified = True
                self._credential_error = ""
                balances = account.get("balances", {})
                usdt = balances.get("USDT", {}) if isinstance(balances, dict) else next(
                    (item for item in balances if item.get("asset") == "USDT"),
                    {},
                )
                balance = float(usdt.get("free", 0.0)) + float(usdt.get("locked", 0.0))
                if balance > 0:
                    self._account_balance = balance
                    self._account_equity = balance
                    realized_pnl = sum(agent.total_pnl for agent in self.agents)
                    inferred_initial = balance - realized_pnl
                    if (
                        self._initial_capital <= 0
                        or balance > self._initial_capital * 2
                        or balance < self._initial_capital * 0.5
                    ):
                        self._initial_capital = max(inferred_initial, balance, 1.0)
                logger.info(
                    "[Account] %s balance=%.2f USDT",
                    getattr(self.router, "network", "unknown"),
                    self._account_balance,
                )
            except Exception as e:
                self._credential_verified = False
                self._credential_error = str(e)
                logger.warning(f"[Account] balance sync failed: {e}")

    # ── tick loop ───────────────────────────────────────
    async def on_tick(self, symbol: str, price: float, volume: float,
                      timestamp: float, is_buy: bool = True) -> None:
        self.signal_engine.record_tick(symbol, price, volume, timestamp, is_buy)
        self._record_price(symbol, price)
        self._tick_count += 1

        if self.paper_mode:
            self._check_paper_positions(symbol, price)
        elif bool(getattr(self.router, "live_trading_supported", False)):
            await self._check_live_managed_positions(symbol, price)

        # process agent signals every 10 ticks
        if self._tick_count % 10 == 0:
            regime, _ = await self.regime_service.get(symbol)
            await self._process_agents(symbol, price, regime=regime)

        # sync live positions every 30 ticks (run.py writes state separately)
        if (
            self._tick_count % 30 == 0
            and not self.paper_mode
            and bool(getattr(self.router, "uses_ticket_positions", False))
        ):
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

            strategy = self._agent_strategy(agent)
            agent.record_trade_result(pnl, pnl_pct)
            self.strategy_performance_guard.record(strategy, pnl)
            self.risk_guardian.on_position_closed(agent.dna.symbol, pnl)
            closed_entry = {
                "timestamp": time.time(),
                "agent": agent.dna.name,
                "symbol": symbol,
                "action": "CLOSE",
                "side": agent._open_side,
                "entry_price": agent._open_entry,
                "price": exit_price,
                "pnl": round(pnl, 2),
                "pnl_pct": round(pnl_pct, 4),
                "strategy": strategy,
                "timeframe": agent.dna.timeframe,
                "ticket": agent._open_ticket,
                "reason": "stop_loss" if sl_hit else "take_profit",
                "type": self.runtime_mode,
                "status": "closed",
            }
            self._order_history.insert(0, closed_entry)
            self._emit_trade_closed(closed_entry)
            self._trim_history()
            self._reset_agent(agent)

    async def _check_live_managed_positions(self, symbol: str, price: float):
        """Close Binance Spot positions owned by this manager at local SL/TP."""
        for agent in self.agents:
            if agent.dna.symbol != symbol or not agent.is_in_trade:
                continue
            if agent._open_side != "BUY":
                logger.error(
                    "[Spot] unmanaged side %s for %s; refusing automatic close",
                    agent._open_side,
                    symbol,
                )
                continue

            sl_hit = price <= agent._open_sl
            tp_hit = price >= agent._open_tp
            if not (sl_hit or tp_hit):
                continue

            try:
                result = await self.router.place_order(
                    symbol=symbol,
                    side="SELL",
                    qty=agent._open_qty,
                    comment=f"CX-CLOSE-{agent.dna.name}",
                )
            except Exception as e:
                logger.error(f"[Spot] close failed for {agent.dna.name}: {e}")
                continue

            exit_price = float(result.get("price") or price)
            qty = float(result.get("qty") or agent._open_qty)
            pnl = (exit_price - agent._open_entry) * qty
            pnl_pct = (pnl / self._account_balance) * 100 if self._account_balance else 0.0
            self._account_balance += pnl
            self._account_equity = self._account_balance

            strategy = self._agent_strategy(agent)
            agent.record_trade_result(pnl, pnl_pct)
            self.strategy_performance_guard.record(strategy, pnl)
            self.risk_guardian.on_position_closed(symbol, pnl)
            closed_entry = {
                "timestamp": time.time(),
                "agent": agent.dna.name,
                "symbol": symbol,
                "action": "CLOSE",
                "side": agent._open_side,
                "entry_price": agent._open_entry,
                "qty": qty,
                "volume": qty,
                "price": exit_price,
                "pnl": round(pnl, 2),
                "pnl_pct": round(pnl_pct, 4),
                "type": self.runtime_mode,
                "network": getattr(self.router, "network", "unknown"),
                "status": "closed",
                "ticket": result.get("ticket"),
                "reason": "stop_loss" if sl_hit else "take_profit",
                "strategy": strategy,
                "timeframe": agent.dna.timeframe,
            }
            self._order_history.insert(0, closed_entry)
            self._emit_trade_closed(closed_entry)
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
            closed_entry = {
                "timestamp": time.time(),
                "agent": agent.dna.name,
                "symbol": agent.dna.symbol,
                "action": "CLOSE",
                "side": agent._open_side,
                "entry_price": agent._open_entry,
                "price": self._latest_prices.get(agent.dna.symbol, {}).get("mid", 0.0),
                "qty": agent._open_qty,
                "volume": agent._open_qty,
                "pnl": 0.0,
                "pnl_pct": 0.0,
                "type": self.runtime_mode,
                "network": getattr(self.router, "network", "unknown"),
                "status": "closed",
                "ticket": agent._open_ticket,
                "reason": "external_close_pnl_unavailable",
                "strategy": self._agent_strategy(agent),
                "timeframe": agent.dna.timeframe,
            }
            agent.record_trade_result(0.0, 0.0)
            self.risk_guardian.on_position_closed(agent.dna.symbol, 0.0)
            self._order_history.insert(0, closed_entry)
            self._emit_trade_closed(closed_entry)
            self._trim_history()
            self._reset_agent(agent)

    async def _process_agents(self, symbol: str, price: float, regime: str = None):
        if self._manual_entries_paused:
            logger.warning(f"[Control] {symbol} entries paused: {self._manual_pause_reason or 'manual pause'}")
            self._audit_entry(
                symbol=symbol,
                stage="manual_pause",
                reason=self._manual_pause_reason or "manual pause",
            )
            return
        shadow_guard = self._shadow_guard_decision(symbol, regime)
        if not shadow_guard["allowed"]:
            self._log_blocked(
                f"shadow_guard:{symbol}:{shadow_guard['regime']}",
                f"[ShadowGuard] {symbol} entries blocked: {shadow_guard['reason']}",
            )
            self._audit_entry(
                symbol=symbol,
                stage="shadow_guard_policy",
                reason=shadow_guard["reason"],
                signal={
                    "regime": shadow_guard["regime"],
                    "source": shadow_guard["source"],
                    "policy_path": str(self._shadow_guard_policy_path),
                },
            )
            return
        idle = [a for a in self.agents if a.dna.symbol == symbol and not a.is_in_trade]
        today = int(time.time() / 86400)
        candidates = []
        guard_mode = self.strategy_performance_guard.guard_mode()
        if guard_mode == "HARD_STOP":
            logger.warning(f"[AdaptiveGuard] {symbol} entries blocked: HARD_STOP")
            self._audit_entry(symbol=symbol, stage="adaptive_guard", reason="HARD_STOP")
            return
        perf = self.pair_performance_guard.evaluate(symbol, "", self._order_history)
        if not perf.allowed:
            self._log_blocked(f"pair_perf:{symbol}", f"[PairPerfGuard] {symbol} blocked: {perf.reason}")
            self._audit_entry(symbol=symbol, stage="pair_performance", reason=perf.reason)
            return
        allowed_strategies = DEFENSE_STRATEGY_ALLOWLIST if guard_mode == "DEFENSE" else ENTRY_STRATEGY_ALLOWLIST
        for agent in idle:
            strategy = self._agent_strategy(agent)
            if allowed_strategies and strategy not in allowed_strategies:
                self._log_blocked(
                    f"allowlist:{symbol}:{strategy}",
                    f"[StrategyAllowlist] {symbol} {strategy} blocked; "
                    f"mode={guard_mode} allowed={sorted(allowed_strategies)}",
                )
                self._audit_entry(
                    symbol=symbol,
                    stage="strategy_allowlist",
                    reason=f"{strategy} not in {guard_mode} allowlist",
                    agent=agent,
                    strategy=strategy,
                )
                continue
            guard = self.strategy_performance_guard.evaluate(strategy)
            if not guard.allowed:
                self._log_blocked(
                    f"strategy_guard:{symbol}:{strategy}",
                    f"[StrategyGuard] {symbol} {strategy} blocked: "
                    f"{guard.reason}; cooldown={guard.cooldown_remaining_seconds}s",
                )
                self._audit_entry(
                    symbol=symbol,
                    stage="strategy_performance",
                    reason=guard.reason,
                    agent=agent,
                    strategy=strategy,
                )
                continue
            signal = self._signal_with_trend_context(agent, price, strategy, regime=regime)
            if signal["action"] == "HOLD" or signal["confidence"] < 50:
                self._audit_entry(
                    symbol=symbol,
                    stage="signal_hold" if signal["action"] == "HOLD" else "signal_confidence",
                    reason=signal.get("reason") or "signal below execution threshold",
                    agent=agent,
                    strategy=strategy,
                    action=signal.get("action"),
                    confidence=signal.get("confidence"),
                    signal=signal,
                )
                continue
            candidates.append((signal["confidence"], agent, signal, strategy))

        candidates.sort(key=lambda item: item[0], reverse=True)
        for _, agent, signal, strategy in candidates[:MAX_SIGNALS_PER_SYMBOL]:
            sl_pct, tp_pct = self._effective_sl_tp(agent, strategy)
            risk = self.risk_guardian.validate(
                symbol=symbol,
                action="BUY" if signal["action"] == "LONG" else "SELL",
                entry_price=price,
                sl_pct=sl_pct,
                tp_pct=tp_pct,
                account_balance=self._account_balance,
                account_equity=self._account_equity,
                current_day=today,
            )
            if not risk.allowed:
                logger.debug(f"[{agent.dna.name}] blocked: {risk.reason}")
                self._audit_entry(
                    symbol=symbol,
                    stage="risk_guardian",
                    reason=risk.reason,
                    agent=agent,
                    strategy=strategy,
                    action=signal.get("action"),
                    confidence=signal.get("confidence"),
                    signal=signal,
                )
                continue
            action = "BUY" if signal["action"] == "LONG" else "SELL"
            if action == "SELL" and not bool(getattr(self.router, "supports_short", True)):
                self._log_blocked(
                    f"spot_short:{symbol}",
                    f"[Spot] {symbol} SELL entry blocked: Binance Spot does not support short positions",
                )
                self._audit_entry(
                    symbol=symbol,
                    stage="spot_short_block",
                    reason="spot exchange does not support short positions",
                    agent=agent,
                    strategy=strategy,
                    action=signal.get("action"),
                    confidence=signal.get("confidence"),
                    signal=signal,
                )
                continue
            dedup = self.position_dedup_guard.evaluate(symbol, action, self.get_open_positions())
            if not dedup.allowed:
                self._log_blocked(f"dedup:{symbol}:{action}", f"[PositionDedup] {agent.dna.name} {symbol} {action} blocked: {dedup.reason}")
                self._audit_entry(
                    symbol=symbol,
                    stage="position_dedup",
                    reason=dedup.reason,
                    agent=agent,
                    strategy=strategy,
                    action=signal.get("action"),
                    confidence=signal.get("confidence"),
                    signal=signal,
                )
                continue
            if self.paper_mode:
                self._paper_execute(agent, signal, price, risk, strategy, sl_pct, tp_pct)
            else:
                if self._blocks_live_execution():
                    self._audit_entry(
                        symbol=symbol,
                        stage="signal_only_execution",
                        reason="live execution is locked by signal-only mode",
                        agent=agent,
                        strategy=strategy,
                        action=signal.get("action"),
                        confidence=signal.get("confidence"),
                        signal=signal,
                    )
                    self._record_signal_only_block(agent, signal, price, risk, strategy, sl_pct, tp_pct)
                    continue
                await self._live_execute(agent, signal, price, risk, strategy, sl_pct, tp_pct)

    def _shadow_guard_decision(self, symbol: str, regime: str = None) -> dict:
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

    def _load_shadow_guard_policy(self) -> dict:
        try:
            if not self._shadow_guard_policy_path.exists():
                return {}
            return json.loads(self._shadow_guard_policy_path.read_text())
        except Exception:
            logger.warning("Failed to load shadow guard policy: %s", self._shadow_guard_policy_path, exc_info=True)
            return {}

    @classmethod
    def _shadow_guard_blocked_regimes(cls, policy: dict) -> set:
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

    def _signal_with_trend_context(self, agent: CryptoAgent, price: float, strategy: str, regime: str = None) -> dict:
        signal = agent.generate_signal(price, markov_regime=regime)
        action = signal.get("action", "HOLD")
        symbol = agent.dna.symbol

        trend_action, trend_reason = self._htf_trend_action(symbol)
        if action in ("LONG", "SHORT"):
            block = self._countertrend_block(action, trend_action, trend_reason)
            if block:
                return block
            if action == trend_action:
                signal = dict(signal)
                signal["confidence"] = min(100, int(signal.get("confidence", 0)) + 15)
                signal["reason"] = f"{signal.get('reason', '')} | HTF aligned {trend_reason}"
            return signal

        if strategy in TREND_FOLLOW_STRATEGIES and trend_action:
            primary_ok = self._primary_allows_trend(symbol, agent.dna.timeframe, trend_action)
            if primary_ok:
                return {
                    "action": trend_action,
                    "confidence": 55,
                    "reason": f"Trend-follow fallback: {trend_reason}",
                }
        return signal

    def _paper_execute(
        self,
        agent: CryptoAgent,
        signal: dict,
        price: float,
        risk: RiskResult,
        strategy: str,
        sl_pct: float,
        tp_pct: float,
    ):
        action = "BUY" if signal["action"] == "LONG" else "SELL"
        agent._open_ticket = int(time.time() * 1000) + agent.dna.id
        agent._open_entry = price
        agent._open_side = action
        agent._open_sl = risk.sl_price
        agent._open_tp = risk.tp_price
        agent._open_qty = risk.qty
        agent._open_risk_amount = risk.risk_amount
        self.risk_guardian.on_position_opened(agent.dna.symbol)
        self.position_dedup_guard.record_open(agent.dna.symbol)
        self._order_history.insert(0, {
            "timestamp": time.time(),
            "agent": agent.dna.name,
            "symbol": agent.dna.symbol,
            "action": action,
            "qty": round(risk.qty, 6),
            "volume": round(risk.qty, 6),
            "price": price,
            "sl": risk.sl_price,
            "tp": risk.tp_price,
            "strategy": strategy,
            "timeframe": agent.dna.timeframe,
            "sl_pct": sl_pct,
            "tp_pct": tp_pct,
            "pnl": 0.0,
            "pnl_pct": 0.0,
            "type": self.runtime_mode,
            "status": "open",
            "ticket": agent._open_ticket,
        })
        self._trim_history()

    async def _live_execute(
        self,
        agent: CryptoAgent,
        signal: dict,
        price: float,
        risk: RiskResult,
        strategy: str,
        sl_pct: float,
        tp_pct: float,
    ):
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
        self.risk_guardian.on_position_opened(agent.dna.symbol)
        self.position_dedup_guard.record_open(agent.dna.symbol)
        self._order_history.insert(0, {
            "timestamp": time.time(),
            "agent": agent.dna.name,
            "symbol": agent.dna.symbol,
            "action": action,
            "qty": round(risk.qty, 6),
            "volume": round(risk.qty, 6),
            "price": agent._open_entry,
            "sl": risk.sl_price,
            "tp": risk.tp_price,
            "strategy": strategy,
            "timeframe": agent.dna.timeframe,
            "sl_pct": sl_pct,
            "tp_pct": tp_pct,
            "pnl": 0.0,
            "pnl_pct": 0.0,
            "type": self.runtime_mode,
            "network": getattr(self.router, "network", "unknown"),
            "status": result.get("status", "placed"),
            "ticket": agent._open_ticket,
        })
        self._trim_history()

    def _blocks_live_execution(self) -> bool:
        if self.paper_mode:
            return False
        if FORCE_SIGNAL_ONLY:
            return True
        if not SIGNAL_ONLY_EXECUTION_ENABLED:
            return False
        return not (
            bool(getattr(self.router, "live_trading_supported", False))
            and self._credential_verified
        )

    def _execution_mode(self) -> str:
        if self.paper_mode:
            return self.runtime_mode
        if self._blocks_live_execution():
            return "signal_only"
        return "testnet" if self.runtime_mode == "demo" else "live"

    def _record_signal_only_block(
        self,
        agent: CryptoAgent,
        signal: dict,
        price: float,
        risk: RiskResult,
        strategy: str,
        sl_pct: float,
        tp_pct: float,
    ) -> None:
        action = "BUY" if signal["action"] == "LONG" else "SELL"
        reason = f"{self._exchange_name} live order placement is not enabled"
        key = f"signal_only:{agent.dna.symbol}:{action}:{agent.dna.name}"
        self._log_blocked(
            key,
            f"[SignalOnly] {agent.dna.name} {agent.dna.symbol} {action} blocked: {reason}",
        )

        now = time.time()
        last = self._last_signal_only_record.get(key, 0.0)
        if now - last < SIGNAL_ONLY_HISTORY_INTERVAL_SECONDS:
            return
        self._last_signal_only_record[key] = now
        self._order_history.insert(0, {
            "timestamp": now,
            "agent": agent.dna.name,
            "symbol": agent.dna.symbol,
            "action": action,
            "qty": round(risk.qty, 6),
            "volume": round(risk.qty, 6),
            "price": price,
            "sl": risk.sl_price,
            "tp": risk.tp_price,
            "strategy": strategy,
            "timeframe": agent.dna.timeframe,
            "sl_pct": sl_pct,
            "tp_pct": tp_pct,
            "pnl": 0.0,
            "pnl_pct": 0.0,
            "type": "signal_only",
            "status": "blocked",
            "reason": reason,
            "signal": dict(signal),
        })
        self._trim_history()

    def _run_evolution(self):
        logger.info("[Evolution] starting cycle")
        if any(agent.is_in_trade for agent in self.agents):
            logger.info("[Evolution] deferred while positions are open")
            return
        # Release positions held by the outgoing agents so the risk guardian's
        # open-position counter does not leak. The new agent objects start flat,
        # so a stale counter would permanently block trading at the
        # MAX_CONCURRENT_POSITIONS limit.
        released = 0
        for agent in self.agents:
            if agent.is_in_trade:
                self.risk_guardian.on_position_closed(agent.dna.symbol, 0.0)
                released += 1
        if released:
            logger.warning(f"[Evolution] released {released} open positions before rebuild")
        stats = [a.to_dict() for a in self.agents]
        runtime_by_id = {a.dna.id: a.runtime_state() for a in self.agents}
        dnas = [a.dna for a in self.agents]
        new_dnas, self._next_agent_id = evolve(dnas, stats, self._next_agent_id, pairs=self._pairs)
        self.agents = [
            CryptoAgent(dna, self.signal_engine, self.risk_guardian, self.paper_mode)
            for dna in new_dnas
        ]
        for agent in self.agents:
            previous = runtime_by_id.get(agent.dna.id)
            if previous:
                agent.restore_runtime_state(previous)
        logger.info(f"[Evolution] done — {len(self.agents)} agents")

    def runtime_state(self) -> dict:
        return {
            "version": 2,
            "saved_at": time.time(),
            "runtime_mode": self.runtime_mode,
            "network": getattr(self.router, "network", "paper"),
            "pairs": list(self._pairs),
            "account": {
                "balance": self._account_balance,
                "equity": self._account_equity,
                "initial_capital": self._initial_capital,
            },
            "next_agent_id": self._next_agent_id,
            "agents": [agent.runtime_state() for agent in self.agents],
            "order_history": self._order_history[:500],
        }

    def restore_runtime_state(self, state: dict) -> bool:
        if not state or state.get("version") != 2:
            return False
        if state.get("runtime_mode") != self.runtime_mode:
            return False
        if state.get("network") != getattr(self.router, "network", "paper"):
            return False
        from engine.dna import CryptoAgentDNA

        restored = []
        for item in state.get("agents") or []:
            raw = item.get("dna") or {}
            try:
                dna = CryptoAgentDNA(
                    id=int(raw["id"]),
                    name=str(raw["name"]),
                    symbol=str(raw["symbol"]),
                    strategy_weights=dict(raw["strategy_weights"]),
                    sl_pct=float(raw["sl_pct"]),
                    tp_pct=float(raw["tp_pct"]),
                    risk_pct=float(raw.get("risk_pct", 0.01)),
                    timeframe=str(raw.get("timeframe", "M15")),
                    regime_bias=str(raw.get("regime_bias", "any")),
                )
            except (KeyError, TypeError, ValueError):
                continue
            agent = CryptoAgent(dna, self.signal_engine, self.risk_guardian, self.paper_mode)
            agent.restore_runtime_state(item)
            restored.append(agent)
        allowed_pairs = set(DEFAULT_PAIRS)
        restored = [agent for agent in restored if agent.dna.symbol in allowed_pairs]
        if not restored:
            return False

        self.agents = restored
        state_pairs = [p for p in (state.get("pairs") or sorted({a.dna.symbol for a in restored})) if p in allowed_pairs]
        self._pairs = state_pairs or list(DEFAULT_PAIRS)
        account = state.get("account") or {}
        self._account_balance = float(account.get("balance", 1000.0))
        self._account_equity = float(account.get("equity", self._account_balance))
        self._initial_capital = float(account.get("initial_capital", 1000.0))
        self._next_agent_id = int(state.get("next_agent_id", max(a.dna.id for a in restored) + 1))
        self._order_history = list(state.get("order_history") or [])[:500]
        for agent in self.agents:
            if agent.is_in_trade:
                self.risk_guardian.on_position_opened(agent.dna.symbol)
                self.position_dedup_guard.record_open(agent.dna.symbol)
        logger.info(
            "[State] restored %s agents, %s open positions, balance=%.2f",
            len(self.agents),
            sum(1 for agent in self.agents if agent.is_in_trade),
            self._account_balance,
        )
        return True

    def get_open_positions(self) -> list[dict]:
        """Open paper positions, shaped for the dashboard order book.

        Paper trades live on the agents (the exchange feed has none in paper
        mode), so the /api/positions route must read them from here.
        """
        positions = []
        for agent in self.agents:
            if not agent.is_in_trade:
                continue
            symbol = agent.dna.symbol
            current = self._latest_prices.get(symbol, {}).get("mid", agent._open_entry)
            direction = 1 if agent._open_side == "BUY" else -1
            profit = (current - agent._open_entry) * direction * agent._open_qty
            positions.append({
                "ticket": agent._open_ticket,
                "symbol": symbol,
                "type": agent._open_side,
                "volume": round(agent._open_qty, 6),
                "price_open": round(agent._open_entry, 4),
                "price_current": round(current, 4),
                "profit": round(profit, 2),
                "sl": round(agent._open_sl, 4),
                "tp": round(agent._open_tp, 4),
            })
        return positions

    def control_status(self) -> dict:
        return {
            "entries_paused": self._manual_entries_paused,
            "pause_reason": self._manual_pause_reason,
            "paper_mode": self.paper_mode,
            "execution_mode": self._execution_mode(),
            "live_trading_supported": bool(getattr(self.router, "live_trading_supported", False)),
            "signal_only_execution": self._blocks_live_execution(),
            "network": getattr(self.router, "network", "paper"),
            "credential_status": getattr(self.router, "credential_status", "not_supported"),
            "credential_verified": self._credential_verified,
            "credential_error": self._credential_error,
            "supports_short": bool(getattr(self.router, "supports_short", True)),
            "open_positions": len(self.get_open_positions()),
            "guard_mode": self.strategy_performance_guard.guard_mode(),
            "mads_defensive_policy": self.risk_guardian.external_policy(),
        }

    def set_risk_policy(self, mode: str, risk_scale: float, max_positions: int) -> dict:
        policy = self.risk_guardian.set_external_policy(mode, risk_scale, max_positions)
        if policy["risk_scale"] <= 0 or policy["max_positions"] <= 0:
            self.pause_entries(f"MADS {policy['mode']} defensive policy")
        logger.warning(f"[Control] MADS defensive policy applied: {policy}")
        return self.control_status()

    def pause_entries(self, reason: str = "manual control") -> dict:
        self._manual_entries_paused = True
        self._manual_pause_reason = reason or "manual control"
        logger.warning(f"[Control] entries paused: {self._manual_pause_reason}")
        return self.control_status()

    def resume_entries(self) -> dict:
        self._manual_entries_paused = False
        self._manual_pause_reason = ""
        logger.warning("[Control] entries resumed")
        return self.control_status()

    def close_paper_position(self, ticket: int, reason: str = "manual control") -> dict:
        ticket = int(ticket)
        for agent in self.agents:
            if not agent.is_in_trade or int(agent._open_ticket or 0) != ticket:
                continue
            symbol = agent.dna.symbol
            current = self._latest_prices.get(symbol, {}).get("mid", agent._open_entry)
            direction = 1 if agent._open_side == "BUY" else -1
            pnl = (current - agent._open_entry) * direction * agent._open_qty
            pnl_pct = (pnl / self._account_balance) * 100 if self._account_balance else 0.0
            strategy = self._agent_strategy(agent)

            self._account_balance += pnl
            self._account_equity = self._account_balance
            agent.record_trade_result(pnl, pnl_pct)
            self.strategy_performance_guard.record(strategy, pnl)
            self.risk_guardian.on_position_closed(symbol, pnl)
            closed_entry = {
                "timestamp": time.time(),
                "agent": agent.dna.name,
                "symbol": symbol,
                "action": "CLOSE",
                "side": agent._open_side,
                "entry_price": agent._open_entry,
                "price": current,
                "pnl": round(pnl, 2),
                "pnl_pct": round(pnl_pct, 4),
                "type": self.runtime_mode,
                "status": "closed",
                "ticket": ticket,
                "reason": reason,
                "strategy": strategy,
                "timeframe": agent.dna.timeframe,
            }
            self._order_history.insert(0, closed_entry)
            self._emit_trade_closed(closed_entry)
            self._trim_history()
            self._reset_agent(agent)
            logger.warning(f"[Control] closed paper position ticket={ticket} pnl={pnl:.2f} reason={reason}")
            return {"closed": True, "ticket": ticket, "symbol": symbol, "pnl": round(pnl, 2)}
        return {"closed": False, "ticket": ticket, "error": "paper position not found"}

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

    def _emit_trade_closed(self, trade: dict):
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

    def _log_blocked(self, key: str, message: str):
        now = time.time()
        last = self._last_block_log.get(key, 0.0)
        if now - last >= BLOCK_LOG_INTERVAL_SECONDS:
            self._last_block_log[key] = now
            logger.warning(message)

    def _audit_entry(
        self,
        *,
        symbol: str,
        stage: str,
        reason: str,
        agent: CryptoAgent = None,
        strategy: str = "",
        action: str = "",
        confidence: float = None,
        signal: dict = None,
    ) -> None:
        row = {
            "timestamp": time.time(),
            "symbol": symbol,
            "block_stage": stage,
            "reason": reason or "unknown",
        }
        if agent is not None:
            row.update(
                {
                    "agent": agent.dna.name,
                    "timeframe": agent.dna.timeframe,
                    "strategy": strategy or self._agent_strategy(agent),
                }
            )
        if action:
            row["action"] = action
        if confidence is not None:
            row["confidence"] = confidence
        if signal:
            row["signal"] = dict(signal)
        self._entry_audit.insert(0, row)
        if len(self._entry_audit) > 1000:
            self._entry_audit = self._entry_audit[:1000]

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

    def _open_pnl_by_ticket(self) -> dict:
        floating = {}
        for agent in self.agents:
            if not agent.is_in_trade:
                continue
            current = self._latest_prices.get(agent.dna.symbol, {}).get("mid")
            if current is None:
                continue
            direction = 1 if agent._open_side == "BUY" else -1
            pnl = (current - agent._open_entry) * direction * agent._open_qty
            pnl_pct = (pnl / self._account_balance) * 100 if self._account_balance else 0.0
            floating[agent._open_ticket] = {
                "pnl": round(pnl, 2),
                "pnl_pct": round(pnl_pct, 4),
                "price_current": round(current, 4),
            }
        return floating

    def _history_for_state(self) -> list[dict]:
        floating = self._open_pnl_by_ticket()
        out = []
        for row in self._order_history[:200]:
            item = dict(row)
            if item.get("status") == "open" and item.get("ticket") in floating:
                item.update(floating[item["ticket"]])
            out.append(item)
        return out

    def _signal_quality_summary(self) -> Dict:
        cutoff = time.time() - 86400
        rows = [
            dict(item)
            for item in self._order_history
            if str(item.get("type") or "").lower() == "signal_only"
            and float(item.get("timestamp") or 0.0) >= cutoff
        ]
        by_symbol: Dict[str, int] = {}
        by_strategy: Dict[str, int] = {}
        by_action: Dict[str, int] = {}
        by_reason: Dict[str, int] = {}
        for row in rows:
            symbol = str(row.get("symbol") or "UNKNOWN")
            strategy = str(row.get("strategy") or "unknown")
            action = str(row.get("action") or "unknown")
            reason = str(row.get("reason") or "unknown")
            by_symbol[symbol] = by_symbol.get(symbol, 0) + 1
            by_strategy[strategy] = by_strategy.get(strategy, 0) + 1
            by_action[action] = by_action.get(action, 0) + 1
            by_reason[reason] = by_reason.get(reason, 0) + 1
        audit_rows = [
            dict(item)
            for item in self._entry_audit
            if float(item.get("timestamp") or 0.0) >= cutoff
        ]
        by_block_stage: Dict[str, int] = {}
        audit_by_symbol: Dict[str, int] = {}
        audit_by_strategy: Dict[str, int] = {}
        for row in audit_rows:
            stage = str(row.get("block_stage") or "unknown")
            symbol = str(row.get("symbol") or "UNKNOWN")
            strategy = str(row.get("strategy") or "unknown")
            by_block_stage[stage] = by_block_stage.get(stage, 0) + 1
            audit_by_symbol[symbol] = audit_by_symbol.get(symbol, 0) + 1
            audit_by_strategy[strategy] = audit_by_strategy.get(strategy, 0) + 1
        min_forward_samples = int(os.getenv("CRYPTO_SIGNAL_QUALITY_MIN_FORWARD_SAMPLES", "20"))
        return {
            "mode": "signal_only_forward_test",
            "window_hours": 24,
            "audit_events": len(audit_rows),
            "signal_only_candidates": len(rows),
            "by_block_stage": by_block_stage,
            "by_symbol": by_symbol,
            "by_strategy": by_strategy,
            "by_action": by_action,
            "by_reason": by_reason,
            "audit_by_symbol": audit_by_symbol,
            "audit_by_strategy": audit_by_strategy,
            "min_forward_samples": min_forward_samples,
            "ready_for_execution": False,
            "reason": (
                "execution locked until forward signal sample reaches "
                f"{min_forward_samples} and expectancy review is positive"
            ),
        }

    @staticmethod
    def _agent_strategy(agent: CryptoAgent) -> str:
        return max(agent.dna.strategy_weights, key=lambda k: agent.dna.strategy_weights[k])

    def _htf_trend_action(self, symbol: str) -> tuple[Optional[str], str]:
        trends = []
        for tf in ("H1", "H4"):
            trend = self.signal_engine.get_history(symbol, tf).it_trend()
            if trend in ("up", "down"):
                trends.append((tf, trend))
        if len(trends) < 2:
            return None, ""
        trend_values = {trend for _, trend in trends}
        if trend_values == {"down"}:
            return "SHORT", ", ".join(f"{tf}:{trend}" for tf, trend in trends)
        if trend_values == {"up"}:
            return "LONG", ", ".join(f"{tf}:{trend}" for tf, trend in trends)
        return None, ", ".join(f"{tf}:{trend}" for tf, trend in trends)

    @staticmethod
    def _countertrend_block(action: str, trend_action: Optional[str], trend_reason: str) -> Optional[dict]:
        if not trend_action or action == trend_action:
            return None
        return {
            "action": "HOLD",
            "confidence": 0,
            "reason": f"HTF trend guard: {action} blocked by {trend_reason}",
        }

    def _primary_allows_trend(self, symbol: str, timeframe: str, trend_action: str) -> bool:
        trend = self.signal_engine.get_history(symbol, timeframe).it_trend()
        if trend not in ("up", "down"):
            return True
        if trend_action == "SHORT":
            return trend != "up"
        return trend != "down"

    def _effective_sl_tp(self, agent: CryptoAgent, strategy: str) -> tuple[float, float]:
        sl_pct = float(agent.dna.sl_pct)
        tp_pct = float(agent.dna.tp_pct)

        caps = STRATEGY_RISK_CAPS.get(strategy, {})
        if "sl" in caps:
            sl_pct = min(sl_pct, caps["sl"])
        tf_sl_cap = TIMEFRAME_SL_CAPS.get(agent.dna.timeframe)
        if tf_sl_cap is not None:
            sl_pct = min(sl_pct, tf_sl_cap)

        atr_pct = self._atr_sl_pct(agent, strategy)
        if atr_pct is not None:
            sl_pct = min(sl_pct, atr_pct)
        sl_pct = max(MIN_EFFECTIVE_SL_PCT, sl_pct)

        if "tp" in caps:
            tp_pct = min(tp_pct, caps["tp"])

        tf_cap = TIMEFRAME_TP_CAPS.get(agent.dna.timeframe)
        if tf_cap is not None:
            tp_pct = min(tp_pct, tf_cap)

        tp_pct = max(tp_pct, sl_pct * MIN_RR_RATIO)
        return round(sl_pct, 4), round(tp_pct, 4)

    def _atr_sl_pct(self, agent: CryptoAgent, strategy: str) -> Optional[float]:
        hist = self.signal_engine.get_history(agent.dna.symbol, agent.dna.timeframe)
        atr_pct = hist.atr_percent(14)
        if atr_pct is None:
            return None
        mult = STRATEGY_RISK_CAPS.get(strategy, {}).get("atr", 1.2)
        return max(MIN_EFFECTIVE_SL_PCT, (atr_pct / 100.0) * mult)

    def _trade_recommendations(self) -> Dict:
        min_confidence = int(os.getenv("CRYPTO_RECOMMENDATION_MIN_CONFIDENCE", "55"))
        strategies = [
            item for item in ("market_structure", "momentum", "breakout_atr")
            if not ENTRY_STRATEGY_ALLOWLIST or item in ENTRY_STRATEGY_ALLOWLIST
        ]
        if not strategies:
            strategies = ["market_structure", "momentum"]
        signal_methods = {
            "market_structure": self.signal_engine.market_structure_signal,
            "momentum": self.signal_engine.technical_signal,
            "breakout_atr": self.signal_engine.breakout_atr_signal,
        }
        symbols = []
        all_candidates = []
        for symbol in self._pairs:
            trend_action, trend_reason = self._htf_trend_action(symbol)
            symbol_candidates = []
            scanned = 0
            for timeframe in TIMEFRAMES:
                hist = self.signal_engine.get_history(symbol, timeframe)
                if hist.count < 20:
                    continue
                scanned += 1
                for strategy in strategies:
                    method = signal_methods.get(strategy)
                    if method is None:
                        continue
                    signal = dict(method(symbol, timeframe))
                    action = str(signal.get("action") or "HOLD")
                    confidence = int(signal.get("confidence") or 0)
                    reason = signal.get("reason") or "no reason"
                    if action == "HOLD" or confidence < min_confidence:
                        continue
                    if trend_action and action != trend_action:
                        continue
                    executable = not (action == "SHORT" and not bool(getattr(self.router, "supports_short", True)))
                    candidate = {
                        "symbol": symbol,
                        "action": "BUY" if action == "LONG" else "SELL",
                        "signal_action": action,
                        "timeframe": timeframe,
                        "strategy": strategy,
                        "confidence": confidence,
                        "reason": reason,
                        "higher_timeframe_filter": trend_reason or "HTF trend not confirmed",
                        "execution_mode": self._execution_mode(),
                        "executable": executable,
                    }
                    if not executable:
                        candidate["execution_note"] = "spot exchange does not support short positions"
                    symbol_candidates.append(candidate)
                    all_candidates.append(candidate)
            best = sorted(
                symbol_candidates,
                key=lambda item: (item.get("executable", False), item["confidence"]),
                reverse=True,
            )[:3]
            symbols.append({
                "symbol": symbol,
                "scanned_timeframes": scanned,
                "best": best[0] if best else None,
                "alternatives": best[1:],
                "status": "candidate_found" if best else "no_signal",
                "message": (
                    "candidate found; execution remains locked by signal-only mode"
                    if best else "no signal found across available timeframes"
                ),
            })
        best_overall = sorted(
            all_candidates,
            key=lambda item: (item.get("executable", False), item["confidence"]),
            reverse=True,
        )[:5]
        return {
            "mode": "advisory",
            "min_confidence": min_confidence,
            "ready_for_execution": False,
            "best_overall": best_overall,
            "symbols": symbols,
            "message": (
                "no signal found in any timeframe"
                if not best_overall else
                "recommendations are advisory; live execution is locked until forward review passes"
            ),
        }

    # ── state export ────────────────────────────────────
    def to_state_dict(self) -> dict:
        agent_entries = [a.to_dict() for a in self.agents]
        total_trades = sum(a.trades_count for a in self.agents)
        winners = sum(a.wins for a in self.agents)
        losers = sum(a.losses for a in self.agents)
        open_positions = sum(1 for a in self.agents if a.is_in_trade)
        total_pnl = sum(a.total_pnl for a in self.agents)
        total_pnl_pct = round(total_pnl / self._initial_capital * 100, 2) if self._initial_capital else 0.0

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
            "mode": self.runtime_mode,
            "execution_mode": self._execution_mode(),
            "live_trading_supported": bool(getattr(self.router, "live_trading_supported", False)),
            "network": getattr(self.router, "network", "paper"),
            "credential_status": getattr(self.router, "credential_status", "not_supported"),
            "credential_verified": self._credential_verified,
            "supports_short": bool(getattr(self.router, "supports_short", True)),
            "total_agents": len(self.agents),
            "pairs": list(self._pairs),
            "strategy_performance_guard": self.strategy_performance_guard.summary(),
            "regime_service": self.regime_service.summary(),
            "signal_quality": self._signal_quality_summary(),
            "trade_recommendations": self._trade_recommendations(),
            "control": self.control_status(),
        }

        return {
            "summary": summary,
            "agents": agent_entries,
            "prices": self._latest_prices,
            "order_history": self._history_for_state(),
        }
