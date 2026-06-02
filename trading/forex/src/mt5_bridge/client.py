"""
MT5 Client — Contacts the MT5 API Server running on Windows.
Replaces ccxt.binance() from the crypto version.
"""
import httpx
import logging
import os
from typing import List, Dict, Optional
from dataclasses import dataclass

logger = logging.getLogger("mt5_client")

# ── Default Config ──────────────────────────────────────────────
MT5_SERVER_URL = "http://127.0.0.1:8888"  # Fallback URL

@dataclass
class Tick:
    symbol: str
    bid: float
    ask: float
    mid: float
    timestamp: float

class MT5Client:
    def __init__(self, server_url: str = MT5_SERVER_URL):
        self.url = server_url
        self._client = httpx.AsyncClient(timeout=15.0, base_url=server_url)
        # Honor environment override to prevent sending real orders
        self.disable_orders = str(os.getenv("DISABLE_ORDERS", "")).lower() in ("1", "true", "yes")

    async def _get_json(self, path: str) -> Optional[dict]:
        r = await self._client.get(path)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    async def health(self) -> dict:
        data = await self._get_json("/health")
        if data is not None:
            return data
        data = await self._get_json("/balance")
        if data is not None:
            return data
        raise RuntimeError("Neither /health nor /balance endpoint is available on MT5 bridge")

    async def get_account(self) -> dict:
        data = await self._get_json("/account")
        if data is not None:
            return data
        data = await self._get_json("/balance")
        if data is None:
            raise RuntimeError("Neither /account nor /balance endpoint is available on MT5 bridge")
        return {
            "login": 0,
            "balance": float(data.get("balance", 0.0)),
            "equity": float(data.get("equity", data.get("balance", 0.0))),
            "margin": 0.0,
            "margin_free": 0.0,
            "profit": 0.0,
            "leverage": 0,
            "currency": data.get("currency", "USD"),
        }

    async def get_price(self, symbol: str) -> Tick:
        r = await self._client.get(f"/price/{symbol}")
        r.raise_for_status()
        d = r.json()
        return Tick(
            symbol=symbol,
            bid=d["bid"],
            ask=d["ask"],
            mid=(d["bid"] + d["ask"]) / 2,
            timestamp=d["time"],
        )

    async def get_ohlcv(self, symbol: str, timeframe: str = "M15", count: int = 200) -> List[dict]:
        r = await self._client.get(f"/ohlcv/{symbol}", params={"timeframe": timeframe, "count": count})
        r.raise_for_status()
        return r.json()

    async def get_recent_deals(self, hours: int = 24, limit: int = 200) -> List[dict]:
        """Fetch recent deal history from the MT5 bridge."""
        try:
            r = await self._client.get("/history/recent", params={"hours": hours, "limit": limit})
            r.raise_for_status()
            return r.json().get("deals", [])
        except Exception as e:
            logger.warning(f"Failed to fetch recent deals: {e}")
            return []

    async def place_order(self, symbol: str, action: str, volume: float,
                          sl: float = 0, tp: float = 0, comment: str = "MTAI", magic: int = 20260101) -> dict:
        payload = {
            "symbol": symbol,
            "action": action,
            "volume": volume,
            "sl": sl,
            "tp": tp,
            "comment": comment,
            "magic": magic,
        }
        if getattr(self, "disable_orders", False):
            logger.info("Orders disabled via DISABLE_ORDERS; skipping place_order: %s %s %s", symbol, action, volume)
            # Return a simulated response indicating the order was skipped
            return {"status": "skipped", "reason": "orders_disabled", "payload": payload}
        logger.info("Placing order payload: %s", payload)
        try:
            r = await self._client.post("/order", json=payload)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as e:
            # Log response body for diagnostics
            try:
                text = e.response.text
            except Exception:
                text = "<no response body>"
            logger.error("Order HTTP error: status=%s body=%s", getattr(e.response, 'status_code', None), text)
            raise
        except Exception:
            raise

    async def get_positions(self) -> List[dict]:
        r = await self._client.get("/positions")
        r.raise_for_status()
        return r.json()["positions"]

    async def get_deal_history(self, ticket: int) -> dict:
        r = await self._client.get(f"/history/deal/{ticket}")
        r.raise_for_status()
        return r.json()

    async def close_position(self, ticket: int) -> dict:
        r = await self._client.delete(f"/position/{ticket}")
        r.raise_for_status()
        return r.json()

    async def modify_position(self, ticket: int, sl: float = 0, tp: float = 0) -> dict:
        r = await self._client.patch(f"/position/{ticket}", json={"sl": sl, "tp": tp})
        r.raise_for_status()
        return r.json()

    async def close(self):
        await self._client.aclose()
