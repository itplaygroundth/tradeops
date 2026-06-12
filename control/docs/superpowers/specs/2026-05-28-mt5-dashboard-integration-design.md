# MT5 Dashboard Integration Design

**Date:** 2026-05-28  
**Scope:** Wire hedgefund-repo dashboard to live MT5 data via Windows bridge

---

## Overview

The current dashboard (`hedgefund-repo`) uses hardcoded seed data in `server.js`. This design wires it to a live MT5 MetaTrader 5 instance running on a Windows machine at `192.168.1.107:8888` via the existing Python bridge (`src/mt5_bridge/`).

---

## Architecture

```
App.jsx (React)
  → fetch every 5s
  → server.js :5001 (Node.js + SQLite)
  → HTTP proxy
  → 192.168.1.107:8888 (MT5 Bridge, Windows)
  → MetaTrader 5
```

`server.js` acts as a proxy — the frontend never calls the MT5 bridge directly. This keeps MT5's IP/port internal and allows server-side validation and caching.

---

## New Endpoints (server.js)

| Method | Path | MT5 Bridge call | Description |
|--------|------|-----------------|-------------|
| GET | `/api/mt5/status` | `GET /health` | Bridge online/offline |
| GET | `/api/mt5/account` | `GET /account` | Balance, equity, margin, profit |
| GET | `/api/mt5/positions` | `GET /positions` | Open positions list |
| GET | `/api/mt5/price/:symbol` | `GET /price/:symbol` | Live bid/ask |
| POST | `/api/mt5/order` | `POST /order` | Place buy/sell order |

All endpoints forward the MT5 bridge response with an added `mt5_status` field (`"online"` or `"offline"`) and `cached_at` timestamp.

---

## MT5 Bridge Configuration

- **URL:** `http://192.168.1.107:8888`
- **Configurable via:** `settings.json` key `mt5BridgeUrl` (fallback: hardcoded above)
- **Timeout:** 5 seconds per request

---

## Dashboard Changes (App.jsx)

1. **Overview tab** — replace hardcoded balance/equity with MT5 account data
2. **Forex tab** — replace external price API with `/api/mt5/price/:symbol`
3. **New MT5 Positions section** — table of open trades (symbol, volume, P&L, SL/TP)
4. **Transaction form** — route forex orders through `/api/mt5/order`
5. **Status bar** — MT5 connection indicator + "Last updated X seconds ago"

---

## Polling

- App.jsx polls `/api/mt5/account`, `/api/mt5/positions` every **5 seconds**
- Price polling per symbol on demand (when Forex tab is active)

---

## Offline / Fallback Handling

- `server.js` keeps an **in-memory cache** of the last successful MT5 response per endpoint
- If the bridge does not respond within 5s, return cached data with:
  ```json
  { "mt5_status": "offline", "cached_at": "<ISO timestamp>" }
  ```
- `App.jsx` shows a visible banner when `mt5_status === "offline"`:
  > ⚠ MT5 Offline — showing stale data (last updated: X min ago)
- Orders are **blocked** when MT5 is offline (button disabled + tooltip)

---

## Files Changed

| File | Change |
|------|--------|
| `server/server.js` | Add `/api/mt5/*` proxy endpoints + in-memory cache |
| `server/settings.json` | Add `mt5BridgeUrl` config key |
| `client/src/App.jsx` | Consume MT5 endpoints, add Positions section, status bar |

No new files needed — changes are additive to existing files.

---

## Out of Scope

- OHLCV / chart data (not requested)
- Deal history
- Crypto/funds data (remain on existing hardcoded/external feeds)
- Authentication on MT5 bridge endpoints
