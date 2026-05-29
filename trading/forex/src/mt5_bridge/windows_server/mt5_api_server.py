"""
MT5 API Server — Runs on Windows machine with MetaTrader 5 installed.
Exposes MT5 data and order execution via REST and WebSocket.
"""
import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Optional, List
import MetaTrader5 as mt5
from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("mt5_api_server")

app = FastAPI(title="MT5 API Bridge")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Config ──────────────────────────────────────────────
MT5_LOGIN = 0          # ← Exness account number
MT5_PASSWORD = ""      # ← Password
MT5_SERVER = ""        # ← "Exness-MT5Real8" or other server name

# ── Startup/Shutdown ─────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    if not mt5.initialize():
        logger.error(f"MT5 init failed: {mt5.last_error()}")
        raise RuntimeError(f"MT5 init failed: {mt5.last_error()}")
    
    # Try to login if parameters are supplied
    if MT5_LOGIN > 0:
        authorized = mt5.login(MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER)
        if not authorized:
            logger.error(f"MT5 login failed: {mt5.last_error()}")
            raise RuntimeError(f"MT5 login failed: {mt5.last_error()}")
    
    account_info = mt5.account_info()
    name = account_info.name if account_info else "Demo Account"
    logger.info(f"MT5 initialized successfully. Account name: {name}")

@app.on_event("shutdown")
async def shutdown():
    mt5.shutdown()
    logger.info("MT5 connection shutdown completed.")

# ── Helper function for filling mode ────────────────────
def get_filling_mode(symbol: str) -> int:
    """Auto-detects the filling mode supported by the broker for a symbol."""
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        logger.warning(f"Symbol {symbol} info not found. Defaulting to ORDER_FILLING_IOC.")
        return mt5.ORDER_FILLING_IOC
        
    filling = symbol_info.filling_mode
    # SYMBOL_FILLING_FOK = 1, SYMBOL_FILLING_IOC = 2
    if filling & 1:  # FOK supported
        return mt5.ORDER_FILLING_FOK
    elif filling & 2:  # IOC supported
        return mt5.ORDER_FILLING_IOC
    else:
        logger.info(f"Neither FOK nor IOC indicated for {symbol}. Using ORDER_FILLING_RETURN.")
        return mt5.ORDER_FILLING_RETURN

# ── REST Endpoints ───────────────────────────────────────

@app.get("/health")
def health():
    info = mt5.account_info()
    if info is None:
        raise HTTPException(503, f"Failed to retrieve account info: {mt5.last_error()}")
    return {"status": "ok", "balance": float(info.balance), "equity": float(info.equity)}

@app.get("/account")
def account():
    info = mt5.account_info()
    if info is None:
        raise HTTPException(503, f"Failed to retrieve account info: {mt5.last_error()}")
    return {
        "login": int(info.login),
        "balance": float(info.balance),
        "equity": float(info.equity),
        "margin": float(info.margin),
        "margin_free": float(info.margin_free),
        "profit": float(info.profit),
        "leverage": int(info.leverage),
        "currency": str(info.currency),
    }

@app.get("/price/{symbol}")
def get_price(symbol: str):
    mt5.symbol_select(symbol, True)
    tick = None
    for _ in range(10):  # retry up to 5s
        tick = mt5.symbol_info_tick(symbol)
        if tick and tick.bid > 0:
            break
        import time; time.sleep(0.5)
    if tick is None or tick.bid == 0:
        raise HTTPException(404, f"Symbol {symbol} not found or no tick data")
    return {
        "symbol": symbol,
        "bid": float(tick.bid),
        "ask": float(tick.ask),
        "last": float((tick.bid + tick.ask) / 2),
        "time": int(tick.time),
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
    
    # Ensure symbol is active in Market Watch
    mt5.symbol_select(symbol, True)
    
    rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
    if rates is None:
        raise HTTPException(404, f"No OHLCV for {symbol}: {mt5.last_error()}")
    
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
    if symbols is None:
        return {"symbols": []}
    # Return first 50 symbols
    return {"symbols": [s.name for s in symbols[:50]]}

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
    # Ensure symbol is selected
    if not mt5.symbol_select(req.symbol, True):
        raise HTTPException(404, f"Symbol {req.symbol} select failed")
        
    symbol_info = mt5.symbol_info(req.symbol)
    if symbol_info is None:
        raise HTTPException(404, f"Symbol {req.symbol} not found")

    tick = mt5.symbol_info_tick(req.symbol)
    if tick is None:
        raise HTTPException(503, f"Cannot get tick data for {req.symbol}")
        
    price = tick.ask if req.action == "BUY" else tick.bid
    order_type = mt5.ORDER_TYPE_BUY if req.action == "BUY" else mt5.ORDER_TYPE_SELL
    filling_mode = get_filling_mode(req.symbol)

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": req.symbol,
        "volume": float(req.volume),
        "type": order_type,
        "price": float(price),
        "sl": float(req.sl),
        "tp": float(req.tp),
        "deviation": 20,
        "magic": int(req.magic),
        "comment": req.comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": filling_mode,
    }

    logger.info(f"Sending order to MT5: {request}")
    result = mt5.order_send(request)
    if result is None:
        raise HTTPException(500, f"Order send failed completely: {mt5.last_error()}")
        
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        logger.error(f"Order failed: {result.comment} (code {result.retcode})")
        raise HTTPException(400, f"Order failed: {result.comment} (code {result.retcode})")

    return {
        "order_id": int(result.order),
        "symbol": req.symbol,
        "action": req.action,
        "volume": float(result.volume),
        "price": float(result.price),
        "comment": str(result.comment),
    }

@app.get("/positions")
def get_positions():
    positions = mt5.positions_get()
    if positions is None:
        return {"positions": []}
    return {
        "positions": [
            {
                "ticket": int(p.ticket),
                "symbol": str(p.symbol),
                "type": "BUY" if p.type == 0 else "SELL",
                "volume": float(p.volume),
                "price_open": float(p.price_open),
                "price_current": float(p.price_current),
                "sl": float(p.sl),
                "tp": float(p.tp),
                "profit": float(p.profit),
                "magic": int(p.magic),
            }
            for p in positions
        ]
    }

@app.get("/history/deal/{ticket}")
def get_deal_history(ticket: int):
    """Retrieves deal history to obtain realized PnL for a closed position ticket."""
    # We query history from 1 day ago to now
    from_date = int(time.time()) - 24 * 3600
    to_date = int(time.time()) + 3600
    
    deals = mt5.history_deals_get(position=ticket)
    if deals is None or len(deals) == 0:
        # Fallback to query by date range
        deals = mt5.history_deals_get(from_date, to_date)
        if deals:
            deals = [d for d in deals if d.position == ticket]
            
    if not deals:
        raise HTTPException(404, f"No history deals found for position ticket {ticket}")
        
    total_pnl = sum(d.profit for d in deals)
    # Add swap and commission
    total_pnl += sum(d.swap + d.commission for d in deals)
    
    # Estimate pnl percentage
    # First deal is usually the entry deal
    entry_price = float(deals[0].price)
    
    return {
        "ticket": ticket,
        "pnl": float(total_pnl),
        "entry_price": entry_price,
        "time": int(deals[-1].time),
    }


@app.get("/history/recent")
def get_recent_history(hours: int = 24, limit: int = 200):
    """Return recent deal history across the account for the past `hours` hours.
    This is used by the dashboard to populate order history.
    """
    to_date = int(time.time()) + 3600
    from_date = int(time.time()) - int(hours) * 3600

    deals = mt5.history_deals_get(from_date, to_date)
    if deals is None:
        return {"deals": []}

    # Sort newest first and limit
    deals_list = sorted(deals, key=lambda d: d.time if hasattr(d, 'time') else 0, reverse=True)[:limit]

    out = []
    for d in deals_list:
        out.append({
            "ticket": int(getattr(d, 'ticket', 0)),
            "position": int(getattr(d, 'position', 0)),
            "symbol": str(getattr(d, 'symbol', '')),
            "volume": float(getattr(d, 'volume', 0.0)),
            "price": float(getattr(d, 'price', 0.0)),
            "profit": float(getattr(d, 'profit', 0.0)),
            "swap": float(getattr(d, 'swap', 0.0)),
            "commission": float(getattr(d, 'commission', 0.0)),
            "time": int(getattr(d, 'time', 0)),
            "type": int(getattr(d, 'type', 0)),
            "entry": bool(getattr(d, 'entry', False)),
            "comment": str(getattr(d, 'comment', '')),
        })

    return {"deals": out}

@app.delete("/position/{ticket}")
def close_position(ticket: int):
    positions = mt5.positions_get(ticket=ticket)
    if not positions:
        raise HTTPException(404, f"Position {ticket} not found")
    pos = positions[0]
    close_type = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY
    
    # Ensure symbol is selected
    mt5.symbol_select(pos.symbol, True)
    
    tick = mt5.symbol_info_tick(pos.symbol)
    if tick is None:
        raise HTTPException(503, f"Cannot get tick data for {pos.symbol}")
        
    price = tick.bid if pos.type == 0 else tick.ask
    filling_mode = get_filling_mode(pos.symbol)

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": pos.symbol,
        "volume": float(pos.volume),
        "type": close_type,
        "position": int(ticket),
        "price": float(price),
        "deviation": 20,
        "magic": int(pos.magic),
        "comment": "MTAI-close",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": filling_mode,
    }
    
    logger.info(f"Closing position {ticket}: {request}")
    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        comment = result.comment if result else "unknown"
        retcode = result.retcode if result else -1
        raise HTTPException(400, f"Close failed: {comment} (code {retcode})")
        
    return {"closed": int(ticket), "profit": float(pos.profit)}

# ── WebSocket real-time price stream ─────────────────────
@app.websocket("/ws/prices")
async def price_stream(ws: WebSocket, symbols: str = "EURUSD,GBPUSD,XAUUSD"):
    await ws.accept()
    raw_list = symbols.split(",")
    # Resolve exact MT5 symbol names (case-sensitive)
    all_mt5 = mt5.symbols_get() or []
    all_symbols = {s.name.upper(): s.name for s in all_mt5}
    def resolve(s: str) -> str:
        exact = all_symbols.get(s.upper())
        if exact:
            return exact
        # try lowercase-m suffix variant (broker convention)
        variant = s.upper().rstrip("M") + "m"
        return variant if variant.upper() in all_symbols else s
    symbol_list = [resolve(s) for s in raw_list]
    logger.info(f"Resolved symbols: {raw_list} -> {symbol_list}")
    for sym in symbol_list:
        mt5.symbol_select(sym, True)
    # Wait until at least one symbol has a tick (MT5 needs time after symbol_select)
    for _ in range(20):  # up to 10s
        await asyncio.sleep(0.5)
        if any(mt5.symbol_info_tick(s) for s in symbol_list):
            break

    try:
        while True:
            prices = {}
            for sym in symbol_list:
                tick = mt5.symbol_info_tick(sym)
                if tick and tick.bid > 0:
                    prices[sym] = {
                        "bid": float(tick.bid),
                        "ask": float(tick.ask),
                        "time": int(tick.time),
                    }
                else:
                    prices[sym] = {"error": "not found"}
            await ws.send_text(json.dumps(prices))
            await asyncio.sleep(0.5)  # 500ms update
    except Exception as e:
        logger.info(f"WebSocket client disconnected: {e}")
    finally:
        try:
            await ws.close()
        except:
            pass

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8888)
