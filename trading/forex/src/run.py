"""
MTAI — Main Entry Point
รัน: python3 run.py [--mode paper|demo|live]
"""
import asyncio
import argparse
import logging
import os
import socket
import sys
import subprocess
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

# Add src/ to path so imports work when running as: python3 src/run.py
sys.path.insert(0, str(Path(__file__).parent))

from mt5_bridge.client import MT5Client
from mt5_bridge.feed import MT5Feed
from engine.agent_manager import ForexAgentManager
import json

# Global reference for the running agent manager so the dashboard can toggle mode
AGENT_MANAGER = None
RUNTIME_MODE = "paper"
ACCOUNT_EVIDENCE = {}

MT5_SERVER = os.getenv("MT5_SERVER", "http://192.168.1.107:8888")
MT5_WS = os.getenv("MT5_WS", "ws://192.168.1.107:8888/ws/prices")

logger = logging.getLogger("run")

API_SERVER_CMD = ["npm", "start"]
API_SERVER_DIR = Path(__file__).parent.parent / "hedgefund-repo" / "server"
API_SERVER_PORT = 5001
api_process = None


def is_port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1.0)
        try:
            sock.connect((host, port))
            return True
        except OSError:
            return False


async def start_hedgefund_api_if_available() -> None:
    global api_process
    if is_port_open("127.0.0.1", API_SERVER_PORT):
        logger.info(f"Hedgefund API already available on port {API_SERVER_PORT}")
        return

    if not API_SERVER_DIR.exists():
        logger.warning(f"Hedgefund API server directory not found: {API_SERVER_DIR}")
        return

    logger.info("Starting Hedgefund API server...")
    api_process = subprocess.Popen(
        API_SERVER_CMD,
        cwd=str(API_SERVER_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env={**os.environ, "PORT": str(API_SERVER_PORT)},
    )

    # Wait for port to accept connections
    for _ in range(20):
        await asyncio.sleep(0.5)
        if is_port_open("127.0.0.1", API_SERVER_PORT):
            logger.info(f"Hedgefund API server ready on port {API_SERVER_PORT}")
            return

    logger.warning("Hedgefund API server did not become ready in time")


def find_available_port(start_port: int = 3003, max_port: int = 3100) -> int:
    for port in range(start_port, max_port + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No available ports found between {start_port} and {max_port}")


async def main(
    mode: str = "paper",
    dashboard_port: int = 3003,
    dashboard_only: bool = False,
    host: str = "0.0.0.0",
    mt5_server: str = MT5_SERVER,
    mt5_ws: str = MT5_WS,
    dashboard_dir: str | None = None,
):
    paper = mode == "paper"
    if mode == "live" and os.getenv("ALLOW_LIVE_MODE", "").lower() != "true":
        raise RuntimeError("live production mode is locked; complete readiness certification first")
    if dashboard_only:
        print("🚀 MTAI Dashboard only")
        if dashboard_dir is None:
            await start_hedgefund_api_if_available()
        chosen_port = find_available_port(dashboard_port)
        print(f"📊 Dashboard: http://{host}:{chosen_port}")
        print("Press Ctrl+C to stop\n")
        asyncio.create_task(start_dashboard(host, chosen_port, dashboard_dir))
        await asyncio.Event().wait()
        return

    print(f"🚀 MTAI Forex AI Trading — mode={mode}")

    # Connect MT5
    client = MT5Client(mt5_server)
    try:
        health = await client.health()
        print(f"✅ MT5 connected: balance={health['balance']}")
    except Exception as e:
        print(f"❌ MT5 connection failed: {e}")
        print(f"   Make sure mt5_api_server.py is running on Windows at {mt5_server}")
        return

    # Init agent manager
    manager = ForexAgentManager(client, paper_mode=paper, agent_count=25)
    # expose manager for dashboard API toggles
    global AGENT_MANAGER, RUNTIME_MODE, ACCOUNT_EVIDENCE
    AGENT_MANAGER = manager
    RUNTIME_MODE = mode
    if os.getenv("START_PAUSED", "true").lower() == "true":
        AGENT_MANAGER.pause_entries("startup safety lock")
    try:
        ACCOUNT_EVIDENCE = await client.get_account()
    except Exception as exc:
        logger.warning("Could not load MT5 account evidence: %s", exc)
    try:
        loop = asyncio.get_event_loop()
        asyncio.run_coroutine_threadsafe(AGENT_MANAGER._update_account(), loop)
        asyncio.run_coroutine_threadsafe(AGENT_MANAGER._load_recent_history(hours=48, limit=500), loop)
    except Exception:
        pass
    print(f"✅ {len(manager.agents)} agents initialized")

    # Start price feed
    feed = MT5Feed(mt5_ws)
    feed.on_tick(manager.on_tick)

    chosen_port = dashboard_port
    try:
        chosen_port = find_available_port(dashboard_port)
    except RuntimeError:
        print(f"❌ No open dashboard port found starting at {dashboard_port}")
        return

    print(f"📊 Dashboard: http://{host}:{chosen_port}")
    print("Press Ctrl+C to stop\n")

    if dashboard_dir is None:
        await start_hedgefund_api_if_available()

    # Start dashboard server in background
    asyncio.create_task(start_dashboard(host, chosen_port, dashboard_dir))

    await feed.start()


async def start_dashboard(host: str, port: int, dashboard_dir: str | None = None):
    """Serves the dashboard/ directory over HTTP on the chosen host and port."""
    import http.server
    import socketserver
    import os
    _event_loop = asyncio.get_event_loop()

    if dashboard_dir:
        dashboard_dir = Path(dashboard_dir)
    else:
        dashboard_dir = Path(__file__).parent.parent / "dashboard"

    if not dashboard_dir.exists():
        raise FileNotFoundError(f"Dashboard directory not found: {dashboard_dir}")

    dashboard_dir = dashboard_dir.resolve()

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(dashboard_dir), **kwargs)
        def log_message(self, *args):
            pass

        def do_GET(self):
            if self.path.startswith("/api/manual_actions"):
                from urllib.parse import urlparse, parse_qs
                qs = parse_qs(urlparse(self.path).query)
                try:
                    limit = int(qs.get("limit", [100])[0])
                except Exception:
                    limit = 100
                try:
                    from storage.manual_audit import read_manual_actions
                    body = json.dumps({"items": read_manual_actions(limit=limit)}).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(body)
                except Exception as e:
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": str(e)}).encode())
                return

            # MT5 open positions: /api/mt5/positions  → {"positions": [...]}
            if self.path.startswith("/api/mt5/positions"):
                if AGENT_MANAGER is None:
                    self.send_response(503); self.end_headers(); return
                try:
                    async def enriched_positions():
                        resp = await AGENT_MANAGER.mt5._client.get("/positions")
                        resp.raise_for_status()
                        payload = resp.json()
                        positions = payload.get("positions", [])
                        ticks = {}
                        for symbol in sorted({p.get("symbol") for p in positions if p.get("symbol")}):
                            try:
                                tick_resp = await AGENT_MANAGER.mt5._client.get(f"/price/{symbol}")
                                tick_resp.raise_for_status()
                                ticks[symbol] = tick_resp.json()
                            except Exception:
                                ticks[symbol] = {}

                        for pos in positions:
                            side_raw = pos.get("type")
                            side = "BUY" if side_raw == 0 else "SELL" if side_raw == 1 else str(side_raw or "").upper()
                            tick = ticks.get(pos.get("symbol"), {})
                            bid = tick.get("bid")
                            ask = tick.get("ask")
                            if bid is not None:
                                pos["bid"] = float(bid)
                            if ask is not None:
                                pos["ask"] = float(ask)
                            if bid is not None and ask is not None:
                                pos["last"] = float((bid + ask) / 2)

                            trigger = bid if side == "BUY" else ask
                            trigger_side = "Bid" if side == "BUY" else "Ask"
                            pos["type"] = side
                            pos["tp_trigger_side"] = trigger_side
                            if trigger is not None:
                                trigger = float(trigger)
                                pos["tp_trigger_price"] = trigger
                                tp = float(pos.get("tp") or 0)
                                sl = float(pos.get("sl") or 0)
                                if tp:
                                    raw_tp_distance = tp - trigger if side == "BUY" else trigger - tp
                                    pos["tp_distance"] = max(raw_tp_distance, 0.0)
                                    pos["tp_hit"] = raw_tp_distance <= 0
                                if sl:
                                    raw_sl_distance = trigger - sl if side == "BUY" else sl - trigger
                                    pos["sl_distance"] = max(raw_sl_distance, 0.0)
                                    pos["sl_hit"] = raw_sl_distance <= 0
                        return {"positions": positions}

                    fut = asyncio.run_coroutine_threadsafe(enriched_positions(), _event_loop)
                    result = fut.result(timeout=10)
                    body = json.dumps(result).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(body)
                except Exception as e:
                    self.send_response(502)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"positions": [], "error": str(e)}).encode())
                return

            # MT5 account: /api/mt5/account → {balance, equity, ...}
            if self.path.startswith("/api/mt5/account"):
                if AGENT_MANAGER is None:
                    self.send_response(503); self.end_headers(); return
                try:
                    fut = asyncio.run_coroutine_threadsafe(
                        AGENT_MANAGER.mt5._client.get("/account"), _event_loop
                    )
                    resp = fut.result(timeout=10)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(resp.content)
                except Exception as e:
                    self.send_response(502)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": str(e)}).encode())
                return

            if self.path.startswith("/api/control/status"):
                if AGENT_MANAGER is None:
                    self.send_response(503); self.end_headers(); return
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(AGENT_MANAGER.control_status()).encode())
                return

            # OHLCV chart data: /api/mt5/ohlcv/<symbol>?timeframe=M15&count=200
            if self.path.startswith("/api/mt5/ohlcv/"):
                from urllib.parse import urlparse, parse_qs
                parsed = urlparse(self.path)
                symbol = parsed.path.split("/api/mt5/ohlcv/", 1)[1].strip("/")
                qs = parse_qs(parsed.query)
                timeframe = qs.get("timeframe", ["M15"])[0]
                count = int(qs.get("count", ["200"])[0])
                if AGENT_MANAGER is None:
                    self.send_response(503)
                    self.end_headers()
                    return
                try:
                    loop = _event_loop
                    fut = asyncio.run_coroutine_threadsafe(
                        AGENT_MANAGER.mt5.get_ohlcv(symbol, timeframe=timeframe, count=count), loop
                    )
                    result = fut.result(timeout=10)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(json.dumps(result).encode())
                except Exception as e:
                    self.send_response(502)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": str(e)}).encode())
                return

            # Provide a small API to read current mode/account
            # Deal history lookup: /api/deal/<ticket>
            if self.path.startswith("/api/deal/"):
                if AGENT_MANAGER is None:
                    self.send_response(503)
                    self.end_headers()
                    return
                try:
                    ticket_str = self.path.split("/api/deal/", 1)[1]
                    ticket = int(ticket_str)
                except Exception:
                    self.send_response(400)
                    self.end_headers()
                    return
                try:
                    loop = _event_loop
                    fut = asyncio.run_coroutine_threadsafe(AGENT_MANAGER.mt5.get_deal_history(ticket), loop)
                    result = fut.result(timeout=5)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps(result).encode())
                except Exception as e:
                    self.send_response(502)
                    self.end_headers()
                return
            if self.path.startswith("/api/mode"):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                if AGENT_MANAGER is None:
                    mode = "dashboard-only"
                    account = {}
                else:
                    mode = RUNTIME_MODE
                    account = {"balance": AGENT_MANAGER._account_balance, "equity": AGENT_MANAGER._account_equity}
                configured_demo_login = os.getenv("MT5_DEMO_LOGIN", "").strip()
                bridge_verified_demo = bool(
                    ACCOUNT_EVIDENCE.get("is_demo")
                    or str(ACCOUNT_EVIDENCE.get("trade_mode", "")).lower() == "demo"
                )
                allowlist_verified_demo = bool(
                    configured_demo_login
                    and str(ACCOUNT_EVIDENCE.get("login", "")) == configured_demo_login
                )
                self.wfile.write(json.dumps({
                    "mode": mode,
                    "execution_environment": "simulated" if mode == "paper" else ("broker_demo" if mode == "demo" else "production"),
                    "demo_account_verified": bridge_verified_demo or allowlist_verified_demo,
                    "demo_verification_source": "bridge" if bridge_verified_demo else ("login_allowlist" if allowlist_verified_demo else "unverified"),
                    "account_evidence": {
                        "login": ACCOUNT_EVIDENCE.get("login"),
                        "server": ACCOUNT_EVIDENCE.get("server"),
                        "company": ACCOUNT_EVIDENCE.get("company"),
                        "trade_mode": ACCOUNT_EVIDENCE.get("trade_mode"),
                        "trade_allowed": ACCOUNT_EVIDENCE.get("trade_allowed"),
                        "trade_expert": ACCOUNT_EVIDENCE.get("trade_expert"),
                    },
                    "account": account,
                }).encode())
                return

            if self.path.startswith("/api/trading_journal/summary"):
                from urllib.parse import urlparse, parse_qs
                qs = parse_qs(urlparse(self.path).query)
                try:
                    limit = int(qs.get("limit", [10000])[0])
                except Exception:
                    limit = 10000
                try:
                    min_trades = int(qs.get("min_trades", [3])[0])
                except Exception:
                    min_trades = 3
                try:
                    from storage.history_db import query_orders_for_export
                    from storage.trading_journal import build_institutional_journal
                    from storage.journal_analysis import analyze_journal
                    account = {}
                    if AGENT_MANAGER is not None:
                        account = {
                            "balance": AGENT_MANAGER._account_balance,
                            "equity": AGENT_MANAGER._account_equity,
                            "currency": AGENT_MANAGER._account_currency,
                        }
                    orders = query_orders_for_export(limit=limit)
                    rows = build_institutional_journal(orders, account=account, venue="MT5")
                    body = json.dumps(analyze_journal(rows, min_trades=min_trades)).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(body)
                except Exception as e:
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": str(e)}).encode())
                return

            if self.path.startswith("/api/trading_journal/export"):
                from urllib.parse import urlparse, parse_qs
                qs = parse_qs(urlparse(self.path).query)
                fmt = qs.get("format", ["csv"])[0].lower()
                symbol = qs.get("symbol", [None])[0]
                agent = qs.get("agent", [None])[0]
                status = qs.get("status", [None])[0]
                q = qs.get("q", [None])[0]
                try:
                    limit = int(qs.get("limit", [10000])[0])
                except Exception:
                    limit = 10000

                try:
                    from storage.history_db import query_orders_for_export
                    from storage.trading_journal import (
                        build_institutional_journal,
                        journal_to_csv,
                        journal_to_json,
                    )
                    account = {}
                    if AGENT_MANAGER is not None:
                        try:
                            fut = asyncio.run_coroutine_threadsafe(AGENT_MANAGER.mt5.get_account(), _event_loop)
                            account = fut.result(timeout=5)
                        except Exception:
                            account = {
                                "balance": AGENT_MANAGER._account_balance,
                                "equity": AGENT_MANAGER._account_equity,
                                "currency": AGENT_MANAGER._account_currency,
                            }
                    orders = query_orders_for_export(symbol=symbol, agent=agent, status=status, q=q, limit=limit)
                    rows = build_institutional_journal(orders, account=account, venue="MT5")
                    if fmt == "json":
                        body = journal_to_json(rows).encode()
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.send_header("Content-Disposition", "attachment; filename=trading_journal_institutional.json")
                        self.end_headers()
                        self.wfile.write(body)
                    else:
                        body = journal_to_csv(rows).encode()
                        self.send_response(200)
                        self.send_header("Content-Type", "text/csv")
                        self.send_header("Content-Disposition", "attachment; filename=trading_journal_institutional.csv")
                        self.end_headers()
                        self.wfile.write(body)
                except Exception as e:
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": str(e)}).encode())
                return

            if self.path.startswith("/api/order_history") and not self.path.startswith("/api/order_history/export") and not self.path.startswith("/api/order_history/stream"):
                # Serve paginated/filtered order history: /api/order_history?offset=0&limit=100&symbol=&agent=&status=&q=
                from urllib.parse import urlparse, parse_qs
                qs = parse_qs(urlparse(self.path).query)
                try:
                    offset = int(qs.get("offset", [0])[0])
                    limit = int(qs.get("limit", [100])[0])
                except Exception:
                    offset = 0
                    limit = 100
                symbol = qs.get("symbol", [None])[0]
                agent = qs.get("agent", [None])[0]
                status = qs.get("status", [None])[0]
                q = qs.get("q", [None])[0]

                try:
                    from storage.history_db import query_orders
                    res = query_orders(offset=offset, limit=limit, symbol=symbol, agent=agent, status=status, q=q)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps(res).encode())
                except Exception:
                    # fallback to in-memory slice
                    if AGENT_MANAGER is None:
                        self.send_response(503)
                        self.end_headers()
                        return
                    try:
                        hist = AGENT_MANAGER._order_history
                        slice_items = hist[offset:offset+limit]
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        self.wfile.write(json.dumps({"offset": offset, "limit": limit, "items": slice_items}).encode())
                    except Exception:
                        self.send_response(500)
                        self.end_headers()
                return

            if self.path.startswith("/api/order_history/export"):
                # Export CSV for filtered query using the institutional journal schema.
                from urllib.parse import urlparse, parse_qs
                qs = parse_qs(urlparse(self.path).query)
                try:
                    limit = int(qs.get("limit", [10000])[0])
                except Exception:
                    limit = 10000
                symbol = qs.get("symbol", [None])[0]
                agent = qs.get("agent", [None])[0]
                status = qs.get("status", [None])[0]
                q = qs.get("q", [None])[0]
                try:
                    from storage.history_db import query_orders_for_export
                    from storage.trading_journal import build_institutional_journal, journal_to_csv
                    account = {}
                    if AGENT_MANAGER is not None:
                        try:
                            fut = asyncio.run_coroutine_threadsafe(AGENT_MANAGER.mt5.get_account(), _event_loop)
                            account = fut.result(timeout=5)
                        except Exception:
                            account = {
                                "balance": AGENT_MANAGER._account_balance,
                                "equity": AGENT_MANAGER._account_equity,
                                "currency": AGENT_MANAGER._account_currency,
                            }
                    items = query_orders_for_export(symbol=symbol, agent=agent, status=status, q=q, limit=limit)
                    csv = journal_to_csv(build_institutional_journal(items, account=account, venue="MT5"))
                    self.send_response(200)
                    self.send_header("Content-Type", "text/csv")
                    self.send_header("Content-Disposition", "attachment; filename=trading_journal_institutional.csv")
                    self.end_headers()
                    self.wfile.write(csv.encode())
                except Exception:
                    self.send_response(500)
                    self.end_headers()
                return

            if self.path.startswith("/api/order_history/stream"):
                # Server-Sent Events stream of new orders
                try:
                    from storage import pubsub
                except Exception:
                    self.send_response(500)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.end_headers()
                q = pubsub.subscribe()
                try:
                    while True:
                        try:
                            ev = q.get()
                        except Exception:
                            break
                        try:
                            data = json.dumps(ev)
                        except Exception:
                            data = str(ev)
                        try:
                            self.wfile.write(f"data: {data}\n\n".encode())
                            self.wfile.flush()
                        except Exception:
                            break
                finally:
                    try:
                        pubsub.unsubscribe(q)
                    except Exception:
                        pass
                return
            return super().do_GET()

        def do_POST(self):
            global RUNTIME_MODE
            if self.path.startswith("/api/control/risk-policy"):
                if AGENT_MANAGER is None:
                    self.send_response(503); self.end_headers(); return
                content_len = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_len) if content_len else b""
                try:
                    data = json.loads(body.decode() or "{}")
                    result = AGENT_MANAGER.set_risk_policy(
                        data.get("mode", "NORMAL"),
                        data.get("risk_scale", 1.0),
                        data.get("max_positions", 3),
                    )
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(json.dumps({"success": True, "control": result}).encode())
                except (TypeError, ValueError) as e:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": str(e)}).encode())
                return
            if self.path.startswith("/api/control/pause") or self.path.startswith("/api/control/resume"):
                if AGENT_MANAGER is None:
                    self.send_response(503); self.end_headers(); return
                content_len = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_len) if content_len else b""
                try:
                    data = json.loads(body.decode() or "{}")
                except Exception:
                    self.send_response(400); self.end_headers(); return
                action_type = "pause" if self.path.startswith("/api/control/pause") else "resume"
                reason = data.get("reason") or "hedgefund control"
                audit_payload = {
                    "action": f"control_{action_type}",
                    "source": "hedgefund-control",
                    "reason": reason,
                    "path": self.path,
                }
                try:
                    if action_type == "pause":
                        result = AGENT_MANAGER.pause_entries(reason)
                    else:
                        result = AGENT_MANAGER.resume_entries()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(json.dumps({"success": True, "control": result}).encode())
                    try:
                        from storage.manual_audit import record_manual_action
                        record_manual_action({**audit_payload, "status": "success", "result": result})
                    except Exception:
                        pass
                except Exception as e:
                    error_text = str(e)
                    try:
                        from storage.manual_audit import record_manual_action
                        record_manual_action({**audit_payload, "status": "failed", "error": error_text})
                    except Exception:
                        pass
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": error_text}).encode())
                return

            # MT5 position actions: modify SL/TP or close
            if self.path.startswith("/api/mt5/position/modify") or self.path.startswith("/api/mt5/position/close"):
                if AGENT_MANAGER is None:
                    self.send_response(503); self.end_headers(); return
                content_len = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_len) if content_len else b""
                try:
                    data = json.loads(body.decode() or "{}")
                except Exception:
                    self.send_response(400); self.end_headers(); return
                ticket = data.get("ticket")
                if ticket is None:
                    self.send_response(400); self.end_headers(); return
                action_type = "modify" if self.path.startswith("/api/mt5/position/modify") else "close"
                audit_payload = {
                    "action": action_type,
                    "ticket": int(ticket),
                    "sl": data.get("sl"),
                    "tp": data.get("tp"),
                    "source": "dashboard",
                    "path": self.path,
                }
                try:
                    if action_type == "modify":
                        coro = AGENT_MANAGER.mt5.modify_position(
                            int(ticket),
                            float(data.get("sl") or 0),
                            float(data.get("tp") or 0),
                        )
                    else:
                        coro = AGENT_MANAGER.mt5.close_position(int(ticket))
                    fut = asyncio.run_coroutine_threadsafe(coro, _event_loop)
                    result = fut.result(timeout=15)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(json.dumps(result).encode())
                    try:
                        from storage.manual_audit import record_manual_action
                        record_manual_action({**audit_payload, "status": "success", "result": result})
                    except Exception:
                        pass
                except Exception as e:
                    error_text = str(e)
                    try:
                        from storage.manual_audit import record_manual_action
                        record_manual_action({**audit_payload, "status": "failed", "error": error_text})
                    except Exception:
                        pass
                    self.send_response(502)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": error_text}).encode())
                return

            # Toggle mode. Production requires an explicit deployment lock and token.
            if self.path.startswith("/api/mode"):
                content_len = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_len) if content_len else b""
                try:
                    data = json.loads(body.decode() or "{}")
                except Exception:
                    self.send_response(400)
                    self.end_headers()
                    return

                requested = data.get("mode")
                if requested not in ("paper", "demo", "live"):
                    self.send_response(400)
                    self.end_headers()
                    return

                if AGENT_MANAGER is None:
                    self.send_response(503)
                    self.end_headers()
                    return
                if requested == "live" and (
                    os.getenv("ALLOW_LIVE_MODE", "").lower() != "true"
                    or not os.getenv("LIVE_PROMOTION_TOKEN")
                    or data.get("promotion_token") != os.getenv("LIVE_PROMOTION_TOKEN")
                ):
                    self.send_response(403)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "live production mode is locked by readiness policy"}).encode())
                    return

                if requested != RUNTIME_MODE:
                    try:
                        positions = asyncio.run_coroutine_threadsafe(
                            AGENT_MANAGER.mt5.get_positions(), _event_loop
                        ).result(timeout=10)
                    except Exception:
                        positions = ["unknown"]
                    if positions:
                        self.send_response(409)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        self.wfile.write(json.dumps({"error": "cannot change mode while positions are open or unknown"}).encode())
                        return

                RUNTIME_MODE = requested
                AGENT_MANAGER.paper_mode = requested == "paper"
                for agent in getattr(AGENT_MANAGER, "agents", []):
                    agent.paper_mode = AGENT_MANAGER.paper_mode
                try:
                    loop = _event_loop
                    asyncio.run_coroutine_threadsafe(AGENT_MANAGER._update_account(), loop)
                    asyncio.run_coroutine_threadsafe(AGENT_MANAGER._load_recent_history(hours=48, limit=500), loop)
                except Exception:
                    pass

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"mode": "live"}).encode())
                return

            # Admin: force writing current state to disk
            if self.path.startswith("/api/write_state"):
                if AGENT_MANAGER is None:
                    self.send_response(503)
                    self.end_headers()
                    return
                try:
                    AGENT_MANAGER._write_state()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "written"}).encode())
                except Exception as e:
                    self.send_response(500)
                    self.end_headers()
                return

            # Delete order history item by ticket: POST /api/order_history/delete {"ticket":123}
            if self.path.startswith("/api/order_history/delete"):
                content_len = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_len) if content_len else b""
                try:
                    data = json.loads(body.decode() or "{}")
                except Exception:
                    self.send_response(400)
                    self.end_headers()
                    return
                ticket = data.get("ticket")
                if ticket is None:
                    self.send_response(400)
                    self.end_headers()
                    return
                try:
                    from storage.history_db import delete_by_ticket
                    deleted = delete_by_ticket(int(ticket))
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"deleted": deleted}).encode())
                except Exception:
                    self.send_response(500)
                    self.end_headers()
                return

            # SimpleHTTPRequestHandler has no do_POST; respond 404 for other POSTs
            self.send_response(404)
            self.end_headers()
            return

    # Use a threading server so multiple simultaneous browser requests don't block
    class ThreadingServer(socketserver.ThreadingTCPServer):
        allow_reuse_address = True

    with ThreadingServer((host, port), Handler) as httpd:
        httpd.daemon_threads = True
        logger.info(f"Dashboard serving at http://{host}:{port}")
        await asyncio.get_event_loop().run_in_executor(None, httpd.serve_forever)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MTAI Forex AI Trading System")
    parser.add_argument(
        "--mode",
        choices=["paper", "demo", "live"],
        default="paper",
        help="Trading mode: paper (simulate), demo (broker demo), or live (production)",
    )
    parser.add_argument(
        "--dashboard-port",
        type=int,
        default=3003,
        help="Starting port for serving the dashboard; uses the next available port if occupied",
    )
    parser.add_argument(
        "--dashboard-only",
        action="store_true",
        help="Start only the static dashboard without connecting to MT5",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host/address to bind the dashboard server (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--mt5-server",
        type=str,
        default=MT5_SERVER,
        help="MT5 API server URL for the Windows bridge",
    )
    parser.add_argument(
        "--mt5-ws",
        type=str,
        default=MT5_WS,
        help="WebSocket price feed URL for the Windows bridge",
    )
    parser.add_argument(
        "--dashboard-dir",
        type=str,
        default=None,
        help="Static dashboard directory to serve (defaults to built hedgefund client dist if available)",
    )
    args = parser.parse_args()
    try:
        asyncio.run(
            main(
                args.mode,
                args.dashboard_port,
                args.dashboard_only,
                args.host,
                args.mt5_server,
                args.mt5_ws,
                args.dashboard_dir,
            )
        )
    except KeyboardInterrupt:
        print("\n👋 MTAI stopped.")
