# Phase 5: Dashboard + Monitoring

> **Objective:** Dashboard แสดง live PnL, agent leaderboard, open trades  
> **Source:** ported จาก `ai-trading-live/dashboard-ui/` (React+Vite)  
> Port แค่ structure + data contracts — ไม่ต้อง copy ทุกไฟล์

---

## Task 5.1: Run Entry Point

**Files:**
- Create: `src/run.py`

```python
"""
MTAI — Main Entry Point
รัน: python3 run.py [--mode paper|live]
"""
import asyncio
import argparse
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

sys.path.insert(0, str(Path(__file__).parent))

from mt5_bridge.client import MT5Client
from mt5_bridge.feed import MT5Feed
from engine.agent_manager import ForexAgentManager

MT5_SERVER = "http://192.168.1.XXX:8888"  # ← ใส่ IP Windows machine
MT5_WS = "ws://192.168.1.XXX:8888/ws/prices"

async def main(mode: str = "paper"):
    paper = mode == "paper"
    print(f"🚀 MTAI Forex AI Trading — mode={mode}")

    # Connect MT5
    client = MT5Client(MT5_SERVER)
    try:
        health = await client.health()
        print(f"✅ MT5 connected: balance={health['balance']}")
    except Exception as e:
        print(f"❌ MT5 connection failed: {e}")
        print(f"   Make sure mt5_api_server.py is running on Windows at {MT5_SERVER}")
        return

    # Init agent manager
    manager = ForexAgentManager(client, paper_mode=paper, agent_count=25)
    print(f"✅ {len(manager.agents)} agents initialized")

    # Start price feed
    feed = MT5Feed(MT5_WS)
    feed.on_tick(manager.on_tick)

    print("📊 Dashboard: http://localhost:3003")
    print("Press Ctrl+C to stop\n")

    # Start dashboard server in background
    asyncio.create_task(start_dashboard())

    await feed.start()

async def start_dashboard():
    """Simple HTTP server for dashboard"""
    import http.server
    import socketserver
    import os
    os.chdir("dashboard")
    handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", 3003), handler) as httpd:
        await asyncio.get_event_loop().run_in_executor(None, httpd.serve_forever)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["paper", "live"], default="paper")
    args = parser.parse_args()
    asyncio.run(main(args.mode))
```

---

## Task 5.2: Dashboard HTML (Simple)

**Objective:** Static HTML dashboard ที่ poll `live_state.json` ทุก 2s  
(ไม่ต้อง React build ใน phase นี้ — เพิ่มทีหลัง)

**Files:**
- Create: `dashboard/index.html`

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>MTAI — Forex AI Trading</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { background: #000; color: #e0e0e0; font-family: 'JetBrains Mono', monospace; padding: 16px; }
    h1 { color: #00ff88; font-size: 20px; margin-bottom: 16px; }
    .stats { display: flex; gap: 16px; margin-bottom: 24px; }
    .stat-card {
      background: #0d0d12; border: 0.5px solid #333; border-radius: 8px;
      padding: 16px; min-width: 160px;
    }
    .stat-label { font-size: 11px; color: #666; margin-bottom: 4px; }
    .stat-value { font-size: 28px; font-weight: 800; }
    .up { color: #34c759; }
    .down { color: #ff3b30; }
    .neutral { color: #888; }
    table { width: 100%; border-collapse: collapse; }
    th { font-size: 11px; color: #666; text-align: left; padding: 6px 8px; border-bottom: 1px solid #222; }
    td { font-size: 12px; padding: 6px 8px; border-bottom: 0.5px solid #1a1a1a; }
    tr:hover { background: #0d0d12; }
    .mode-badge {
      display: inline-block; padding: 2px 8px; border-radius: 4px;
      font-size: 11px; font-weight: 700; margin-left: 8px;
    }
    .paper { background: #1a3a1a; color: #34c759; }
    .live { background: #3a1a1a; color: #ff3b30; }
  </style>
</head>
<body>
  <h1>⚡ MTAI Forex AI Trading <span id="mode-badge" class="mode-badge paper">PAPER</span></h1>

  <div class="stats">
    <div class="stat-card">
      <div class="stat-label">Balance</div>
      <div class="stat-value neutral" id="balance">—</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Equity</div>
      <div class="stat-value neutral" id="equity">—</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Total PnL</div>
      <div class="stat-value" id="total-pnl">—</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Avg Win Rate</div>
      <div class="stat-value neutral" id="win-rate">—</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Active Trades</div>
      <div class="stat-value neutral" id="active-trades">—</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Total Agents</div>
      <div class="stat-value neutral" id="total-agents">—</div>
    </div>
  </div>

  <table>
    <thead>
      <tr>
        <th>Agent</th><th>Symbol</th><th>Strategy</th>
        <th>Trades</th><th>Win%</th><th>PnL$</th><th>SL/TP pip</th><th>Status</th>
      </tr>
    </thead>
    <tbody id="agent-table"></tbody>
  </table>

  <div id="last-update" style="font-size:10px;color:#444;margin-top:12px;"></div>

<script>
async function refresh() {
  try {
    const r = await fetch(`live_state.json?_=${Date.now()}`);
    const d = await r.json();

    // Mode badge
    const badge = document.getElementById('mode-badge');
    badge.textContent = d.paper_mode ? 'PAPER' : 'LIVE';
    badge.className = `mode-badge ${d.paper_mode ? 'paper' : 'live'}`;

    // Stats
    document.getElementById('balance').textContent = '$' + (d.account?.balance || 0).toFixed(2);
    document.getElementById('equity').textContent = '$' + (d.account?.equity || 0).toFixed(2);

    const pnl = d.summary?.total_pnl || 0;
    const pnlEl = document.getElementById('total-pnl');
    pnlEl.textContent = (pnl >= 0 ? '+' : '') + '$' + pnl.toFixed(2);
    pnlEl.className = 'stat-value ' + (pnl > 0 ? 'up' : pnl < 0 ? 'down' : 'neutral');

    document.getElementById('win-rate').textContent = (d.summary?.avg_win_rate || 0).toFixed(1) + '%';
    document.getElementById('active-trades').textContent = d.summary?.active_agents || 0;
    document.getElementById('total-agents').textContent = d.summary?.total_agents || 0;

    // Agent table
    const tbody = document.getElementById('agent-table');
    tbody.innerHTML = (d.agents || [])
      .sort((a, b) => b.total_pnl - a.total_pnl)
      .map(a => `
        <tr>
          <td>${a.name}</td>
          <td>${a.symbol}</td>
          <td>${a.strategy}</td>
          <td>${a.trades}</td>
          <td class="${a.win_rate > 50 ? 'up' : 'down'}">${a.win_rate}%</td>
          <td class="${a.total_pnl > 0 ? 'up' : a.total_pnl < 0 ? 'down' : 'neutral'}">
            ${a.total_pnl >= 0 ? '+' : ''}$${a.total_pnl.toFixed(2)}
          </td>
          <td>${a.sl_pips}/${a.tp_pips}</td>
          <td>${a.in_trade ? '🟢 IN' : '⚪ —'}</td>
        </tr>`).join('');

    document.getElementById('last-update').textContent = 'Updated: ' + new Date().toLocaleTimeString();
  } catch(e) {
    // State file not ready yet
  }
}

refresh();
setInterval(refresh, 2000);
</script>
</body>
</html>
```

---

## Task 5.3: Systemd Service

**Files:**
- Create: `scripts/mtai.service`

```ini
[Unit]
Description=MTAI Forex AI Trading System
After=network-online.target

[Service]
Type=simple
User=alfred
WorkingDirectory=/home/alfred/mtai/src
ExecStart=/home/alfred/.hermes/hermes-agent/venv/bin/python3 /home/alfred/mtai/src/run.py --mode paper
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

```bash
# Install
sudo cp /home/alfred/mtai/scripts/mtai.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable mtai
sudo systemctl start mtai

# Monitor
sudo systemctl status mtai
journalctl -u mtai -f
```

---

## Phase 5 Checklist

- [ ] `python3 run.py --mode paper` รันได้ไม่ error
- [ ] Dashboard พร้อม `http://localhost:3003`
- [ ] `live_state.json` เขียนทุก 2s
- [ ] Dashboard แสดง agent table ถูกต้อง
- [ ] Systemd service start/restart ได้

---

## Dashboard Port Plan

**Phase 5 (now):** Simple HTML → `localhost:3003`  
**Phase 6 (later):** React+Vite port จาก `ai-trading-live/dashboard-ui/` → เปลี่ยน symbols จาก crypto → forex
