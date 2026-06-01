from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from json import JSONDecodeError
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

    def __init__(self, url: str = None, timeout: int = None, retries: int = None, model: str = None):
        import os
        # 9Router exposes an OpenAI-compatible API at /v1/chat/completions.
        # HERMES_URL can still point directly to a chat endpoint; otherwise use
        # NINEROUTER_URL as the gateway base URL.
        gateway = os.getenv("NINEROUTER_URL", "http://127.0.0.1:20128").rstrip("/")
        self.url = url or os.getenv("HERMES_URL", f"{gateway}/v1/chat/completions")
        self.model = model or os.getenv("HERMES_MODEL") or os.getenv("NINEROUTER_MODEL", "FreeCombo")
        self.api_key = os.getenv("NINEROUTER_KEY", "")
        self.timeout = timeout if timeout is not None else int(os.getenv("LLM_TIMEOUT_SECONDS", "30"))
        self.retries = retries if retries is not None else int(os.getenv("LLM_RETRIES", "3"))

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
        winner_config = payload.get("winner_config", {})
        lines = [
            f"Symbol: {payload.get('symbol', 'UNKNOWN')}",
            f"Selected winner idx: {payload.get('winner_idx', 'UNKNOWN')}",
            f"Best forward PnL: {payload.get('forward_pnl', 0):.4f}",
            f"Winner strategy_weights: {json.dumps(winner_config, sort_keys=True)}",
            "",
            "Forward-test results for top-3 strategies over 15 minutes of live trading:",
        ]
        if results:
            for r in results:
                lines.append(
                    f"  idx={r.get('idx', 'N/A')} pnl={r.get('pnl', 0):.4f} "
                    f"max_dd={r.get('max_drawdown', 0):.4f} trades={r.get('trade_count', 0)} "
                    f"pnl_pct={r.get('pnl_pct', 0):.4f}"
                )
        else:
            lines.append(f"  aggregate_pnl={payload.get('forward_pnl', 0):.4f}")
        lines += [
            "",
            "Should we apply the winner strategy to the production agent?",
            "Consider: is the PnL positive? Is max_drawdown acceptable (<2%)?",
            "Use winner strategy_weights as apply_config unless there is a clear risk reason to reject.",
            'Respond with only valid JSON: {"approved": bool, "apply_config": {strategy_weights dict}, "reason": str}',
        ]
        return "\n".join(lines)

    async def select_winner(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        prompt = self._build_select_prompt(payload)
        request_body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "Return only one valid JSON object. No prose, markdown, or thinking."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
            "stream": False,
        }
        raw = await asyncio.to_thread(self._post_with_retries, request_body)
        content = raw.get("choices", [{}])[0].get("message", {}).get("content", "{}")
        parsed = _loads_first_json_object(content)
        if parsed is not None:
            return parsed
        raise HermesError(f"No JSON in Hermes response: {content[:200]}")

    async def verify_forward_test(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        prompt = self._build_verify_prompt(payload)
        request_body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "Return only one valid JSON object. No prose, markdown, or thinking."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
            "stream": False,
        }
        raw = await asyncio.to_thread(self._post_with_retries, request_body)
        content = raw.get("choices", [{}])[0].get("message", {}).get("content", "{}")
        parsed = _loads_first_json_object(content)
        if parsed is not None:
            return parsed
        raise HermesError(f"No JSON in Hermes response: {content[:200]}")

    def _post_with_retries(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        last_exc = None
        backoff = 0.5
        for attempt in range(1, self.retries + 1):
            try:
                return self._post_json(self.url, payload, timeout=self.timeout)
            except (TimeoutError, error.URLError, error.HTTPError, JSONDecodeError) as e:
                last_exc = e
                logger.warning("Hermes request attempt %d failed: %s", attempt, e)
                time.sleep(backoff)
                backoff *= 2
        raise HermesError(f"Hermes unreachable after {self.retries} attempts: {last_exc}")

    def _post_json(self, url: str, payload: Dict[str, Any], timeout: int = 5) -> Dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = request.Request(url, data=data, headers=headers)
        with request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            text = body.decode("utf-8")
            try:
                return json.loads(text)
            except JSONDecodeError:
                logger.warning("Hermes returned non-JSON response: %s", text[:500])
                raise


def _loads_first_json_object(content: str) -> Dict[str, Any] | None:
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", content):
        try:
            obj, _ = decoder.raw_decode(content[match.start():])
        except JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return None
