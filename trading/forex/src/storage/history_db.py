import sqlite3
from pathlib import Path
from typing import Dict, Any, List, Optional

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "history.db"

EXTRA_COLUMNS = {
    "deal_ticket": "INTEGER",
    "commission": "REAL DEFAULT 0",
    "swap": "REAL DEFAULT 0",
    "fees": "REAL DEFAULT 0",
    "deal_entry": "INTEGER",
    "deal_reason": "INTEGER",
    "exit_reason": "TEXT",
    "magic": "INTEGER",
}


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
    cur.execute("PRAGMA table_info(orders)")
    existing = {row[1] for row in cur.fetchall()}
    for column, spec in EXTRA_COLUMNS.items():
        if column not in existing:
            cur.execute(f"ALTER TABLE orders ADD COLUMN {column} {spec}")
    cur.execute("DROP INDEX IF EXISTS idx_orders_deal_ticket")
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_deal_ticket ON orders(deal_ticket)")
    conn.commit()
    conn.close()


def _order_values(entry: Dict[str, Any]) -> tuple:
    return (
        entry.get("deal_ticket"),
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
        float(entry.get("commission") or 0),
        float(entry.get("swap") or 0),
        float(entry.get("fees") or 0),
        entry.get("deal_entry"),
        entry.get("deal_reason"),
        entry.get("exit_reason"),
        entry.get("magic"),
    )


ORDER_COLUMNS = """
    deal_ticket, ts, agent, symbol, action, volume, price, sl, tp, type, status, ticket, pnl, comment,
    commission, swap, fees, deal_entry, deal_reason, exit_reason, magic
"""


def insert_order(entry: Dict[str, Any]) -> None:
    init_db()
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM orders WHERE deal_ticket = ?", (entry.get("deal_ticket"),))
    exists = cur.fetchone() is not None
    cur.execute(
        f"INSERT INTO orders ({ORDER_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        _order_values(entry),
    )
    conn.commit()
    conn.close()
    # publish to in-memory subscribers (SSE)
    try:
        from storage import pubsub
        pubsub.publish(entry)
    except Exception:
        pass


def upsert_order(entry: Dict[str, Any]) -> bool:
    """Insert or update a deal-backed row. Returns True when inserted."""
    if entry.get("deal_ticket") in (None, ""):
        insert_order(entry)
        return True

    init_db()
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM orders WHERE deal_ticket = ?", (entry.get("deal_ticket"),))
    exists = cur.fetchone() is not None
    cur.execute(
        f"""
        INSERT INTO orders ({ORDER_COLUMNS})
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(deal_ticket) DO UPDATE SET
            ts=excluded.ts,
            agent=excluded.agent,
            symbol=excluded.symbol,
            action=excluded.action,
            volume=excluded.volume,
            price=excluded.price,
            sl=excluded.sl,
            tp=excluded.tp,
            type=excluded.type,
            status=excluded.status,
            ticket=excluded.ticket,
            pnl=excluded.pnl,
            comment=excluded.comment,
            commission=excluded.commission,
            swap=excluded.swap,
            fees=excluded.fees,
            deal_entry=excluded.deal_entry,
            deal_reason=excluded.deal_reason,
            exit_reason=excluded.exit_reason,
            magic=excluded.magic
        """,
        _order_values(entry),
    )
    inserted = not exists
    conn.commit()
    conn.close()
    if inserted:
        try:
            from storage import pubsub
            pubsub.publish(entry)
        except Exception:
            pass
    return inserted


def delete_by_ticket(ticket: int) -> int:
    """Delete orders matching ticket. Returns number deleted."""
    init_db()
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute("DELETE FROM orders WHERE ticket = ?", (int(ticket),))
    cnt = cur.rowcount
    conn.commit()
    conn.close()
    return cnt


def query_orders(offset: int = 0, limit: int = 100, symbol: Optional[str] = None, agent: Optional[str] = None, status: Optional[str] = None, q: Optional[str] = None) -> Dict[str, Any]:
    init_db()
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

    sql = (
        "SELECT ts,agent,symbol,action,volume,price,sl,tp,type,status,ticket,pnl,comment,"
        f"deal_ticket,commission,swap,fees,deal_entry,deal_reason,exit_reason,magic FROM orders {where_sql} "
        "ORDER BY ts DESC LIMIT ? OFFSET ?"
    )
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
            "deal_ticket": r[13],
            "commission": r[14],
            "swap": r[15],
            "fees": r[16],
            "deal_entry": r[17],
            "deal_reason": r[18],
            "exit_reason": r[19],
            "magic": r[20],
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
