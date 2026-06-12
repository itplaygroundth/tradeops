# Phase 1: MT5 Bridge

> **Objective:** แทน Binance WebSocket + CCXT ด้วย MetaTrader 5 data feed + execution  
> เมื่อเสร็จ phase นี้: ดึง real-time price จาก MT5 ได้ + ส่ง order ผ่าน MT5 ได้

---

## ⚠️ Prerequisites

MetaTrader5 Python library รองรับ **Windows เท่านั้น** (native COM API)  
บน Linux ต้องเลือก 1 วิธี:

**Option A (แนะนำ): MT5 API Server บน Windows VM/machine แยก**
```
Windows PC (Exness MT5 installed)
  └── mt5_api_server.py  ←── FastAPI server port 8888
          ↑
Linux (192.168.1.166)
  └── mt5_bridge/feed.py  ←── HTTP/WebSocket client
```

**Option B: Wine + MetaTrader5 บน Linux (unstable)**
```bash
pip install MetaTrader5  # จะ error บน Linux
# ต้องใช้ Wine workaround — ไม่แนะนำ production
```

**Plan นี้ใช้ Option A** — แยก concerns ชัดเจน, stable กว่า

---

## Task 1.1: สร้าง MT5 API Server (Windows side)

**Objective:** FastAPI server บน Windows ที่ wrap MetaTrader5 library

**Files:**
- Create: `src/mt5_bridge/windows_server/mt5_api_server.py`
- Create: `src/mt5_bridge/windows_server/requirements.txt`

**Step 1: สร้าง requirements.txt**

```
MetaTrader5==5.0.45
fastapi==0.111.0
uvicorn==0.29.0
websockets==12.0
```

**Step 2: สร้าง mt5_api_server.py**

```python
"""
MT5 API Server — รันบน Windows machine ที่ติดตั้ง MetaTrader5
Expose MT5 data + order execution ผ่าน REST + WebSocket
"""
import asyncio
import json
import time
from datetime import datetime
from typing import Optional, List
import MetaTrader5 as mt5
from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

app = FastAPI(title="MT5 API Bridge")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── Config ──────────────────────────────────────────────
MT5_LOGIN = 0          # ← ใส่ Exness account number
MT5_PASSWORD = ""      # ← ใส่ password
MT5_SERVER = ""        # ← "Exness-MT5Real8" หรือ server name

# ── Startup ─────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    if not mt5.initialize():
        raise RuntimeError(f"MT5 init failed: {mt5.last_error()}")
    authorized = mt5.login(MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER)
    if not authorized:
        raise RuntimeError(f"MT5 login failed: {mt5.last_error()}")
    print(f"MT5 connected: {mt5.account_info().name}")

@app.on_event("shutdown")
async def shutdown():
    mt5.shutdown()

# ── REST Endpoints ───────────────────────────────────────

@app.get("/health")
def health():
    info = mt5.account_info()
    return {"status": "ok", "balance": info.balance, "equity": info.equity}

@app.get("/account")
def account():
    info = mt5.account_info()
    return {
        "login": info.login,
        "balance": info.balance,
        "equity": info.equity,
        "margin": info.margin,
        "margin_free": info.margin_free,
        "profit": info.profit,
        "leverage": info.leverage,
        "currency": info.currency,
    }

@app.get("/price/{symbol}")
def get_price(symbol: str):
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        raise HTTPException(404, f"Symbol {symbol} not found")
    return {
        "symbol": symbol,
        "bid": tick.bid,
        "ask": tick.ask,
        "last": (tick.bid + tick.ask) / 2,
        "time": tick.time,
    }

@app.get("/ohlcv/{symbol}")
def get_ohlcv(symbol: str, timeframe: str = "M15", count: int = 200):
    tf_map = {
        "M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15, "M30": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1,
    }
    tf = tf_map.get(timeframe, mt5.TIMEFRAME_M15)
    rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
    if rates is None:
        raise HTTPException(404, f"No OHLCV for {symbol}")
    return [
        {
            "time": int(r["time"]),
            "open": float(r["open"]),
            "high": float(r["high"]),
            "low": float(r["low"]),
            "close": float(r["close"]),
            "volume": float(r["tick_volume"]),
        }
        for r in rates
    ]

@app.get("/symbols")
def get_symbols():
    symbols = mt5.symbols_get()
    forex = [s.name for s in symbols if s.path.startswith("Forex")]
    return {"symbols": forex[:50]}

class OrderRequest(BaseModel):
    symbol: str
    action: str       # "BUY" | "SELL"
    volume: float     # lot size
    price: float = 0  # 0 = market order
    sl: float = 0     # stop loss price (0 = no SL)
    tp: float = 0     # take profit price (0 = no TP)
    comment: str = "MTAI"
    magic: int = 20260101

@app.post("/order")
def place_order(req: OrderRequest):
    symbol_info = mt5.symbol_info(req.symbol)
    if symbol_info is None:
        raise HTTPException(404, f"Symbol {req.symbol} not found")

    tick = mt5.symbol_info_tick(req.symbol)
    price = tick.ask if req.action == "BUY" else tick.bid

    order_type = mt5.ORDER_TYPE_BUY if req.action == "BUY" else mt5.ORDER_TYPE_SELL

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": req.symbol,
        "volume": req.volume,
        "type": order_type,
        "price": price,
        "sl": req.sl,
        "tp": req.tp,
        "deviation": 20,
        "magic": req.magic,
        "comment": req.comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        raise HTTPException(400, f"Order failed: {result.comment} (code {result.retcode})")

    return {
        "order_id": result.order,
        "symbol": req.symbol,
        "action": req.action,
        "volume": result.volume,
        "price": result.price,
        "comment": result.comment,
    }

@app.get("/positions")
def get_positions():
    positions = mt5.positions_get()
    if positions is None:
        return {"positions": []}
    return {
        "positions": [
            {
                "ticket": p.ticket,
                "symbol": p.symbol,
                "type": "BUY" if p.type == 0 else "SELL",
                "volume": p.volume,
                "price_open": p.price_open,
                "price_current": p.price_current,
                "sl": p.sl,
                "tp": p.tp,
                "profit": p.profit,
                "magic": p.magic,
            }
            for p in positions
        ]
    }

@app.delete("/position/{ticket}")
def close_position(ticket: int):
    positions = mt5.positions_get(ticket=ticket)
    if not positions:
        raise HTTPException(404, f"Position {ticket} not found")
    pos = positions[0]
    close_type = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY
    tick = mt5.symbol_info_tick(pos.symbol)
    price = tick.bid if pos.type == 0 else tick.ask

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": pos.symbol,
        "volume": pos.volume,
        "type": close_type,
        "position": ticket,
        "price": price,
        "deviation": 20,
        "magic": pos.magic,
        "comment": "MTAI-close",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        raise HTTPException(400, f"Close failed: {result.comment}")
    return {"closed": ticket, "profit": pos.profit}

# ── WebSocket real-time price stream ─────────────────────
@app.websocket("/ws/prices")
async def price_stream(ws: WebSocket, symbols: str = "EURUSD,GBPUSD,XAUUSD"):
    await ws.accept()
    symbol_list = symbols.split(",")
    try:
        while True:
            prices = {}
            for sym in symbol_list:
                tick = mt5.symbol_info_tick(sym)
                if tick:
                    prices[sym] = {
                        "bid": tick.bid,
                        "ask": tick.ask,
                        "time": tick.time,
                    }
            await ws.send_text(json.dumps(prices))
            await asyncio.sleep(0.5)  # 500ms update
    except Exception:
        pass

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8888)
```

**Step 3: Install + Run (บน Windows)**

```bash
pip install -r requirements.txt
python mt5_api_server.py
# → Server running on http://0.0.0.0:8888
```

**Verify:**
```bash
curl http://WINDOWS_IP:8888/health
# → {"status":"ok","balance":1000.0,"equity":1000.0}
curl http://WINDOWS_IP:8888/price/EURUSD
# → {"symbol":"EURUSD","bid":1.0850,"ask":1.0852,...}
```

---

## Task 1.2: MT5 Client (Linux side)

**Objective:** Python client บน Linux ที่คุยกับ MT5 API Server

**Files:**
- Create: `src/mt5_bridge/__init__.py`
- Create: `src/mt5_bridge/client.py`
- Create: `src/mt5_bridge/feed.py`

**Step 1: สร้าง client.py**

```python
"""
MT5 Client — ติดต่อกับ MT5 API Server บน Windows
ใช้แทน ccxt.binance() ใน ai-trading-live
"""
import httpx
import asyncio
import websockets
import json
import logging
from typing import Optional, List, Dict, Callable
from dataclasses import dataclass

logger = logging.getLogger("mt5_client")

# ── Config ──────────────────────────────────────────────
MT5_SERVER_URL = "http://192.168.1.XXX:8888"  # ← ใส่ IP ของ Windows machine

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
        self._client = httpx.AsyncClient(timeout=10.0, base_url=server_url)

    async def health(self) -> dict:
        r = await self._client.get("/health")
        r.raise_for_status()
        return r.json()

    async def get_account(self) -> dict:
        r = await self._client.get("/account")
        r.raise_for_status()
        return r.json()

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

    async def place_order(self, symbol: str, action: str, volume: float,
                          sl: float = 0, tp: float = 0, comment: str = "MTAI") -> dict:
        payload = {
            "symbol": symbol,
            "action": action,
            "volume": volume,
            "sl": sl,
            "tp": tp,
            "comment": comment,
        }
        r = await self._client.post("/order", json=payload)
        r.raise_for_status()
        return r.json()

    async def get_positions(self) -> List[dict]:
        r = await self._client.get("/positions")
        r.raise_for_status()
        return r.json()["positions"]

    async def close_position(self, ticket: int) -> dict:
        r = await self._client.delete(f"/position/{ticket}")
        r.raise_for_status()
        return r.json()

    async def close(self):
        await self._client.aclose()
```

**Step 2: สร้าง feed.py (แทน market_feed.py)**

```python
"""
MT5 Feed — Real-time price stream จาก MT5 API Server
แทน Binance WebSocket ใน ai-trading-live/engine/market_feed.py
"""
import asyncio
import json
import logging
import time
import websockets
from typing import Dict, Callable, List, Optional

logger = logging.getLogger("mt5_feed")

# Forex symbols ที่จะ trade (แทน BTC/ETH/SOL)
DEFAULT_SYMBOLS = [
    "EURUSD",   # Major — high liquidity
    "GBPUSD",   # Major — volatile, good for momentum
    "USDJPY",   # Major — yen carry trade
    "XAUUSD",   # Gold — high volatility, strong trends
    "USDCHF",   # Safe haven
    "AUDUSD",   # Commodity-linked
    "USDCAD",   # Oil-linked
    "NZDUSD",   # Risk-on
]

class MT5Feed:
    """
    Real-time price feed จาก MT5 API Server
    Interface เหมือน MarketFeed ใน ai-trading-live
    """

    def __init__(self, ws_url: str, symbols: List[str] = None):
        self.ws_url = ws_url  # ws://WINDOWS_IP:8888/ws/prices
        self.symbols = symbols or DEFAULT_SYMBOLS
        self._callbacks: List[Callable] = []
        self._running = False
        self._last_prices: Dict[str, dict] = {}

    def on_tick(self, callback: Callable):
        """Register callback รับ tick data"""
        self._callbacks.append(callback)

    async def start(self):
        """Start streaming prices"""
        self._running = True
        symbols_param = ",".join(self.symbols)
        url = f"{self.ws_url}?symbols={symbols_param}"
        logger.info(f"MT5Feed connecting: {url}")

        while self._running:
            try:
                async with websockets.connect(url) as ws:
                    logger.info("MT5Feed connected ✓")
                    async for message in ws:
                        if not self._running:
                            break
                        prices = json.loads(message)
                        await self._process_tick(prices)
            except Exception as e:
                logger.warning(f"MT5Feed disconnected: {e} — retry in 3s")
                await asyncio.sleep(3)

    async def _process_tick(self, prices: Dict[str, dict]):
        """Process incoming tick from WebSocket"""
        now = time.time()
        for symbol, data in prices.items():
            mid = (data["bid"] + data["ask"]) / 2
            tick = {
                "symbol": symbol,
                "price": mid,
                "bid": data["bid"],
                "ask": data["ask"],
                "volume": 1.0,   # MT5 tick volume ไม่เหมือน crypto — ใช้ 1 เป็น placeholder
                "timestamp": data.get("time", now),
            }
            self._last_prices[symbol] = tick
            for cb in self._callbacks:
                try:
                    await cb(tick)
                except Exception as e:
                    logger.error(f"Tick callback error: {e}")

    def get_last_price(self, symbol: str) -> Optional[float]:
        tick = self._last_prices.get(symbol)
        return tick["price"] if tick else None

    async def stop(self):
        self._running = False
```

**Step 3: Test connection**

```python
# tests/test_mt5_bridge.py
import asyncio
import pytest
from mt5_bridge.client import MT5Client

@pytest.mark.asyncio
async def test_health():
    client = MT5Client()
    result = await client.health()
    assert result["status"] == "ok"
    assert "balance" in result
    await client.close()

@pytest.mark.asyncio
async def test_get_price():
    client = MT5Client()
    tick = await client.get_price("EURUSD")
    assert tick.bid > 0
    assert tick.ask > tick.bid  # ask > bid always
    await client.close()
```

**Verify:**
```bash
cd /home/alfred/mtai/src
python3 -c "
import asyncio
from mt5_bridge.client import MT5Client
async def test():
    c = MT5Client()
    h = await c.health()
    print('Health:', h)
    t = await c.get_price('EURUSD')
    print('EURUSD:', t)
asyncio.run(test())
"
```

---

## Task 1.3: Pip Value Calculator

**Objective:** คำนวณ pip value สำหรับ position sizing (critical สำหรับ forex)

**Files:**
- Create: `src/mt5_bridge/pip_calc.py`

```python
"""
Pip Value Calculator — forex-specific position sizing helper
ใช้ใน Risk Guardian เพื่อคำนวณ lot size จาก risk amount
"""

# Pip sizes ต่อ symbol
PIP_SIZES = {
    "EURUSD": 0.0001, "GBPUSD": 0.0001, "AUDUSD": 0.0001,
    "NZDUSD": 0.0001, "USDCHF": 0.0001, "USDCAD": 0.0001,
    "USDJPY": 0.01,   "EURJPY": 0.01,   "GBPJPY": 0.01,
    "XAUUSD": 0.1,    "XAGUSD": 0.001,
}

def get_pip_size(symbol: str) -> float:
    return PIP_SIZES.get(symbol, 0.0001)

def price_to_pips(symbol: str, price_distance: float) -> float:
    """แปลง price distance → จำนวน pips"""
    return price_distance / get_pip_size(symbol)

def pips_to_price(symbol: str, pips: float) -> float:
    """แปลง pips → price distance"""
    return pips * get_pip_size(symbol)

def calculate_lot_size(
    account_balance: float,
    risk_pct: float,      # เช่น 0.01 = 1%
    sl_price_distance: float,
    symbol: str,
    contract_size: float = 100_000,  # standard lot
    price: float = 1.0,              # current price (สำหรับ pairs ที่ quote ไม่ใช่ USD)
) -> float:
    """
    คำนวณ lot size จาก risk percentage
    
    Formula: lot_size = (balance × risk_pct) / (sl_distance × contract_size)
    สำหรับ USD-quoted pairs (EURUSD, GBPUSD, XAUUSD)
    """
    risk_amount = account_balance * risk_pct
    pip_size = get_pip_size(symbol)
    sl_pips = sl_price_distance / pip_size
    pip_value_per_lot = pip_size * contract_size  # USD per pip per lot (for USD-quote)

    if sl_pips == 0:
        return 0.01  # minimum lot

    lot_size = risk_amount / (sl_pips * pip_value_per_lot)
    
    # Clamp: min 0.01 lot, max 10 lots
    return max(0.01, min(10.0, round(lot_size, 2)))
```

---

## Task 1.4: Integration Test

**Objective:** ทดสอบ end-to-end: feed → price → order (paper)

```python
# tests/test_integration.py
import asyncio
from mt5_bridge.client import MT5Client
from mt5_bridge.pip_calc import calculate_lot_size, price_to_pips

async def test_paper_workflow():
    client = MT5Client()
    
    # 1. ดึง account info
    account = await client.get_account()
    balance = account["balance"]
    print(f"Balance: {balance}")
    
    # 2. ดึงราคา EURUSD
    tick = await client.get_price("EURUSD")
    print(f"EURUSD: bid={tick.bid}, ask={tick.ask}")
    
    # 3. คำนวณ lot size (1% risk, 20 pip SL)
    sl_distance = 0.0020  # 20 pips
    lot = calculate_lot_size(
        account_balance=balance,
        risk_pct=0.01,
        sl_price_distance=sl_distance,
        symbol="EURUSD",
    )
    print(f"Lot size (1% risk, 20pip SL): {lot}")
    
    # 4. ดึง OHLCV
    ohlcv = await client.get_ohlcv("EURUSD", timeframe="M15", count=50)
    print(f"OHLCV candles: {len(ohlcv)}")
    
    await client.close()
    print("✅ Phase 1 integration test PASSED")

asyncio.run(test_paper_workflow())
```

---

## Phase 1 Checklist

- [ ] Windows MT5 API server รัน port 8888
- [ ] Linux client ต่อ server ได้ (`/health` return OK)
- [ ] ดึง EURUSD price ได้
- [ ] ดึง OHLCV M15 200 candles ได้
- [ ] คำนวณ lot size ถูกต้อง (1% risk, 20pip SL)
- [ ] WebSocket price stream ส่ง tick ทุก 500ms

---

## Pitfalls

1. **MT5 ต้องรัน logged-in ตลอดเวลา** บน Windows — ถ้า terminal ปิด API server หยุด
2. **Symbol names ต่างกันตาม broker** — Exness ใช้ `EURUSD` (ไม่มี `.r` suffix) แต่บาง broker ใช้ `EURUSDm`
3. **Filling mode** — Exness ส่วนใหญ่ใช้ `ORDER_FILLING_IOC` แต่บางเซิร์ฟเวอร์ใช้ `ORDER_FILLING_FOK`
4. **Weekend gap** — Forex ปิด Sat-Sun จะมี gap ตอน Monday open → ต้องมี session filter
5. **Spread สำคัญมาก** — Exness Raw spread EURUSD ~0.1 pip แต่ Standard spread ~1.2 pip → ส่งผลต่อ scalping strategy โดยตรง
