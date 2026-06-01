"""
Crypto AI — backend entry point + HTTP API server.

Run: python3 src/run.py [--mode paper|live] [--exchange binance|bybit]

The dashboard/static client polls /live_state.json and the /api/* routes.
CRITICAL: asyncio.get_event_loop() fails inside HTTP request threads, so the
running loop is captured once in build_server() and reused via
asyncio.run_coroutine_threadsafe(coro, loop) from every handler.
"""
import argparse
import asyncio
import json
import logging
import os
import socketserver
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from exchange.router import ExchangeRouter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("run")

# Global manager reference so handlers/state-writer can reach it.
AGENT_MANAGER = None

ROOT = Path(__file__).parent.parent
DEFAULT_PAIRS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]


def build_server(host, port, router, manager, dashboard_dir, loop):
    """Construct (but do not start) a ThreadingHTTPServer wired to router/manager.

    `loop` is the asyncio event loop running on the main thread; handlers
    schedule coroutines onto it via run_coroutine_threadsafe.
    """
    global AGENT_MANAGER
    AGENT_MANAGER = manager
    _event_loop = loop
    static_dir = Path(dashboard_dir)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        # ---- helpers ----------------------------------------------------
        def _json(self, obj, status=200):
            body = json.dumps(obj).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_body(self):
            n = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(n) if n else b""
            try:
                return json.loads(raw.decode() or "{}")
            except Exception:
                return {}

        def _await(self, coro, timeout=15):
            fut = asyncio.run_coroutine_threadsafe(coro, _event_loop)
            return fut.result(timeout=timeout)

        # ---- GET --------------------------------------------------------
        def do_GET(self):
            parsed = urlparse(self.path)
            path = parsed.path
            qs = parse_qs(parsed.query)

            if path == "/live_state.json":
                state = manager.to_state_dict() if manager is not None else {}
                self._json(state)
                return

            if path == "/api/mode":
                mode = "paper" if router.paper_mode else "live"
                if manager is not None:
                    account = {
                        "balance": manager._account_balance,
                        "equity": manager._account_equity,
                    }
                else:
                    account = {"balance": 0.0, "equity": 0.0}
                self._json({"mode": mode, "account": account})
                return

            if path == "/api/exchange":
                self._json({"exchange": router.exchange_name})
                return

            if path == "/api/pairs":
                pairs = list(manager.pairs) if manager is not None else []
                self._json({"pairs": pairs})
                return

            if path == "/api/account":
                if manager is not None:
                    self._json({
                        "balance": manager._account_balance,
                        "equity": manager._account_equity,
                    })
                else:
                    self._json({"balance": 0.0, "equity": 0.0})
                return

            if path == "/api/positions":
                try:
                    positions = self._await(router.get_positions())
                except Exception as e:
                    self._json({"error": str(e)}, status=502)
                    return
                self._json({"positions": positions})
                return

            if path.startswith("/api/ohlcv/"):
                symbol = path.split("/api/ohlcv/", 1)[1].strip("/")
                timeframe = qs.get("timeframe", ["M15"])[0]
                count = int(qs.get("count", ["200"])[0])
                try:
                    data = self._await(
                        router.get_ohlcv(symbol, timeframe=timeframe, count=count)
                    )
                except Exception as e:
                    self._json({"error": str(e)}, status=502)
                    return
                self._json(data)
                return

            if path == "/api/order_history":
                offset = int(qs.get("offset", ["0"])[0])
                limit = int(qs.get("limit", ["100"])[0])
                symbol = qs.get("symbol", [None])[0]
                agent = qs.get("agent", [None])[0]
                status = qs.get("status", [None])[0]
                q = qs.get("q", [None])[0]
                try:
                    from storage.history_db import query_orders
                    res = query_orders(offset=offset, limit=limit, symbol=symbol,
                                       agent=agent, status=status, q=q)
                    self._json(res)
                except Exception as e:
                    self._json({"error": str(e)}, status=500)
                return

            # static file fallback
            self._serve_static(path)

        # ---- POST -------------------------------------------------------
        def do_POST(self):
            path = urlparse(self.path).path
            data = self._read_body()

            if path == "/api/mode":
                mode = data.get("mode")
                if mode not in ("paper", "live"):
                    self._json({"error": "invalid mode"}, status=400)
                    return
                paper = mode == "paper"
                router.set_mode(paper)
                if manager is not None:
                    manager.paper_mode = paper
                self._json({"mode": mode})
                return

            if path == "/api/exchange":
                exchange = data.get("exchange")
                try:
                    self._await(router.switch_exchange(exchange))
                except Exception as e:
                    self._json({"error": str(e)}, status=400)
                    return
                self._json({"exchange": router.exchange_name})
                return

            if path == "/api/pairs":
                symbol = data.get("symbol")
                if not symbol:
                    self._json({"error": "symbol required"}, status=400)
                    return
                if manager is not None:
                    manager.add_pair(symbol.upper())
                self._json({"pairs": list(manager.pairs) if manager else []})
                return

            self._json({"error": "not found"}, status=404)

        # ---- DELETE -----------------------------------------------------
        def do_DELETE(self):
            parsed = urlparse(self.path)
            path = parsed.path
            qs = parse_qs(parsed.query)

            if path == "/api/pairs":
                data = self._read_body()
                symbol = data.get("symbol") or qs.get("symbol", [None])[0]
                if not symbol:
                    self._json({"error": "symbol required"}, status=400)
                    return
                if manager is not None:
                    manager.remove_pair(symbol.upper())
                self._json({"pairs": list(manager.pairs) if manager else []})
                return

            self._json({"error": "not found"}, status=404)

        # ---- static -----------------------------------------------------
        def _serve_static(self, path):
            rel = path.lstrip("/") or "index.html"
            target = (static_dir / rel).resolve()
            try:
                target.relative_to(static_dir.resolve())
            except ValueError:
                self._json({"error": "forbidden"}, status=403)
                return
            if not target.is_file():
                self._json({"error": "not found"}, status=404)
                return
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(target.read_bytes())

    class ThreadingServer(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    return ThreadingServer((host, port), Handler)


async def main():
    parser = argparse.ArgumentParser(description="Crypto AI backend")
    parser.add_argument("--mode", choices=["paper", "live"],
                        default=os.getenv("MODE", "paper"))
    parser.add_argument("--exchange", choices=["binance", "bybit"],
                        default=os.getenv("EXCHANGE", "binance"))
    args = parser.parse_args()

    paper = args.mode == "paper"
    router = ExchangeRouter(exchange=args.exchange, paper_mode=paper)

    global AGENT_MANAGER
    manager = None
    try:
        from engine.agent_manager import CryptoAgentManager
        manager = CryptoAgentManager(router, paper_mode=paper)
    except ImportError as e:
        logger.warning(f"engine unavailable, serving API only: {e}")
    AGENT_MANAGER = manager

    if manager is not None:
        router.set_tick_callback(manager.on_tick)

    host = "0.0.0.0"
    port = int(os.getenv("DASHBOARD_PORT", "3006"))
    dashboard_dir = ROOT / "dashboard"
    dashboard_dir.mkdir(parents=True, exist_ok=True)

    loop = asyncio.get_event_loop()
    httpd = build_server(host, port, router, manager, str(dashboard_dir), loop)
    import threading
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    logger.info(f"API server on http://{host}:{port}")

    pairs = manager.pairs if manager is not None else DEFAULT_PAIRS
    await router.subscribe(pairs)
    logger.info(f"Subscribed to {pairs} on {router.exchange_name} (mode={args.mode})")

    state_path = dashboard_dir / "live_state.json"
    while True:
        try:
            if AGENT_MANAGER is not None:
                state_path.write_text(json.dumps(AGENT_MANAGER.to_state_dict()))
        except Exception as e:
            logger.warning(f"state write failed: {e}")
        await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())
