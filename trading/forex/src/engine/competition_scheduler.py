from __future__ import annotations

import time
from typing import Callable, Iterable, List


class CompetitionScheduler:
    """Simple scheduler that tracks last-run time per symbol and interval.

    Usage:
        scheduler = CompetitionScheduler(symbols, interval_seconds=3600)
        if scheduler.tick(symbol):
            await asset_leader.run_competition()
    """

    def __init__(self, symbols: Iterable[str], interval_seconds: int = 3600):
        self.interval = interval_seconds
        self.last: dict[str, float] = {s: 0.0 for s in symbols}

    def tick(self, symbol: str) -> bool:
        now = time.time()
        last = self.last.get(symbol, 0.0)
        if now - last >= self.interval:
            self.last[symbol] = now
            return True
        return False
