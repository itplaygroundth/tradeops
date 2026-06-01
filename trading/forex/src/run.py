"""
MTAI — Main Entry Point
รัน: python3 run.py [--mode paper|live]
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
    global AGENT_MANAGER
    AGENT_MANAGER = manager
    # Enforce live-only mode to prevent unstable toggling
    AGENT_MANAGER.paper_mode = False
    try:
        loop = asyncio.get_event_loop()
        asyncio.run_coroutine_threadsafe(AGENT_MANAGER._update_account(), loop)
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
            # MT5 open positions: /api/mt5/positions  → {"positions": [...]}
            if self.path.startswith("/api/mt5/positions"):
                if AGENT_MANAGER is None:
                    self.send_response(503); self.end_headers(); return
                try:
                    fut = asyncio.run_coroutine_threadsafe(
                        AGENT_MANAGER.mt5._client.get("/positions"), _event_loop
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
                    # Dashboard enforces live-only mode
                    mode = "live"
                    account = {"balance": AGENT_MANAGER._account_balance, "equity": AGENT_MANAGER._account_equity}
                self.wfile.write(json.dumps({"mode": mode, "account": account}).encode())
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
                # Export CSV for filtered query
                from urllib.parse import urlparse, parse_qs
                qs = parse_qs(urlparse(self.path).query)
                try:
                    offset = int(qs.get("offset", [0])[0])
                    limit = int(qs.get("limit", [1000])[0])
                except Exception:
                    offset = 0
                    limit = 1000
                symbol = qs.get("symbol", [None])[0]
                agent = qs.get("agent", [None])[0]
                status = qs.get("status", [None])[0]
                q = qs.get("q", [None])[0]
                try:
                    from storage.history_db import query_orders
                    res = query_orders(offset=offset, limit=limit, symbol=symbol, agent=agent, status=status, q=q)
                    items = res.get("items", [])
                    # build CSV
                    keys = ["timestamp","agent","symbol","action","volume","price","sl","tp","type","status","pnl","ticket","comment"]
                    lines = [",".join(keys)]
                    for it in items:
                        line = []
                        for k in keys:
                            v = it.get(k, "")
                            if v is None:
                                v = ""
                            s = str(v).replace('"', '""')
                            line.append(f'"{s}"')
                        lines.append(",".join(line)
                        )
                    csv = "\n".join(lines)
                    self.send_response(200)
                    self.send_header("Content-Type", "text/csv")
                    self.send_header("Content-Disposition", "attachment; filename=order_history.csv")
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
            # Toggle mode: POST /api/mode {"mode": "paper"|"live"}
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
                if requested not in ("paper", "live"):
                    self.send_response(400)
                    self.end_headers()
                    return

                if AGENT_MANAGER is None:
                    self.send_response(503)
                    self.end_headers()
                    return
                # Enforce live-only: reject attempts to set paper mode
                if requested == "paper":
                    self.send_response(403)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "paper mode disabled on this deployment"}).encode())
                    return

                # For live requests, ensure manager is live and update account
                AGENT_MANAGER.paper_mode = False
                try:
                    loop = _event_loop
                    asyncio.run_coroutine_threadsafe(AGENT_MANAGER._update_account(), loop)
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
        choices=["paper", "live"],
        default="paper",
        help="Trading mode: paper (simulate) or live (real orders)",
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
