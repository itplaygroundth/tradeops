"""Durable, non-blocking delivery of trading lifecycle events."""

import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger("trade_event_outbox")


class TradeEventOutbox:
    def __init__(self, engine_id: str, db_path: Path):
        self.engine_id = engine_id
        self.db_path = Path(db_path)
        self.control_url = os.getenv(
            "CONTROL_TRADE_EVENT_URL",
            "http://127.0.0.1:5001/api/trading/events",
        )
        self.retry_seconds = max(1.0, float(os.getenv("TRADE_EVENT_RETRY_SECONDS", "5")))
        self._wake = threading.Event()
        self._init_db()
        self._thread = threading.Thread(
            target=self._run,
            name=f"{engine_id}-trade-events",
            daemon=True,
        )
        self._thread.start()

    def _connect(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(self.db_path), timeout=5)
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _init_db(self):
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS trade_event_outbox (
                    event_id TEXT PRIMARY KEY,
                    created_at REAL NOT NULL,
                    event_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at REAL NOT NULL DEFAULT 0,
                    delivered_at REAL,
                    last_error TEXT NOT NULL DEFAULT ''
                )
                """
            )

    def emit(self, event_type: str, trade: dict) -> str:
        event_id = str(trade.get("event_id") or uuid.uuid4())
        envelope = {
            "event_id": event_id,
            "event_type": event_type,
            "engine_id": self.engine_id,
            "occurred_at": trade.get("timestamp") or time.time(),
            "trade": trade,
        }
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO trade_event_outbox
                    (event_id, created_at, event_type, payload, next_attempt_at)
                VALUES (?, ?, ?, ?, 0)
                """,
                (event_id, time.time(), event_type, json.dumps(envelope)),
            )
        self._wake.set()
        return event_id

    def _next(self):
        with self._connect() as connection:
            return connection.execute(
                """
                SELECT event_id, payload, attempts
                FROM trade_event_outbox
                WHERE delivered_at IS NULL AND next_attempt_at <= ?
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (time.time(),),
            ).fetchone()

    def _deliver(self, payload: str):
        request = Request(
            self.control_url,
            data=payload.encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=10) as response:
            if response.status < 200 or response.status >= 300:
                raise RuntimeError(f"Control returned HTTP {response.status}")

    def _mark_delivered(self, event_id: str):
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE trade_event_outbox
                SET delivered_at = ?, last_error = ''
                WHERE event_id = ?
                """,
                (time.time(), event_id),
            )

    def _mark_retry(self, event_id: str, attempts: int, error: str):
        delay = min(300.0, self.retry_seconds * (2 ** min(attempts, 6)))
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE trade_event_outbox
                SET attempts = ?, next_attempt_at = ?, last_error = ?
                WHERE event_id = ?
                """,
                (attempts + 1, time.time() + delay, str(error)[:500], event_id),
            )

    def _run(self):
        while True:
            row = self._next()
            if not row:
                self._wake.wait(self.retry_seconds)
                self._wake.clear()
                continue
            event_id, payload, attempts = row
            try:
                self._deliver(payload)
                self._mark_delivered(event_id)
            except (HTTPError, URLError, OSError, RuntimeError) as error:
                self._mark_retry(event_id, attempts, error)
                logger.warning(
                    "Trade event delivery failed event_id=%s attempt=%s: %s",
                    event_id,
                    attempts + 1,
                    error,
                )

    def status(self) -> dict:
        with self._connect() as connection:
            pending = connection.execute(
                "SELECT COUNT(*) FROM trade_event_outbox WHERE delivered_at IS NULL"
            ).fetchone()[0]
            delivered = connection.execute(
                "SELECT COUNT(*) FROM trade_event_outbox WHERE delivered_at IS NOT NULL"
            ).fetchone()[0]
        return {"pending": pending, "delivered": delivered, "control_url": self.control_url}
