# MT5 Dashboard Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the hedgefund-repo dashboard to live MT5 data via a Windows Python bridge at `192.168.1.107:8888`.

**Architecture:** `server.js` adds `/api/mt5/*` proxy endpoints that forward to the MT5 bridge, caching the last successful response in memory. `App.jsx` polls these endpoints every 5 seconds and shows an offline banner when the bridge is unreachable.

**Tech Stack:** Node.js (Express), node-fetch, React (useState/useEffect), existing SQLite settings storage.

---

## File Map

| File | Change |
|------|--------|
| `server/server.js` | Add MT5 bridge URL constant, in-memory cache object, 5 proxy endpoints |
| `client/src/App.jsx` | Add MT5 state + polling, MT5 account section in Overview, Positions table in new tab, offline banner, order form wired to MT5 |

No new files. Changes are additive.

---

## Task 1: Add MT5 bridge config and cache to server.js

**Files:**
- Modify: `server/server.js` (after line 17, before `const db = ...`)

- [ ] **Step 1: Add MT5 bridge URL and in-memory cache**

Open `server/server.js`. After line 17 (`const PORT = 5001;`), insert:

```js
// MT5 Bridge
const MT5_BRIDGE_URL = 'http://192.168.1.107:8888';
const MT5_TIMEOUT_MS = 5000;
const mt5Cache = {}; // { [endpoint]: { data: {...}, cachedAt: ISO string } }

async function fetchMT5(path, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), MT5_TIMEOUT_MS);
  try {
    const res = await fetch(`${MT5_BRIDGE_URL}${path}`, { ...options, signal: controller.signal });
    clearTimeout(timer);
    if (!res.ok) throw new Error(`MT5 bridge ${res.status}`);
    const data = await res.json();
    mt5Cache[path] = { data, cachedAt: new Date().toISOString() };
    return { ...data, mt5_status: 'online', cached_at: mt5Cache[path].cachedAt };
  } catch (err) {
    clearTimeout(timer);
    if (mt5Cache[path]) {
      return { ...mt5Cache[path].data, mt5_status: 'offline', cached_at: mt5Cache[path].cachedAt };
    }
    return { mt5_status: 'offline', cached_at: null, error: err.message };
  }
}
```

- [ ] **Step 2: Commit**

```bash
cd /home/alfred/mtai/hedgefund-repo
git add server/server.js
git commit -m "feat: add MT5 bridge config and fetchMT5 helper"
```

---

## Task 2: Add /api/mt5/* proxy endpoints to server.js

**Files:**
- Modify: `server/server.js` (before `app.listen` at line 932)

- [ ] **Step 1: Add 5 MT5 endpoints**

Open `server/server.js`. Before `app.listen(PORT, ...)` (line 932), insert:

```js
// --- MT5 PROXY ENDPOINTS ---

app.get('/api/mt5/status', async (req, res) => {
  const data = await fetchMT5('/health');
  res.json(data);
});

app.get('/api/mt5/account', async (req, res) => {
  const data = await fetchMT5('/account');
  res.json(data);
});

app.get('/api/mt5/positions', async (req, res) => {
  const raw = await fetchMT5('/positions');
  // MT5 bridge returns { positions: [...] } when online
  const positions = raw.positions ?? (raw.mt5_status === 'offline' ? (mt5Cache['/positions']?.data?.positions ?? []) : []);
  res.json({ positions, mt5_status: raw.mt5_status, cached_at: raw.cached_at });
});

app.get('/api/mt5/price/:symbol', async (req, res) => {
  const data = await fetchMT5(`/price/${req.params.symbol}`);
  res.json(data);
});

app.post('/api/mt5/order', async (req, res) => {
  const { symbol, action, volume, sl = 0, tp = 0 } = req.body;
  if (!symbol || !action || !volume) {
    return res.status(400).json({ error: 'symbol, action, volume required' });
  }
  const data = await fetchMT5('/order', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ symbol, action, volume, sl, tp, comment: 'dashboard', magic: 20260528 })
  });
  if (data.mt5_status === 'offline') return res.status(503).json(data);
  res.json(data);
});
```

- [ ] **Step 2: Verify server starts without errors**

```bash
cd /home/alfred/mtai/hedgefund-repo/server
node server.js &
sleep 2
curl -s http://localhost:5001/api/mt5/status
# Expected: JSON with mt5_status field (either "online" or "offline")
kill %1
```

- [ ] **Step 3: Commit**

```bash
cd /home/alfred/mtai/hedgefund-repo
git add server/server.js
git commit -m "feat: add /api/mt5/* proxy endpoints"
```

---

## Task 3: Add MT5 state and polling to App.jsx

**Files:**
- Modify: `client/src/App.jsx`

- [ ] **Step 1: Add MT5 state variables**

In `App.jsx`, find the existing state declarations block (around line 10–35). Add after the last existing `useState`:

```jsx
const [mt5Account, setMt5Account] = useState(null);
const [mt5Positions, setMt5Positions] = useState([]);
const [mt5Status, setMt5Status] = useState('unknown'); // 'online' | 'offline' | 'unknown'
const [mt5CachedAt, setMt5CachedAt] = useState(null);
```

- [ ] **Step 2: Add polling useEffect**

In `App.jsx`, find the existing `useEffect` hooks block. Add a new effect:

```jsx
useEffect(() => {
  const pollMT5 = async () => {
    try {
      const [acctRes, posRes] = await Promise.all([
        fetch(`${API_BASE}/api/mt5/account`),
        fetch(`${API_BASE}/api/mt5/positions`)
      ]);
      const acct = await acctRes.json();
      const pos = await posRes.json();
      setMt5Account(acct);
      setMt5Positions(pos.positions ?? []);
      setMt5Status(acct.mt5_status ?? 'offline');
      setMt5CachedAt(acct.cached_at);
    } catch {
      setMt5Status('offline');
    }
  };
  pollMT5();
  const id = setInterval(pollMT5, 5000);
  return () => clearInterval(id);
}, []);
```

- [ ] **Step 3: Commit**

```bash
cd /home/alfred/mtai/hedgefund-repo
git add client/src/App.jsx
git commit -m "feat: add MT5 state and 5s polling"
```

---

## Task 4: Add MT5 offline banner

**Files:**
- Modify: `client/src/App.jsx`

- [ ] **Step 1: Add offline banner JSX**

In `App.jsx`, find the outermost return's opening `<div>`. After the first opening wrapper `<div>` (before the nav/tab bar), add:

```jsx
{mt5Status === 'offline' && (
  <div style={{
    background: '#7f1d1d', color: '#fca5a5',
    padding: '8px 16px', textAlign: 'center', fontSize: '13px',
    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px'
  }}>
    <AlertCircle size={14} />
    MT5 Offline — showing stale data
    {mt5CachedAt && ` (last updated: ${new Date(mt5CachedAt).toLocaleTimeString()})`}
  </div>
)}
```

Note: `AlertCircle` is already imported in `App.jsx`.

- [ ] **Step 2: Verify banner renders**

```bash
cd /home/alfred/mtai/hedgefund-repo/client
npm run dev &
# Open browser to http://localhost:5173
# With MT5 bridge offline, red banner should appear at top
```

- [ ] **Step 3: Commit**

```bash
cd /home/alfred/mtai/hedgefund-repo
git add client/src/App.jsx
git commit -m "feat: add MT5 offline banner"
```

---

## Task 5: Show MT5 account data in Overview tab

**Files:**
- Modify: `client/src/App.jsx`

- [ ] **Step 1: Add MT5 account section to Overview tab**

In `App.jsx`, find the Overview tab render section (look for `activeTab === 'overview'`). Add an MT5 account card block after the existing net worth summary cards:

```jsx
{mt5Account && mt5Status !== 'unknown' && (
  <div style={{ marginTop: '24px' }}>
    <h3 style={{ fontSize: '14px', color: '#9ca3af', marginBottom: '12px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
      MT5 Account
    </h3>
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '12px' }}>
      {[
        { label: 'Balance', value: mt5Account.balance },
        { label: 'Equity', value: mt5Account.equity },
        { label: 'Margin', value: mt5Account.margin },
        { label: 'Free Margin', value: mt5Account.margin_free },
        { label: 'Profit', value: mt5Account.profit },
      ].map(({ label, value }) => (
        <div key={label} style={{ background: '#1f2937', borderRadius: '8px', padding: '12px 16px' }}>
          <div style={{ fontSize: '12px', color: '#6b7280', marginBottom: '4px' }}>{label}</div>
          <div style={{ fontSize: '18px', fontWeight: '600', color: value >= 0 ? '#34d399' : '#f87171' }}>
            {value != null ? value.toFixed(2) : '—'}
          </div>
        </div>
      ))}
    </div>
  </div>
)}
```

- [ ] **Step 2: Commit**

```bash
cd /home/alfred/mtai/hedgefund-repo
git add client/src/App.jsx
git commit -m "feat: show MT5 account data in Overview tab"
```

---

## Task 6: Add MT5 Positions tab

**Files:**
- Modify: `client/src/App.jsx`

- [ ] **Step 1: Add 'mt5' to tab list**

In `App.jsx`, find the tab navigation array/list (look for `'overview'`, `'forex'`, etc.). Add `mt5` tab entry:

```jsx
{ id: 'mt5', label: 'MT5 Positions' }
```

Add it after the existing `forex` tab entry.

- [ ] **Step 2: Add MT5 Positions tab render**

In `App.jsx`, find the tab content switch/conditional block. Add a new section for `activeTab === 'mt5'`:

```jsx
{activeTab === 'mt5' && (
  <div>
    <h2 style={{ fontSize: '20px', fontWeight: '700', marginBottom: '16px' }}>MT5 Open Positions</h2>
    {mt5Positions.length === 0 ? (
      <div style={{ color: '#6b7280', textAlign: 'center', padding: '40px' }}>
        {mt5Status === 'offline' ? 'MT5 offline — no position data' : 'No open positions'}
      </div>
    ) : (
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '14px' }}>
        <thead>
          <tr style={{ color: '#6b7280', borderBottom: '1px solid #374151' }}>
            {['Ticket', 'Symbol', 'Type', 'Volume', 'Open Price', 'Current Price', 'SL', 'TP', 'P&L'].map(h => (
              <th key={h} style={{ padding: '8px 12px', textAlign: 'right', fontWeight: '500' }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {mt5Positions.map(pos => (
            <tr key={pos.ticket} style={{ borderBottom: '1px solid #1f2937' }}>
              <td style={{ padding: '8px 12px', textAlign: 'right', color: '#9ca3af' }}>{pos.ticket}</td>
              <td style={{ padding: '8px 12px', textAlign: 'right', fontWeight: '600' }}>{pos.symbol}</td>
              <td style={{ padding: '8px 12px', textAlign: 'right', color: pos.type === 0 ? '#34d399' : '#f87171' }}>
                {pos.type === 0 ? 'BUY' : 'SELL'}
              </td>
              <td style={{ padding: '8px 12px', textAlign: 'right' }}>{pos.volume}</td>
              <td style={{ padding: '8px 12px', textAlign: 'right' }}>{pos.price_open?.toFixed(5)}</td>
              <td style={{ padding: '8px 12px', textAlign: 'right' }}>{pos.price_current?.toFixed(5)}</td>
              <td style={{ padding: '8px 12px', textAlign: 'right', color: '#6b7280' }}>{pos.sl || '—'}</td>
              <td style={{ padding: '8px 12px', textAlign: 'right', color: '#6b7280' }}>{pos.tp || '—'}</td>
              <td style={{ padding: '8px 12px', textAlign: 'right', color: pos.profit >= 0 ? '#34d399' : '#f87171', fontWeight: '600' }}>
                {pos.profit?.toFixed(2)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    )}
  </div>
)}
```

- [ ] **Step 3: Commit**

```bash
cd /home/alfred/mtai/hedgefund-repo
git add client/src/App.jsx
git commit -m "feat: add MT5 Positions tab"
```

---

## Task 7: Wire forex order form to MT5

**Files:**
- Modify: `client/src/App.jsx`

- [ ] **Step 1: Find the transaction form submit handler**

In `App.jsx`, find the transaction form submit handler (look for `handleTransaction` or the `onSubmit` handler that calls `/api/portfolio/transaction`). It will check `txType`.

- [ ] **Step 2: Add MT5 branch for forex orders**

Inside the submit handler, before or after the existing `fetch('/api/portfolio/transaction', ...)` call, add a branch for forex type:

```jsx
if (txType === 'forex') {
  // Route forex orders to MT5
  if (mt5Status === 'offline') {
    setTxError('MT5 is offline — cannot place order');
    return;
  }
  try {
    const res = await fetch(`${API_BASE}/api/mt5/order`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        symbol: txAssetId,
        action: txAction === 'buy' ? 'buy' : 'sell',
        volume: parseFloat(txUnits),
      })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Order failed');
    setTxSuccess(true);
    setTxError('');
  } catch (err) {
    setTxError(err.message);
  }
  return; // don't also hit /api/portfolio/transaction for forex
}
```

- [ ] **Step 3: Disable order button when MT5 offline**

Find the transaction form submit button. Add `disabled` condition:

```jsx
disabled={txType === 'forex' && mt5Status === 'offline'}
title={txType === 'forex' && mt5Status === 'offline' ? 'MT5 offline — cannot place order' : undefined}
```

- [ ] **Step 4: Commit**

```bash
cd /home/alfred/mtai/hedgefund-repo
git add client/src/App.jsx
git commit -m "feat: route forex orders through MT5 bridge"
```

---

## Task 8: Manual end-to-end test

- [ ] **Step 1: Start server and dev client**

```bash
cd /home/alfred/mtai/hedgefund-repo/server && node server.js &
cd /home/alfred/mtai/hedgefund-repo/client && npm run dev &
```

- [ ] **Step 2: Test with MT5 bridge reachable**

Open `http://localhost:5173`. Check:
- Overview tab shows MT5 account cards (Balance, Equity, Margin, Free Margin, Profit)
- MT5 Positions tab shows open trades table (or "No open positions" if none)
- No offline banner visible

- [ ] **Step 3: Test with MT5 bridge unreachable**

Temporarily point bridge URL to a bad host to simulate offline:
```bash
# In server.js temporarily change MT5_BRIDGE_URL to 'http://192.168.1.107:9999'
# Restart server, reload browser
```
Check:
- Red offline banner appears at top with last-updated time
- MT5 account cards show last cached values
- Forex order button disabled with tooltip

- [ ] **Step 4: Restore correct URL and final commit**

```bash
# Revert MT5_BRIDGE_URL back to 'http://192.168.1.107:8888'
cd /home/alfred/mtai/hedgefund-repo
git add server/server.js
git commit -m "test: restore MT5 bridge URL after offline simulation"
```
