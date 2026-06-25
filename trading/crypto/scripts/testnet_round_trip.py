"""Minimal Binance Spot Testnet round-trip with fail-closed safety checks."""
import argparse
import asyncio
import json
import os
import time
import urllib.request

from exchange.binance import BinanceFeed


def control_status(url: str) -> dict:
    with urllib.request.urlopen(f"{url.rstrip('/')}/api/control/status", timeout=5) as response:
        return json.load(response)


def record_evidence(url: str, payload: dict) -> dict:
    body = json.dumps({"engineId": "crypto-ai", **payload}).encode()
    request = urllib.request.Request(
        f"{url.rstrip('/')}/api/live-readiness/round-trip/evidence",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


async def run(symbol: str, quote_limit: float, control_url: str) -> dict:
    if os.getenv("CONFIRM_TESTNET_ROUND_TRIP") != "YES":
        raise RuntimeError("CONFIRM_TESTNET_ROUND_TRIP=YES is required")
    status = control_status(control_url)
    if status.get("entries_paused") is not True:
        raise RuntimeError("autonomous entries must be paused")

    feed = BinanceFeed(mode="demo")
    if feed.network != "testnet":
        raise RuntimeError(f"refusing non-testnet network: {feed.network}")
    if not feed.supports_live_trading:
        raise RuntimeError("Testnet credentials are not configured")

    base_asset = symbol.removesuffix("USDT")
    run_id = str(int(time.time() * 1000))[-10:]
    buy_client_id = f"readiness-buy-{run_id}"
    sell_client_id = f"readiness-sell-{run_id}"
    result = {"network": feed.network, "symbol": symbol, "quoteLimit": quote_limit}
    try:
        account_before = await feed.get_account()
        if not account_before.get("can_trade"):
            raise RuntimeError("Binance Testnet account cannot trade")
        before_base = account_before.get("balances", {}).get(base_asset, {}).get("free", 0.0)

        tick = await feed.get_price(symbol)
        raw_qty = quote_limit / tick.ask
        quantity = await feed.normalize_quantity(symbol, raw_qty, tick.ask)
        expected_notional = float(quantity) * tick.ask
        if expected_notional > quote_limit * 1.01:
            raise RuntimeError("normalized quantity exceeds quote limit")

        common = {
            "symbol": symbol,
            "side": "BUY",
            "type": "MARKET",
            "quantity": quantity,
            "newClientOrderId": buy_client_id,
        }
        await feed.sync_time()
        await feed._json_request("POST", "/api/v3/order/test", common, signed=True)
        buy = await feed._json_request(
            "POST",
            "/api/v3/order",
            {**common, "newOrderRespType": "FULL"},
            signed=True,
        )

        account_after_buy = await feed.get_account()
        after_base = account_after_buy.get("balances", {}).get(base_asset, {}).get("free", 0.0)
        acquired = max(0.0, after_base - before_base)
        if acquired <= 0:
            raise RuntimeError("buy filled but no available base-asset delta was found")

        sell_tick = await feed.get_price(symbol)
        sell_quantity = await feed.normalize_quantity(symbol, acquired, sell_tick.bid)
        sell = await feed._json_request(
            "POST",
            "/api/v3/order",
            {
                "symbol": symbol,
                "side": "SELL",
                "type": "MARKET",
                "quantity": sell_quantity,
                "newClientOrderId": sell_client_id,
                "newOrderRespType": "FULL",
            },
            signed=True,
        )
        account_after = await feed.get_account()
        final_base = account_after.get("balances", {}).get(base_asset, {}).get("free", 0.0)
        result.update({
            "success": True,
            "orderTestPassed": True,
            "buy": {
                "orderId": buy.get("orderId"),
                "clientOrderId": buy.get("clientOrderId"),
                "status": buy.get("status"),
                "executedQty": buy.get("executedQty"),
                "quoteQty": buy.get("cummulativeQuoteQty"),
            },
            "sell": {
                "orderId": sell.get("orderId"),
                "clientOrderId": sell.get("clientOrderId"),
                "status": sell.get("status"),
                "executedQty": sell.get("executedQty"),
                "quoteQty": sell.get("cummulativeQuoteQty"),
            },
            "baseDeltaAfterCleanup": final_base - before_base,
        })
        return result
    finally:
        await feed.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--quote-limit", type=float, default=12.0)
    parser.add_argument("--control-url", default="http://127.0.0.1:3006")
    parser.add_argument("--readiness-url", default="http://127.0.0.1:5001")
    args = parser.parse_args()
    if args.quote_limit <= 0 or args.quote_limit > 15:
        raise SystemExit("quote-limit must be > 0 and <= 15 USDT")
    result = asyncio.run(run(args.symbol.upper(), args.quote_limit, args.control_url))
    result["evidence"] = record_evidence(args.readiness_url, result)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
