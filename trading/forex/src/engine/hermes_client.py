from __future__ import annotations

import asyncio
import json
import logging
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

    async def select_winner(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        resp = await asyncio.to_thread(self._post_with_retries, payload)
        # basic validation
        if not isinstance(resp, dict):
            raise HermesError("Invalid response type from Hermes")
        return resp

    async def verify_forward_test(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        resp = await asyncio.to_thread(self._post_with_retries, payload)
        if not isinstance(resp, dict):
            raise HermesError("Invalid response type from Hermes")
        return resp

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

