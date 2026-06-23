from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Dict, List


BINANCE_REST = {
    "production": "https://api.binance.com",
    "live": "https://api.binance.com",
    "paper": "https://api.binance.com",
    "testnet": "https://testnet.binance.vision",
    "demo": "https://testnet.binance.vision",
}

TF_MAP = {
    "M1": "1m",
    "M5": "5m",
    "M15": "15m",
    "M30": "30m",
    "H1": "1h",
    "H4": "4h",
    "D1": "1d",
}


def normalize_timeframe(timeframe: str) -> str:
    raw = str(timeframe or "M15").strip()
    aliases = {value: key for key, value in TF_MAP.items()}
    return aliases.get(raw.lower(), raw.upper())


def fetch_binance_ohlcv(
    symbol: str,
    timeframe: str = "M15",
    count: int = 500,
    network: str = "production",
    timeout: int = 15,
) -> List[Dict]:
    tf = normalize_timeframe(timeframe)
    interval = TF_MAP.get(tf)
    if not interval:
        raise ValueError(f"unsupported timeframe: {timeframe}")
    base = BINANCE_REST.get(str(network or "production").lower())
    if not base:
        raise ValueError(f"unsupported Binance network: {network}")
    limit = max(1, min(int(count), 1000))
    params = urllib.parse.urlencode({
        "symbol": symbol.upper(),
        "interval": interval,
        "limit": limit,
    })
    url = f"{base}/api/v3/klines?{params}"
    with urllib.request.urlopen(url, timeout=timeout) as response:
        rows = json.loads(response.read().decode("utf-8"))
    return [
        {
            "time": int(row[0]) // 1000,
            "open": float(row[1]),
            "high": float(row[2]),
            "low": float(row[3]),
            "close": float(row[4]),
            "volume": float(row[5]),
            "taker_buy": float(row[9]),
        }
        for row in rows
    ]

