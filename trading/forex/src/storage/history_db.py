import sqlite3
from pathlib import Path
from typing import Dict, Any, List, Optional

DB_PATH = Path("data") / "history.db"


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL,
            agent TEXT,
            symbol TEXT,
            action TEXT,
            volume REAL,
            price REAL,
            sl REAL,
            tp REAL,
            type TEXT,
            status TEXT,
            ticket INTEGER,
            pnl REAL,
            comment TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def insert_order(entry: Dict[str, Any]) -> None:
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO orders (ts, agent, symbol, action, volume, price, sl, tp, type, status, ticket, pnl, comment)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            float(entry.get("timestamp", 0)),
            entry.get("agent"),
            entry.get("symbol"),
            entry.get("action"),
            float(entry.get("volume") or 0),
            float(entry.get("price") or 0),
            float(entry.get("sl") or 0),
            float(entry.get("tp") or 0),
            entry.get("type"),
            entry.get("status"),
            entry.get("ticket"),
            float(entry.get("pnl") or 0),
            entry.get("comment"),
        ),
    )
    conn.commit()
    conn.close()
    # publish to in-memory subscribers (SSE)
    try:
        from storage import pubsub
        pubsub.publish(entry)
    except Exception:
        pass


def delete_by_ticket(ticket: int) -> int:
    """Delete orders matching ticket. Returns number deleted."""
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute("DELETE FROM orders WHERE ticket = ?", (int(ticket),))
    cnt = cur.rowcount
    conn.commit()
    conn.close()
    return cnt


def query_orders(offset: int = 0, limit: int = 100, symbol: Optional[str] = None, agent: Optional[str] = None, status: Optional[str] = None, q: Optional[str] = None) -> Dict[str, Any]:
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    where = []
    params: List[Any] = []
    if symbol:
        where.append("symbol = ?")
        params.append(symbol)
    if agent:
        where.append("agent = ?")
        params.append(agent)
    if status:
        where.append("status = ?")
        params.append(status)
    if q:
        where.append("(agent LIKE ? OR symbol LIKE ? OR comment LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like, like])

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    total_q = f"SELECT COUNT(1) FROM orders {where_sql}"
    cur.execute(total_q, params)
    total = cur.fetchone()[0]

    sql = f"SELECT ts,agent,symbol,action,volume,price,sl,tp,type,status,ticket,pnl,comment FROM orders {where_sql} ORDER BY ts DESC LIMIT ? OFFSET ?"
    params2 = list(params) + [limit, offset]
    cur.execute(sql, params2)
    rows = cur.fetchall()
    items = []
    for r in rows:
        items.append({
            "timestamp": r[0],
            "agent": r[1],
            "symbol": r[2],
            "action": r[3],
            "volume": r[4],
            "price": r[5],
            "sl": r[6],
            "tp": r[7],
            "type": r[8],
            "status": r[9],
            "ticket": r[10],
            "pnl": r[11],
            "comment": r[12],
        })
    conn.close()
    return {"total": total, "offset": offset, "limit": limit, "items": items}


def query_orders_for_export(
    symbol: Optional[str] = None,
    agent: Optional[str] = None,
    status: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 10000,
) -> List[Dict[str, Any]]:
    """Return export-ready order rows in ascending time order."""
    result = query_orders(offset=0, limit=limit, symbol=symbol, agent=agent, status=status, q=q)
    return sorted(result.get("items", []), key=lambda item: float(item.get("timestamp") or 0))
