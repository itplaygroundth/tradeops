from collections import defaultdict
from typing import Any, Dict, Iterable, List


def _float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def _bucket(rows: Iterable[Dict[str, Any]], key: str) -> Dict[str, Dict[str, Any]]:
    buckets: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "trades": 0,
        "wins": 0,
        "losses": 0,
        "net_pnl": 0.0,
        "gross_win": 0.0,
        "gross_loss": 0.0,
    })
    for row in rows:
        name = str(row.get(key) or "UNKNOWN")
        pnl = _float(row.get("net_pnl"))
        b = buckets[name]
        b["trades"] += 1
        b["net_pnl"] += pnl
        if pnl > 0:
            b["wins"] += 1
            b["gross_win"] += pnl
        elif pnl < 0:
            b["losses"] += 1
            b["gross_loss"] += abs(pnl)
    return {name: _finalize_bucket(bucket) for name, bucket in sorted(buckets.items())}


def _finalize_bucket(bucket: Dict[str, Any]) -> Dict[str, Any]:
    trades = int(bucket["trades"])
    wins = int(bucket["wins"])
    losses = int(bucket["losses"])
    avg_win = bucket["gross_win"] / wins if wins else 0.0
    avg_loss = bucket["gross_loss"] / losses if losses else 0.0
    expectancy = bucket["net_pnl"] / trades if trades else 0.0
    profit_factor = bucket["gross_win"] / bucket["gross_loss"] if bucket["gross_loss"] else (None if wins else 0.0)
    return {
        "trades": trades,
        "wins": wins,
        "losses": losses,
        "win_rate": round((wins / trades * 100.0) if trades else 0.0, 2),
        "net_pnl": round(bucket["net_pnl"], 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "expectancy": round(expectancy, 4),
        "profit_factor": None if profit_factor is None else round(profit_factor, 3),
    }


def _recommendations(by_symbol: Dict[str, Dict[str, Any]], min_trades: int) -> List[str]:
    recs: List[str] = []
    for symbol, stats in sorted(by_symbol.items(), key=lambda item: item[1]["expectancy"]):
        if stats["trades"] < min_trades:
            continue
        if stats["expectancy"] < 0:
            recs.append(
                f"reduce_or_block {symbol}: expectancy {stats['expectancy']:.4f}, "
                f"win_rate {stats['win_rate']:.1f}%, trades {stats['trades']}"
            )
    for symbol, stats in sorted(by_symbol.items(), key=lambda item: item[1]["expectancy"], reverse=True):
        if stats["trades"] < min_trades:
            continue
        if stats["expectancy"] > 0 and stats["profit_factor"] and stats["profit_factor"] >= 1.2:
            recs.append(
                f"prefer {symbol}: expectancy {stats['expectancy']:.4f}, "
                f"profit_factor {stats['profit_factor']:.2f}, trades {stats['trades']}"
            )
    if not recs:
        recs.append(f"collect_more_data: no bucket has at least {min_trades} decisive trades with clear edge")
    return recs[:12]


def analyze_journal(rows: Iterable[Dict[str, Any]], min_trades: int = 3) -> Dict[str, Any]:
    closed = [
        row for row in rows
        if str(row.get("lifecycle_status") or "").lower() == "closed"
        or row.get("exit_time_utc")
        or _float(row.get("net_pnl")) != 0.0
    ]
    total = _finalize_bucket({
        "trades": len(closed),
        "wins": sum(1 for row in closed if _float(row.get("net_pnl")) > 0),
        "losses": sum(1 for row in closed if _float(row.get("net_pnl")) < 0),
        "net_pnl": sum(_float(row.get("net_pnl")) for row in closed),
        "gross_win": sum(_float(row.get("net_pnl")) for row in closed if _float(row.get("net_pnl")) > 0),
        "gross_loss": sum(abs(_float(row.get("net_pnl"))) for row in closed if _float(row.get("net_pnl")) < 0),
    })
    by_symbol = _bucket(closed, "symbol")
    return {
        "total": total,
        "by_symbol": by_symbol,
        "by_agent": _bucket(closed, "agent"),
        "by_exit_reason": _bucket(closed, "exit_reason"),
        "recommendations": _recommendations(by_symbol, min_trades=min_trades),
    }
