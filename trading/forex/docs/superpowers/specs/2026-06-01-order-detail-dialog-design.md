# Order Detail Dialog with SL/TP/Close — Design

**Date:** 2026-06-01
**Status:** Approved (pending spec review)

## Goal

Click a row in the Order Book → open a dialog showing full position detail, with buttons to manually set SL/TP and close the position.

## Current state

- `useLiveState.js` polls `GET /api/mt5/positions` every 5s → `App` → `ChartTabs` → `OrderBook` (static, non-clickable table).
- MT5 bridge (`mt5_api_server.py`, Windows 192.168.1.107:8888) endpoints:
  - `POST /order` — new order (has sl/tp fields)
  - `GET /positions` — open positions
  - `DELETE /position/{ticket}` — close position (exists)
  - **No SL/TP modify endpoint** — must be added.
- `client.py` has `place_order`, `get_positions`, `close_position`. No `modify_position`.
- `run.py` proxies GETs to the bridge; `do_POST` handles `/api/mode`, `/api/write_state`, `/api/order_history/delete`. No position-action POST routes.

## Scope (approved)

- Actions: **Set SL/TP + Close**.
- SL/TP input: **direct price inputs**, prefilled with current values.
- MT5 bridge file will be edited; **user restarts the Windows server** to activate modify.

## Layers

### 1. MT5 bridge — `src/mt5_bridge/windows_server/mt5_api_server.py`

Add `PATCH /position/{ticket}` with body `{sl: float, tp: float}`:

```python
class ModifyRequest(BaseModel):
    sl: float = 0
    tp: float = 0

@app.patch("/position/{ticket}")
def modify_position(ticket: int, req: ModifyRequest):
    positions = mt5.positions_get(ticket=ticket)
    if not positions:
        raise HTTPException(404, f"Position {ticket} not found")
    pos = positions[0]
    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "symbol": pos.symbol,
        "position": int(ticket),
        "sl": float(req.sl),
        "tp": float(req.tp),
        "magic": int(pos.magic),
    }
    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        comment = result.comment if result else "unknown"
        retcode = result.retcode if result else -1
        raise HTTPException(400, f"Modify failed: {comment} (code {retcode})")
    return {"ticket": int(ticket), "sl": float(req.sl), "tp": float(req.tp)}
```

`sl=0` / `tp=0` clears that level (MT5 semantics). **Requires server restart.**

### 2. client — `src/mt5_bridge/client.py`

Add `modify_position` (close already exists):

```python
async def modify_position(self, ticket: int, sl: float = 0, tp: float = 0) -> dict:
    r = await self._client.patch(f"/position/{ticket}", json={"sl": sl, "tp": tp})
    r.raise_for_status()
    return r.json()
```

### 3. run.py proxy — `src/run.py` `do_POST`

Two new routes, each reading JSON body, dispatching to the manager's MT5 client on `_event_loop`, returning the bridge JSON (or 502 on error). Mirror existing `do_POST` handler style (Content-Length read, json.loads, `asyncio.run_coroutine_threadsafe(..., _event_loop)`, CORS header).

- `POST /api/mt5/position/modify` body `{ticket, sl, tp}` → `AGENT_MANAGER.mt5.modify_position(ticket, sl, tp)`
- `POST /api/mt5/position/close` body `{ticket}` → `AGENT_MANAGER.mt5.close_position(ticket)`

Guard: `AGENT_MANAGER is None` → 503; missing `ticket` → 400; bridge exception → 502 with `{error}`.

### 4. UI — `dashboard-ui/src/`

**`components/OrderBook.jsx`**
- Add `onSelect` prop. Each `<tr>` gets `onClick={() => onSelect(p)}` and `className` includes `ob-row` (cursor: pointer, hover highlight).

**`components/ChartTabs.jsx`**
- Hold `const [selected, setSelected] = useState(null)`.
- Pass `onSelect={setSelected}` to `OrderBook`.
- Render `<OrderDialog position={selected} onClose={() => setSelected(null)} onDone={refreshMT5} />` when `selected`.
- Receives `refreshMT5` via prop from `App`.

**`components/OrderDialog.jsx`** (new)
- Modal overlay (fixed, backdrop click → close). Inner card.
- Read-only detail block: symbol, side (BUY/SELL colored), lots, open price, bid/ask, current P&L, current SL, current TP. Uses same `priceDigits`/`fmt` helpers (extract to a shared spot or duplicate the small helpers — duplicate is fine, they're tiny).
- Two number inputs: **SL price**, **TP price**, prefilled from `position.sl` / `position.tp` (blank if 0).
- Buttons:
  - **Set SL/TP** → `POST /api/mt5/position/modify {ticket, sl, tp}` (empty input → 0). On success: `onDone()` then `onClose()`.
  - **Close Position** → two-step: first click flips button to **Confirm Close** (red); second click → `POST /api/mt5/position/close {ticket}`. On success: `onDone()` + `onClose()`.
  - **Cancel** → `onClose()`.
- Local state: `busy` (disables buttons during request), `err` (inline error text from response).

**`hooks/useLiveState.js`**
- Return `refreshMT5: fetchMT5` so an action can refresh positions immediately rather than waiting for the 5s poll.

**`App.jsx`**
- Destructure `refreshMT5` from `useLiveState()`, pass to `ChartTabs`.

**CSS** — add to existing stylesheet: `.ob-row` (pointer/hover), `.order-dialog-overlay`, `.order-dialog`, detail grid, input rows, button variants (primary/danger/confirm). Match existing dark dashboard theme (Binance-style: `#F0B90B` accent, `#0ECB81` buy, `#F6465D` sell/danger).

## Data flow (new action)

```
OrderDialog → POST /api/mt5/position/{modify|close}
  → run.py do_POST → AGENT_MANAGER.mt5.{modify,close}_position (on _event_loop)
    → bridge PATCH/DELETE /position/{ticket}
  → success → onDone() = refreshMT5() → GET /api/mt5/positions → table updates
```

## Error handling

- Each layer returns HTTP error with a message; UI surfaces `err` inline in the dialog, leaves it open so the user can retry.
- Buttons disabled while `busy`.
- Close is two-click (confirm) — irreversible, real money.

## Out of scope

- Editing volume / partial close.
- Pips-based quick-set (price input only this round).
- New order entry from the dialog (only modify/close of existing positions).

## Testing

- Bridge: with MT5 connected, `PATCH /position/{ticket}` with a known ticket sets SL/TP; verify in MT5 terminal.
- run.py proxy: `curl -X POST .../api/mt5/position/modify -d '{"ticket":...,"sl":...,"tp":...}'` returns bridge JSON.
- UI: click row → dialog opens with correct prefilled values; Set SL/TP updates table within a refresh; Close (two-click) removes the position; error path shows inline message.
