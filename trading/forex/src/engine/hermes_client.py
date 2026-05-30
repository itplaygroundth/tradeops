from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any, Dict
from urllib import error, request

logger = logging.getLogger(__name__)


class HermesError(RuntimeError):
    pass


class HermesClient:
    """Hermes REST client with retries and validation.

    Methods are async and will offload blocking HTTP calls to a thread.
    On repeated network failures a `HermesError` is raised so callers can
    implement fallback logic (e.g., use top-sharpe result).
    """

    def __init__(self, url: str = "http://127.0.0.1:20128/v1/chat/completions", timeout: int = 5, retries: int = 3):
        self.url = url
        self.timeout = timeout
        self.retries = retries

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
        content = raw.get("choices", [{}])[0].get("message", {}).get("content", "{}")
        m = re.search(r"\{.*\}", content, re.DOTALL)
        if m:
            return json.loads(m.group())
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
        m = re.search(r"\{.*\}", content, re.DOTALL)
        if m:
            return json.loads(m.group())
        raise HermesError(f"No JSON in Hermes response: {content[:200]}")

    def _post_with_retries(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        last_exc = None
        backoff = 0.5
        for attempt in range(1, self.retries + 1):
            try:
                return self._post_json(self.url, payload, timeout=self.timeout)
            except error.URLError as e:
                last_exc = e
                logger.warning("Hermes request attempt %d failed: %s", attempt, e)
                time.sleep(backoff)
                backoff *= 2
        raise HermesError(f"Hermes unreachable after {self.retries} attempts: {last_exc}")

    def _post_json(self, url: str, payload: Dict[str, Any], timeout: int = 5) -> Dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            return json.loads(body.decode("utf-8"))

