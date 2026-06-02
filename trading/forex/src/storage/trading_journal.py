import csv
import io
import json
import math
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from mt5_bridge.pip_calc import get_contract_size


INSTITUTIONAL_JOURNAL_FIELDS = [
    "trade_id",
    "ticket",
    "account_login",
    "account_currency",
    "venue",
    "asset_class",
    "symbol",
    "side",
    "strategy",
    "agent",
    "lifecycle_status",
    "entry_time_utc",
    "exit_time_utc",
    "holding_seconds",
    "quantity_lots",
    "contract_size",
    "entry_price",
    "exit_price",
    "stop_loss",
    "take_profit",
    "initial_risk_price",
    "notional_quote",
    "gross_pnl",
    "commission",
    "swap",
    "fees",
    "net_pnl",
    "r_multiple",
    "return_pct",
    "execution_source",
    "magic",
    "comment",
]


def _float(value: Any) -> Optional[float]:
    try:
        if value in (None, ""):
            return None
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return None
        return result
    except Exception:
        return None


def _timestamp(value: Any) -> Optional[float]:
    result = _float(value)
    return result if result and result > 0 else None


def _iso_utc(ts: Any) -> str:
    value = _timestamp(ts)
    if value is None:
        return ""
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _round(value: Optional[float], digits: int = 6) -> Any:
    if value is None:
        return ""
    return round(value, digits)


def _side(value: Any) -> str:
    text = str(value or "").upper()
    if text in ("LONG", "BUY", "0"):
        return "BUY"
    if text in ("SHORT", "SELL", "1"):
        return "SELL"
    return text


def _asset_class(symbol: str) -> str:
    upper = symbol.upper()
    if "XAU" in upper or "XAG" in upper:
        return "METAL"
    if len(upper) >= 6:
        return "FX"
    return "UNKNOWN"


def _pick_entry(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    for row in rows:
        status = str(row.get("status") or "").lower()
        if status in ("placed", "open"):
            return row
    return rows[0] if rows else {}


def _pick_exit(rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    closed = [
        row for row in rows
        if str(row.get("status") or "").lower() == "closed" or str(row.get("type") or "").lower() == "closed"
    ]
    if closed:
        return closed[-1]
    return None


def _trade_id(row: Dict[str, Any], index: int) -> str:
    ticket = row.get("ticket")
    if ticket not in (None, ""):
        return f"MT5-{ticket}"
    symbol = row.get("symbol") or "UNKNOWN"
    ts = int(_timestamp(row.get("timestamp")) or 0)
    return f"LOCAL-{symbol}-{ts}-{index}"


def build_institutional_journal(
    orders: Iterable[Dict[str, Any]],
    account: Optional[Dict[str, Any]] = None,
    venue: str = "MT5",
) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    loose_index = 0
    for row in sorted(list(orders), key=lambda item: _timestamp(item.get("timestamp")) or 0):
        ticket = row.get("ticket")
        if ticket in (None, ""):
            loose_index += 1
            key = f"loose-{loose_index}"
        else:
            key = str(ticket)
        grouped.setdefault(key, []).append(dict(row))

    account = account or {}
    result: List[Dict[str, Any]] = []
    for idx, rows in enumerate(grouped.values(), start=1):
        entry = _pick_entry(rows)
        exit_row = _pick_exit(rows)
        source = exit_row or entry

        symbol = str(source.get("symbol") or entry.get("symbol") or "")
        side = _side(entry.get("action") or source.get("action"))
        entry_time = _timestamp(entry.get("timestamp"))
        exit_time = _timestamp(exit_row.get("timestamp")) if exit_row else None
        entry_price = _float(entry.get("price"))
        exit_price = _float(exit_row.get("price")) if exit_row else None
        if exit_row and exit_price == entry_price and str(exit_row.get("type") or "").lower() == "closed":
            exit_price = None

        volume = _float(entry.get("volume")) or _float(source.get("volume"))
        sl = _float(entry.get("sl"))
        tp = _float(entry.get("tp"))
        contract_size = get_contract_size(symbol) if symbol else None
        risk_price = abs(entry_price - sl) if entry_price is not None and sl not in (None, 0) else None
        notional = entry_price * volume * contract_size if None not in (entry_price, volume, contract_size) else None

        net_pnl = _float(source.get("pnl"))
        commission = _float(source.get("commission")) or 0.0
        swap = _float(source.get("swap")) or 0.0
        fees = _float(source.get("fees"))
        if fees is None:
            fees = commission + swap
        gross_pnl = _float(source.get("gross_pnl"))
        if gross_pnl is None and net_pnl is not None:
            gross_pnl = net_pnl - fees

        r_multiple = None
        if None not in (entry_price, exit_price, risk_price) and risk_price and risk_price > 0 and side in ("BUY", "SELL"):
            signed_move = (exit_price - entry_price) if side == "BUY" else (entry_price - exit_price)
            r_multiple = signed_move / risk_price

        return_pct = (net_pnl / notional * 100.0) if net_pnl is not None and notional else None
        holding_seconds = int(exit_time - entry_time) if entry_time and exit_time and exit_time >= entry_time else ""

        status = "CLOSED" if exit_row else str(entry.get("status") or source.get("status") or "OPEN").upper()
        comment = source.get("comment") or entry.get("comment") or ""
        agent = source.get("agent") or entry.get("agent") or ""

        result.append({
            "trade_id": _trade_id(entry, idx),
            "ticket": entry.get("ticket") or source.get("ticket") or "",
            "account_login": account.get("login", ""),
            "account_currency": account.get("currency", ""),
            "venue": venue,
            "asset_class": _asset_class(symbol),
            "symbol": symbol,
            "side": side,
            "strategy": agent,
            "agent": agent,
            "lifecycle_status": status,
            "entry_time_utc": _iso_utc(entry_time),
            "exit_time_utc": _iso_utc(exit_time),
            "holding_seconds": holding_seconds,
            "quantity_lots": _round(volume, 4),
            "contract_size": _round(contract_size, 2),
            "entry_price": _round(entry_price, 6),
            "exit_price": _round(exit_price, 6),
            "stop_loss": _round(sl, 6),
            "take_profit": _round(tp, 6),
            "initial_risk_price": _round(risk_price, 6),
            "notional_quote": _round(notional, 2),
            "gross_pnl": _round(gross_pnl, 2),
            "commission": _round(commission, 2),
            "swap": _round(swap, 2),
            "fees": _round(fees, 2),
            "net_pnl": _round(net_pnl, 2),
            "r_multiple": _round(r_multiple, 4),
            "return_pct": _round(return_pct, 6),
            "execution_source": source.get("type") or entry.get("type") or "",
            "magic": source.get("magic") or entry.get("magic") or "",
            "comment": comment,
        })

    return sorted(result, key=lambda item: item.get("entry_time_utc") or "", reverse=True)


def journal_to_csv(rows: List[Dict[str, Any]]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=INSTITUTIONAL_JOURNAL_FIELDS, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return output.getvalue()


def journal_to_json(rows: List[Dict[str, Any]]) -> str:
    return json.dumps({"standard": "institutional_trade_journal_v1", "rows": rows}, indent=2)
