#!/usr/bin/env python3
"""GA throughput watcher — emits one line only when a milestone changes.

Tracks the 3 signals that confirm the GA started turning after MIN_TRADES 30->10:
  1. DB order count rising (market open -> trades happening)
  2. max trades_count per agent crossing 10 (judgment threshold reached)
  3. max agent id > 24 (evolution reassigned ids -> a cycle ran)

Prints a line to stdout ONLY on change, so it's safe to attach to a Monitor.
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "dashboard" / "live_state.json"
sys.path.insert(0, str(ROOT / "src"))

THRESHOLD = 10  # MIN_TRADES_BEFORE_JUDGMENT

def db_total():
    try:
        from storage.history_db import query_orders
        return query_orders(offset=0, limit=1).get("total", 0)
    except Exception:
        return -1

def state_metrics():
    try:
        d = json.loads(STATE.read_text())
        ag = d.get("agents", [])
        ids = [a.get("id", -1) for a in ag]
        tc = [a.get("trades_count", a.get("trades", 0)) for a in ag]
        return {
            "max_id": max(ids) if ids else -1,
            "max_trades": max(tc) if tc else 0,
            "ts": d.get("timestamp", 0),
        }
    except Exception:
        return {"max_id": -1, "max_trades": 0, "ts": 0}

def snapshot():
    m = state_metrics()
    m["db_total"] = db_total()
    return m

def fmt(m):
    age_h = (time.time() - m["ts"]) / 3600 if m["ts"] else -1
    return (f"db_orders={m['db_total']} max_trades={m['max_trades']}/{THRESHOLD} "
            f"max_agent_id={m['max_id']} state_age={age_h:.1f}h")

prev = snapshot()
print(f"[ga_watch {time.strftime('%Y-%m-%d %H:%M:%S')}] baseline: {fmt(prev)}", flush=True)

while True:
    time.sleep(120)  # poll every 2 min
    cur = snapshot()
    events = []
    if cur["db_total"] > prev["db_total"]:
        events.append(f"+{cur['db_total'] - prev['db_total']} new orders (total={cur['db_total']})")
    if cur["max_trades"] >= THRESHOLD > prev["max_trades"]:
        events.append(f"AGENT REACHED {THRESHOLD} TRADES (GA judgment now possible)")
    elif cur["max_trades"] > prev["max_trades"]:
        events.append(f"max_trades {prev['max_trades']}->{cur['max_trades']}")
    if cur["max_id"] > 24 >= prev["max_id"]:
        events.append(f"GA EVOLVED — agent ids reassigned (max_id={cur['max_id']})")
    elif cur["max_id"] > prev["max_id"]:
        events.append(f"max_agent_id {prev['max_id']}->{cur['max_id']} (evolution ran)")

    if events:
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[ga_watch {stamp}] {'; '.join(events)} | {fmt(cur)}", flush=True)
    prev = cur
