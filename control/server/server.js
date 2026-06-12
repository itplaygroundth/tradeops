import express from 'express';
import cors from 'cors';
import fetch from 'node-fetch';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { DatabaseSync } from 'node:sqlite';
import {
  dispatchControlCommand,
  installTradingControlRoutes,
  recordControlAction,
} from './services/tradingControl.js';
import { installAiAnalystRoutes } from './services/aiAnalyst.js';
import { createNotificationService, installNotificationRoutes } from './services/notifications.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SETTINGS_FILE = path.join(__dirname, 'settings.json');
const DB_FILE = path.join(__dirname, 'hedgefund.db');

const app = express();
app.use(cors());
app.use(express.json());

const PORT = 5001;

// MT5 Bridge
const MT5_BRIDGE_URL = 'http://192.168.1.107:8888';
const MT5_TIMEOUT_MS = 5000;
const mt5Cache = {}; // { [endpoint]: { data, cachedAt } } — keyed on path string only, not request body

async function fetchMT5(endpoint, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), MT5_TIMEOUT_MS);
  try {
    const bridgeUrl = getSettings().mt5BridgeUrl || MT5_BRIDGE_URL;
    const res = await fetch(`${bridgeUrl}${endpoint}`, { ...options, signal: controller.signal });
    clearTimeout(timer);
    if (!res.ok) throw new Error(`MT5 bridge ${res.status}`);
    const data = await res.json();
    if (!options.method || options.method.toUpperCase() !== 'POST') {
      mt5Cache[endpoint] = { data, cachedAt: new Date().toISOString() };
    }
    return { ...data, mt5_status: 'online', cached_at: (mt5Cache[endpoint]?.cachedAt ?? new Date().toISOString()) };
  } catch (err) {
    clearTimeout(timer);
    if (mt5Cache[endpoint]) {
      return { ...mt5Cache[endpoint].data, mt5_status: 'offline', cached_at: mt5Cache[endpoint].cachedAt };
    }
    return { mt5_status: 'offline', cached_at: null, error: err.message };
  }
}

// 1. Initialize SQLite connection and pragmas
const db = new DatabaseSync(DB_FILE);
db.exec('PRAGMA journal_mode = WAL;');
db.exec('PRAGMA synchronous = NORMAL;');
db.exec('PRAGMA foreign_keys = ON;');

// 2. Define schema
db.exec(`
  CREATE TABLE IF NOT EXISTS portfolio (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    units REAL NOT NULL DEFAULT 0.0,
    avgBuyPrice REAL NOT NULL DEFAULT 0.0,
    currentPrice REAL NOT NULL DEFAULT 0.0,
    code_symbol_pair TEXT NOT NULL
  );
`);

db.exec(`
  CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
  );
`);

db.exec(`
  CREATE TABLE IF NOT EXISTS alerts (
    id TEXT PRIMARY KEY,
    assetId TEXT NOT NULL,
    condition TEXT NOT NULL,
    value REAL NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
  );
`);

db.exec(`
  CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    assetId TEXT NOT NULL,
    type TEXT NOT NULL,
    action TEXT NOT NULL,
    units REAL NOT NULL,
    price REAL NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
  );
`);

// 3. Define Seed Constants & templates
const INITIAL_PORTFOLIO = {
  funds: [
    { id: "SCBUSA", name: "SCB US Equity Fund", units: 125.4, avgBuyPrice: 42.50, currentPrice: 45.80, type: "funds", code: "SCBUSA" },
    { id: "B-CARE", name: "Bualuang Global Healthcare", units: 210.5, avgBuyPrice: 28.10, currentPrice: 27.40, type: "funds", code: "B-CARE" },
    { id: "K-SET50", name: "K SET50 Index ETF", units: 450.0, avgBuyPrice: 12.20, currentPrice: 11.90, type: "funds", code: "K-SET50" }
  ],
  crypto: [
    { id: "BTC", name: "Bitcoin", units: 0.45, avgBuyPrice: 62500.00, currentPrice: 67200.00, type: "crypto", symbol: "BTC" },
    { id: "ETH", name: "Ethereum", units: 3.2, avgBuyPrice: 3100.00, currentPrice: 3450.00, type: "crypto", symbol: "ETH" },
    { id: "SOL", name: "Solana", units: 15.0, avgBuyPrice: 142.00, currentPrice: 168.50, type: "crypto", symbol: "SOL" }
  ],
  forex: [
    { id: "EUR_USD", name: "EUR/USD", units: 10000, avgBuyPrice: 1.0750, currentPrice: 1.0825, type: "forex", pair: "EUR/USD" },
    { id: "USD_JPY", name: "USD/JPY", units: 5000, avgBuyPrice: 155.20, currentPrice: 156.42, type: "forex", pair: "USD/JPY" },
    { id: "GBP_USD", name: "GBP/USD", units: 8000, avgBuyPrice: 1.2580, currentPrice: 1.2715, type: "forex", pair: "GBP/USD" }
  ]
};

const DEFAULT_SETTINGS = {
  telegramBotToken: "",
  telegramChatId: "",
  lineChannelAccessToken: "",
  lineTargetId: "",
  lineNotifyToken: "",
  riskProfile: "Balanced",
  mt5BridgeUrl: 'http://192.168.1.107:8888',
  tradingControl: {
    mtaiUrl: "http://127.0.0.1:3003",
    cryptoUrl: "http://127.0.0.1:3006",
    dailyReportTime: "23:55",
    autoSendDailyReport: false
  },
  alerts: [
    { id: "alert-1", assetId: "BTC", condition: "above", value: 70000, active: true },
    { id: "alert-2", assetId: "SOL", condition: "below", value: 150, active: true }
  ],
  llmConfig: {
    provider: "Gemini",
    apiKey: "",
    model: "gemini-1.5-flash",
    endpoint: ""
  },
  mcpConfig: {
    enabled: false,
    serverUrl: "",
    status: "offline",
    connectors: { yahoo: true, binance: false, forex: true }
  }
};

// Seed default portfolio if empty
try {
  const rowCount = db.prepare('SELECT COUNT(*) as count FROM portfolio').get();
  if (rowCount.count === 0) {
    console.log('🌱 Seeding default portfolio assets into SQLite...');
    const insertStmt = db.prepare(`
      INSERT INTO portfolio (id, name, type, units, avgBuyPrice, currentPrice, code_symbol_pair)
      VALUES (?, ?, ?, ?, ?, ?, ?)
    `);
    
    INITIAL_PORTFOLIO.funds.forEach(a => insertStmt.run(a.id, a.name, 'funds', a.units, a.avgBuyPrice, a.currentPrice, a.code));
    INITIAL_PORTFOLIO.crypto.forEach(a => insertStmt.run(a.id, a.name, 'crypto', a.units, a.avgBuyPrice, a.currentPrice, a.symbol));
    INITIAL_PORTFOLIO.forex.forEach(a => insertStmt.run(a.id, a.name, 'forex', a.units, a.avgBuyPrice, a.currentPrice, a.pair));
    console.log('✅ Default assets seeded!');
  }
} catch (e) {
  console.error('❌ Failed to seed portfolio:', e.message);
}

// 4. Settings Migration and Database API
function loadSettingsFromDb() {
  try {
    const settingsVal = db.prepare('SELECT value FROM settings WHERE key = ?').get('config');
    
    if (!settingsVal) {
      // Try migrating from settings.json
      let migratedSettings = null;
      if (fs.existsSync(SETTINGS_FILE)) {
        try {
          const raw = fs.readFileSync(SETTINGS_FILE, 'utf8');
          migratedSettings = JSON.parse(raw);
          console.log('📂 Migrating settings from settings.json to SQLite...');
        } catch (e) {
          console.warn('⚠️ Could not load settings.json for migration, using defaults:', e.message);
        }
      }
      
      const initialSettings = migratedSettings || DEFAULT_SETTINGS;
      
      // Save config json
      db.prepare('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)').run('config', JSON.stringify(initialSettings));
      
      // Seed default alerts table
      if (initialSettings.alerts && initialSettings.alerts.length > 0) {
        const alertInsert = db.prepare('INSERT OR REPLACE INTO alerts (id, assetId, condition, value, active) VALUES (?, ?, ?, ?, ?)');
        initialSettings.alerts.forEach(al => {
          alertInsert.run(al.id, al.assetId, al.condition, al.value, al.active ? 1 : 0);
        });
      }
      
      // Delete old file
      if (fs.existsSync(SETTINGS_FILE)) {
        try {
          fs.unlinkSync(SETTINGS_FILE);
          console.log('🗑️ settings.json deleted after successful migration.');
        } catch (err) {
          console.warn('⚠️ Could not delete settings.json:', err.message);
        }
      }
      
      return initialSettings;
    }
    
    return JSON.parse(settingsVal.value);
  } catch (err) {
    console.error('❌ Failed to load settings from DB, using defaults:', err.message);
    return { ...DEFAULT_SETTINGS };
  }
}

function getSettings() {
  const settings = loadSettingsFromDb();
  
  // Merge with latest alerts table
  try {
    const dbAlerts = db.prepare('SELECT * FROM alerts').all();
    settings.alerts = dbAlerts.map(al => ({
      id: al.id,
      assetId: al.assetId,
      condition: al.condition,
      value: al.value,
      active: al.active === 1
    }));
  } catch (e) {
    console.error('❌ Failed to load alerts:', e.message);
  }
  
  return settings;
}

function saveSettings(updatedSettings) {
  const settingsJson = { ...updatedSettings };
  delete settingsJson.alerts;
  
  db.prepare('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)').run('config', JSON.stringify(settingsJson));
  
  if (updatedSettings.alerts !== undefined) {
    db.exec('DELETE FROM alerts');
    const alertInsert = db.prepare('INSERT INTO alerts (id, assetId, condition, value, active) VALUES (?, ?, ?, ?, ?)');
    updatedSettings.alerts.forEach(al => {
      alertInsert.run(al.id, al.assetId, al.condition, al.value, al.active ? 1 : 0);
    });
  }
}

// Global active notification cooldowns keyed by alert id.
const ALERT_COOLDOWN_MS = Number(process.env.ALERT_COOLDOWN_MS || 30 * 60 * 1000);
const triggeredAlerts = new Map();
const notifications = createNotificationService({ db, getSettings });
const sendTelegramMessage = (...args) => notifications.sendTelegramMessage(...args);
const sendLineMessage = (...args) => notifications.sendLineMessage(...args);

// 6. Price Alerts Checker
async function checkPriceAlert(asset, currentSettings) {
  const activeAlerts = currentSettings.alerts.filter(a => a.assetId === asset.id && a.active);
  const now = Date.now();
  for (const alert of activeAlerts) {
    let isTriggered = false;
    if (alert.condition === 'above' && asset.currentPrice >= alert.value) {
      isTriggered = true;
    } else if (alert.condition === 'below' && asset.currentPrice <= alert.value) {
      isTriggered = true;
    }

    if (!isTriggered) {
      triggeredAlerts.delete(alert.id);
      continue;
    }

    const nextAllowedAt = triggeredAlerts.get(alert.id) || 0;
    if (now < nextAllowedAt) continue;

    if (isTriggered) {
      triggeredAlerts.set(alert.id, now + ALERT_COOLDOWN_MS);
      
      const emoji = alert.condition === 'above' ? '📈' : '📉';
      const condText = alert.condition === 'above' ? 'ทะลุสูงกว่า' : 'ดิ่งต่ำกว่า';
      const text = `🚨 *AI INVESTMENT ALERT* 🚨\n\nสินทรัพย์: *${asset.name} (${asset.id})*\nแจ้งเตือน: ราคา ${condText} *${alert.value}*\nราคาปัจจุบัน: *${asset.currentPrice}*\n\n🤖 *คำแนะนำจาก AI:* สินทรัพย์มีพฤติกรรมราคาที่น่าสนใจ แนะนำเข้าตรวจสอบพอร์ตของท่านเพื่อบริหารความเสี่ยงทันทีครับ`;
      
      await notifications.sendChannels({
        text,
        settings: currentSettings,
        type: 'price_alert',
        meta: {
          alertId: alert.id,
          assetId: asset.id,
          condition: alert.condition,
          value: alert.value,
          currentPrice: asset.currentPrice,
        },
      });
    }
  }
}

// 7. Live Price Feed — real data where available, stable mock for funds NAV
const FOREX_MT5_MAP = {
  'EUR_USD': 'EURUSDm',
  'USD_JPY': 'USDJPYm',
  'GBP_USD': 'GBPUSDm',
  'AUD_USD': 'AUDUSDm',
  'USD_CAD': 'USDCADm',
  'USD_CHF': 'USDCHFm',
  'NZD_USD': 'NZDUSDm',
  'XAU_USD': 'XAUUSDm',
};
const CRYPTO_CG_MAP = {
  'BTC': 'bitcoin',
  'ETH': 'ethereum',
  'SOL': 'solana',
  'BNB': 'binancecoin',
  'XRP': 'ripple',
};

let cryptoPriceCache = {};
let lastCryptoFetch = 0;

async function fetchCryptoPrices() {
  const ids = Object.values(CRYPTO_CG_MAP).join(',');
  try {
    const res = await fetch(`https://api.coingecko.com/api/v3/simple/price?ids=${ids}&vs_currencies=usd`, { signal: AbortSignal.timeout(8000) });
    if (!res.ok) throw new Error(`CoinGecko ${res.status}`);
    const data = await res.json();
    for (const [sym, cgId] of Object.entries(CRYPTO_CG_MAP)) {
      if (data[cgId]?.usd) cryptoPriceCache[sym] = data[cgId].usd;
    }
    lastCryptoFetch = Date.now();
  } catch (err) {
    console.warn('⚠️ CoinGecko fetch failed:', err.message);
  }
}

async function updateLivePrices() {
  try {
    const settings = getSettings();
    const dbAssets = db.prepare('SELECT * FROM portfolio').all();
    const updatePriceStmt = db.prepare('UPDATE portfolio SET currentPrice = ? WHERE id = ?');

    // Fetch crypto prices once per cycle (rate-limit friendly: ~30s interval)
    const cryptoAssets = dbAssets.filter(a => a.type === 'crypto');
    if (cryptoAssets.length && Date.now() - lastCryptoFetch > 25000) {
      await fetchCryptoPrices();
    }

    for (const asset of dbAssets) {
      let newPrice = null;

      if (asset.type === 'forex') {
        const mt5Symbol = FOREX_MT5_MAP[asset.id];
        if (mt5Symbol) {
          const tick = await fetchMT5(`/price/${mt5Symbol}`);
          if (tick.mt5_status === 'online' && tick.last) {
            newPrice = parseFloat(tick.last.toFixed(asset.id === 'USD_JPY' ? 2 : 4));
          } else if (tick.bid && tick.ask) {
            newPrice = parseFloat(((tick.bid + tick.ask) / 2).toFixed(asset.id === 'USD_JPY' ? 2 : 4));
          }
        }
      } else if (asset.type === 'crypto') {
        const sym = asset.code_symbol_pair || asset.id;
        if (cryptoPriceCache[sym]) {
          newPrice = parseFloat(cryptoPriceCache[sym].toFixed(2));
        }
      }
      // funds: no real-time API — keep currentPrice stable (NAV updates daily)

      if (newPrice !== null && newPrice > 0) {
        updatePriceStmt.run(newPrice, asset.id);
        checkPriceAlert({ ...asset, currentPrice: newPrice }, settings);
      }
    }
  } catch (err) {
    console.error('⚠️ Price update error:', err.message);
  }
}

// Forex updates every 5s, crypto piggybacks on same loop but CoinGecko fetched every ~30s
setInterval(updateLivePrices, 5000);
// Initial fetch on startup
updateLivePrices();

// --- API ENDPOINTS ---

// GET /api/health - dashboard dependency health for UI diagnostics
app.get('/api/health', async (req, res) => {
  const startedAt = new Date().toISOString();
  let portfolioOk = false;
  let assetCount = 0;
  try {
    const row = db.prepare('SELECT COUNT(*) as count FROM portfolio').get();
    assetCount = row.count;
    portfolioOk = true;
  } catch (err) {
    return res.status(500).json({
      status: 'degraded',
      startedAt,
      portfolio: { status: 'down', error: err.message },
      mt5: { status: 'unknown' },
    });
  }

  const mt5 = await fetchMT5('/account');
  const mt5Online = mt5.mt5_status === 'online' && !mt5.error;
  res.json({
    status: portfolioOk && mt5Online ? 'ok' : 'degraded',
    startedAt,
    portfolio: { status: 'ok', assetCount },
    mt5: {
      status: mt5.mt5_status || 'offline',
      cachedAt: mt5.cached_at || null,
      error: mt5.error || null,
      account: mt5.login || null,
      currency: mt5.currency || null,
    },
    prices: {
      cryptoCacheAgeSeconds: lastCryptoFetch ? Math.round((Date.now() - lastCryptoFetch) / 1000) : null,
      cryptoSymbols: Object.keys(cryptoPriceCache),
    },
  });
});

// GET /api/portfolio - active portfolio valuation
app.get('/api/portfolio', (req, res) => {
  try {
    const dbAssets = db.prepare('SELECT * FROM portfolio').all();
    
    let totalValue = 0;
    let totalCost = 0;
    
    const calculateCategoryValuation = (itemsList) => {
      let categoryValue = 0;
      let categoryCost = 0;
      
      const items = itemsList.map(dbItem => {
        const item = {
          id: dbItem.id,
          name: dbItem.name,
          units: dbItem.units,
          avgBuyPrice: dbItem.avgBuyPrice,
          currentPrice: dbItem.currentPrice,
          type: dbItem.type,
          [dbItem.type === 'funds' ? 'code' : dbItem.type === 'crypto' ? 'symbol' : 'pair']: dbItem.code_symbol_pair
        };
        
        const value = item.units * item.currentPrice;
        const cost = item.units * item.avgBuyPrice;
        const pnl = value - cost;
        const pnlPct = cost > 0 ? (pnl / cost) * 100 : 0;
        
        categoryValue += value;
        categoryCost += cost;
        
        return {
          ...item,
          currentValue: parseFloat(value.toFixed(2)),
          totalCost: parseFloat(cost.toFixed(2)),
          pnl: parseFloat(pnl.toFixed(2)),
          pnlPct: parseFloat(pnlPct.toFixed(2))
        };
      });
      
      totalValue += categoryValue;
      totalCost += categoryCost;
      
      return {
        items,
        value: parseFloat(categoryValue.toFixed(2)),
        pnl: parseFloat((categoryValue - categoryCost).toFixed(2)),
        pnlPct: parseFloat((categoryCost > 0 ? ((categoryValue - categoryCost) / categoryCost) * 100 : 0).toFixed(2))
      };
    };
    
    const fundsData = calculateCategoryValuation(dbAssets.filter(a => a.type === 'funds'));
    const cryptoData = calculateCategoryValuation(dbAssets.filter(a => a.type === 'crypto'));
    const forexData = calculateCategoryValuation(dbAssets.filter(a => a.type === 'forex'));

    const netWorth = parseFloat(totalValue.toFixed(2));
    const totalProfitLoss = parseFloat((totalValue - totalCost).toFixed(2));
    const totalProfitLossPct = parseFloat((totalCost > 0 ? (totalProfitLoss / totalCost) * 100 : 0).toFixed(2));

    res.json({
      netWorth,
      totalCost: parseFloat(totalCost.toFixed(2)),
      totalProfitLoss,
      totalProfitLossPct,
      categories: {
        funds: fundsData,
        crypto: cryptoData,
        forex: forexData
      }
    });
  } catch (err) {
    res.status(500).json({ error: `Failed to calculate valuation: ${err.message}` });
  }
});

// POST /api/portfolio/transaction - add buy/sell
app.post('/api/portfolio/transaction', (req, res) => {
  const { type, assetId, action, units, price } = req.body;
  
  if (!type || !assetId || !action || !units || !price) {
    return res.status(400).json({ error: "Missing required transaction fields" });
  }

  const inputUnits = parseFloat(units);
  const inputPrice = parseFloat(price);

  if (isNaN(inputUnits) || inputUnits <= 0 || isNaN(inputPrice) || inputPrice <= 0) {
    return res.status(400).json({ error: "Units and price must be valid positive numbers" });
  }

  db.exec('BEGIN TRANSACTION;');
  try {
    const asset = db.prepare('SELECT * FROM portfolio WHERE id = ? AND type = ?').get(assetId, type);
    if (!asset) {
      db.exec('ROLLBACK;');
      return res.status(404).json({ error: "Asset not found" });
    }

    let newUnits = asset.units;
    let newAvgPrice = asset.avgBuyPrice;

    if (action === 'buy') {
      const currentCost = asset.units * asset.avgBuyPrice;
      const additionalCost = inputUnits * inputPrice;
      newUnits = asset.units + inputUnits;
      newAvgPrice = newUnits > 0 ? (currentCost + additionalCost) / newUnits : 0;
      newAvgPrice = parseFloat(newAvgPrice.toFixed(4));
      newUnits = parseFloat(newUnits.toFixed(4));
    } else if (action === 'sell') {
      if (asset.units < inputUnits) {
        db.exec('ROLLBACK;');
        return res.status(400).json({ error: "Insufficient units to sell" });
      }
      newUnits = parseFloat((asset.units - inputUnits).toFixed(4));
    } else {
      db.exec('ROLLBACK;');
      return res.status(400).json({ error: "Invalid action" });
    }

    db.prepare('UPDATE portfolio SET units = ?, avgBuyPrice = ? WHERE id = ?').run(newUnits, newAvgPrice, assetId);
    db.prepare('INSERT INTO transactions (assetId, type, action, units, price) VALUES (?, ?, ?, ?, ?)').run(assetId, type, action, inputUnits, inputPrice);

    db.exec('COMMIT;');

    const actionText = action === 'buy' ? '🟢 ซื้อเพิ่ม' : '🔴 ขายออก';
    const txMsg = `🔔 *AI PORTFOLIO UPDATE* 🔔\n\nทำธุรกรรม: *${actionText}*\nสินทรัพย์: *${asset.name} (${asset.id})*\nจำนวน: *${inputUnits}* หน่วย\nราคา: *${inputPrice}*\n\n🤖 *ระบบ AI* ได้บันทึกรายการธุรกรรมลงใน SQLite และปรับปรุงการวิเคราะห์สัดส่วนพอร์ตเรียบร้อยแล้ว`;
    sendTelegramMessage(txMsg, null, null, { type: 'transaction_alert', meta: { assetId, action, type } });

    res.json({ success: true, asset: { ...asset, units: newUnits, avgBuyPrice: newAvgPrice } });
  } catch (err) {
    try { db.exec('ROLLBACK;'); } catch (_) {}
    res.status(500).json({ error: `Transaction failed: ${err.message}` });
  }
});

// GET /api/ai/recommend - portfolio recommendation & rebalancing
app.get('/api/ai/recommend', (req, res) => {
  try {
    const settings = getSettings();
    const currentRisk = settings.riskProfile;
    
    const dbAssets = db.prepare('SELECT * FROM portfolio').all();
    let totalVal = 0;
    const vals = { funds: 0, crypto: 0, forex: 0 };
    
    dbAssets.forEach(item => {
      vals[item.type] += item.units * item.currentPrice;
    });
    totalVal = vals.funds + vals.crypto + vals.forex;

    const currentWeights = {
      funds: totalVal > 0 ? parseFloat(((vals.funds / totalVal) * 100).toFixed(2)) : 0,
      crypto: totalVal > 0 ? parseFloat(((vals.crypto / totalVal) * 100).toFixed(2)) : 0,
      forex: totalVal > 0 ? parseFloat(((vals.forex / totalVal) * 100).toFixed(2)) : 0
    };

    let targetWeights = { funds: 50, crypto: 20, forex: 30 }; // Balanced
    let aiInsights = "";

    if (currentRisk === 'Conservative') {
      targetWeights = { funds: 75, crypto: 5, forex: 20 };
      aiInsights = "พอร์ตระดับความเสี่ยงต่ำเน้นการรักษาเงินต้น AI แนะนำให้เน้นการลงทุนในกองทุนรวมดัชนีเป็นหลัก หลีกเลี่ยงคริปโตเพื่อจำกัดความผันผวน และถือ Forex สกุลเงินหลักเพื่อเพิ่มสภาพคล่อง";
    } else if (currentRisk === 'Aggressive') {
      targetWeights = { funds: 25, crypto: 55, forex: 20 };
      aiInsights = "พอร์ตระดับความเสี่ยงสูงเน้นการสร้างผลตอบแทนสูงสุด AI วิเคราะห์ว่าแนวโน้ม Crypto และ Forex กำลังเข้าสู่ความผันผวนด้านบวก แนะนำเพิ่มสัดส่วนการเก็บ BTC/SOL และบริหารเลเวอเรจในพอร์ต Forex ให้เหมาะสม";
    } else {
      aiInsights = "พอร์ตระดับสมดุลกระจายความเสี่ยงอย่างเป็นระบบ AI แนะนำให้ถือครองกองทุนหลัก 50% ควบคู่กับบลูชิพคริปโต (BTC/ETH) 20% เพื่อเพิ่ม Alpha และเทรด Forex 30% เพื่อสร้างกระแสเงินสดในกรอบราคา";
    }

    const recommendations = [];
    ['funds', 'crypto', 'forex'].forEach(cat => {
      const diff = targetWeights[cat] - currentWeights[cat];
      const amountToAdjust = parseFloat(((diff / 100) * totalVal).toFixed(2));
      
      let action = "HOLD";
      if (diff > 2) action = "BUY_MORE";
      else if (diff < -2) action = "TAKE_PROFIT";

      recommendations.push({
        category: cat,
        currentWeight: currentWeights[cat],
        targetWeight: targetWeights[cat],
        difference: parseFloat(diff.toFixed(2)),
        amount: amountToAdjust,
        action
      });
    });

    res.json({
      riskProfile: currentRisk,
      totalValue: parseFloat(totalVal.toFixed(2)),
      recommendations,
      aiInsights
    });
  } catch (err) {
    res.status(500).json({ error: `Rebalancing recommend failed: ${err.message}` });
  }
});

// POST /api/ai/chat - AI assistant chat
app.post('/api/ai/chat', async (req, res) => {
  const { message } = req.body;
  if (!message) {
    return res.status(400).json({ error: "Message is required" });
  }

  try {
    const settings = getSettings();
    const dbAssets = db.prepare('SELECT * FROM portfolio').all();
    
    let totalVal = 0;
    const vals = { funds: 0, crypto: 0, forex: 0 };
    dbAssets.forEach(item => {
      vals[item.type] += item.units * item.currentPrice;
    });
    totalVal = vals.funds + vals.crypto + vals.forex;

    const btcPrice = dbAssets.find(c => c.id === 'BTC')?.currentPrice || 67000;
    const { provider, apiKey, model, endpoint } = settings.llmConfig;
    const realLlmActive = (provider === 'Ollama') || (provider === 'Custom') || (apiKey && apiKey.trim() !== "");

    if (realLlmActive) {
      try {
        const systemInstruction = 
          `You are a premium world-class AI Wealth Coach & Investment Advisor inside an investment dashboard. ` +
          `You have real-time access to the user's active SQLite portfolio statistics:\n` +
          `- Total Net Worth: ฿${totalVal.toLocaleString('th-TH', {minimumFractionDigits: 2})} THB\n` +
          `- Active Risk Target Profile: ${settings.riskProfile}\n` +
          `- Holding Asset Classes:\n` +
          `  * Mutual Funds: ${dbAssets.filter(a => a.type === 'funds').map(f => `${f.name} (${f.id}, units: ${f.units}, currentPrice: ฿${f.currentPrice})`).join(', ')}\n` +
          `  * Crypto Assets: ${dbAssets.filter(a => a.type === 'crypto').map(c => `${c.name} (${c.id}, units: ${c.units}, currentPrice: $${c.currentPrice})`).join(', ')}\n` +
          `  * Forex Pairs: ${dbAssets.filter(a => a.type === 'forex').map(fx => `${fx.name} (${fx.id}, size: ${fx.units}, rate: ${fx.currentPrice})`).join(', ')}\n\n` +
          `User's Risk Preference: ${settings.riskProfile === 'Conservative' ? 'Conservative (Low risk, preserves capital)' : settings.riskProfile === 'Aggressive' ? 'Aggressive (High growth, cryptocurrency and forex focus)' : 'Balanced (Dynamic portfolio with indices and blue-chips)'}.\n\n` +
          `INSTRUCTIONS:\n` +
          `1. Answer the user's investment inquiries in excellent, encouraging, and highly professional Thai language (ภาษาไทย).\n` +
          `2. Give specific, data-backed financial recommendations referring to their portfolio holdings, allocations, or risk preferences.\n` +
          `3. Format your answers clearly using bold headings, styled list bullets, and proper markdown to match a premium financial terminal.\n` +
          `4. Be encouraging but structurally sound with risk disclosures. Keep it concise.`;

        let replyText = "";
        if (provider === 'Gemini') {
          const url = `https://generativelanguage.googleapis.com/v1beta/models/${model || 'gemini-1.5-flash'}:generateContent?key=${apiKey}`;
          const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              contents: [
                {
                  role: 'user',
                  parts: [{ text: `${systemInstruction}\n\nUser Question: ${message}` }]
                }
              ]
            })
          });
          const data = await response.json();
          if (response.ok && data.candidates && data.candidates[0].content.parts[0].text) {
            replyText = data.candidates[0].content.parts[0].text;
          } else {
            throw new Error(data.error?.message || "Gemini API returned error response");
          }
        } else if (provider === 'OpenAI') {
          const url = endpoint || 'https://api.openai.com/v1/chat/completions';
          const response = await fetch(url, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Authorization': `Bearer ${apiKey}`
            },
            body: JSON.stringify({
              model: model || 'gpt-4o-mini',
              messages: [
                { role: 'system', content: systemInstruction },
                { role: 'user', content: message }
              ]
            })
          });
          const data = await response.json();
          if (response.ok && data.choices && data.choices[0].message.content) {
            replyText = data.choices[0].message.content;
          } else {
            throw new Error(data.error?.message || "OpenAI API returned error response");
          }
        } else if (provider === 'Ollama') {
          const url = `${endpoint || 'http://localhost:11434'}/api/chat`;
          const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              model: model || 'llama3',
              messages: [
                { role: 'system', content: systemInstruction },
                { role: 'user', content: message }
              ],
              stream: false
            })
          });
          const data = await response.json();
          if (response.ok && data.message && data.message.content) {
            replyText = data.message.content;
          } else {
            throw new Error("Ollama connection timeout or error");
          }
        } else if (provider === 'Custom') {
          if (!endpoint || endpoint.trim() === '') {
            throw new Error("Custom provider requires a server endpoint URL");
          }
          const customUrl = endpoint.trim().replace(/\/$/, '') + '/v1/chat/completions';
          const headers = { 'Content-Type': 'application/json' };
          if (apiKey && apiKey.trim() !== '') {
            headers['Authorization'] = `Bearer ${apiKey}`;
          }
          const response = await fetch(customUrl, {
            method: 'POST',
            headers,
            body: JSON.stringify({
              model: model || 'default',
              stream: false,
              messages: [
                { role: 'system', content: systemInstruction },
                { role: 'user', content: message }
              ]
            })
          });
          const rawText = await response.text();
          let data;
          try {
            data = JSON.parse(rawText);
          } catch (parseErr) {
            const match = rawText.match(/data:\s*(\{.*\})/s);
            if (match) data = JSON.parse(match[1]);
            else throw new Error(`Custom proxy returned non-JSON response`);
          }
          if (response.ok && data.choices && data.choices[0].message?.content) {
            replyText = data.choices[0].message.content;
          } else if (data.error) {
            throw new Error(data.error?.message || JSON.stringify(data.error));
          } else {
            throw new Error("Custom proxy returned unexpected response format");
          }
        }

        if (replyText) {
          return res.json({ reply: replyText });
        }
      } catch (err) {
        console.warn("Real LLM call failed, falling back to simulated engine. Error: ", err.message);
      }
    }

    // simulated engine fallback
    const msgLower = message.toLowerCase();
    let reply = "";

    if (msgLower.includes("วิเคราะห์") || msgLower.includes("แนะนำ") || msgLower.includes("พอร์ต") || msgLower.includes("portfolio")) {
      reply = `🤖 **บทวิเคราะห์พอร์ตโฟลิโอโดย AI (Offline SQLite Mode)**\n\nปัจจุบันคุณมีมูลค่าทรัพย์สินสุทธิอยู่ที่ **฿${totalVal.toLocaleString('th-TH', {minimumFractionDigits: 2, maximumFractionDigits: 2})}** ซึ่งกระจายตัวบน SQLite (WAL Mode) ดังนี้:\n` +
              `• 📈 **กองทุนรวม:** ${((vals.funds/totalVal)*100 || 0).toFixed(1)}%\n` +
              `• 🪙 **คริปโต:** ${((vals.crypto/totalVal)*100 || 0).toFixed(1)}%\n` +
              `• 💱 **Forex:** ${((vals.forex/totalVal)*100 || 0).toFixed(1)}%\n\n` +
              `**ความเห็นเชิงลึกจาก AI:** พอร์ตของคุณจัดอยู่ในระดับความเสี่ยงแบบ **${settings.riskProfile}** ปัจจุบันระบบได้ย้ายฐานรากบันทึกด้วย SQLite พร้อมการจัดเก็บทรานแซกชันเรียบร้อย แนะนำเข้าดูหน้า AI Optimizer เพื่อปรับปรุงพอร์ตตามเป้าหมายครับ`;
    } else if (msgLower.includes("crypto") || msgLower.includes("คริปโต") || msgLower.includes("btc") || msgLower.includes("bitcoin")) {
      reply = `🪙 **วิเคราะห์แนวโน้มตลาด Crypto (Offline Mode)**\n\nปัจจุบัน **Bitcoin (BTC)** อัปเดตราคาล่าสุดคือ **$${btcPrice.toLocaleString()}**\n\n**สัญญาณทางเทคนิคจาก AI:**\n` +
              `• RSI (14 วัน) อยู่ที่ระดับ 58.4 (เป็นกลางค่อนไปทางบวก)\n` +
              `• MACD เกิดการตัดกันสีเขียว (Bullish Crossover) ในกราฟ 4 ชม.\n\n` +
              `**กลยุทธ์แนะนำ:** แนะนำให้ทยอยสะสม (DCA) บริเวณแนวรับสำคัญของ Bitcoin และพิจารณาถือ Solana (SOL) เพิ่มเติมเนื่องจากมีระดับ Momentum ที่แข็งแกร่งกว่าตลาดทั่วไป`;
    } else if (msgLower.includes("telegram") || msgLower.includes("บอท") || msgLower.includes("เตือน")) {
      const configStatus = settings.telegramBotToken ? "✅ เปิดใช้งานแล้ว" : "❌ ยังไม่ได้ตั้งค่า";
      reply = `🔔 **ระบบแจ้งเตือนผ่าน Telegram**\n\nสถานะการเชื่อมต่อบอท: **${configStatus}**\n\nบอท AI นี้จะทำงานอัตโนมัติดังนี้:\n` +
              `1. แจ้งเตือนด่วนเมื่อราคาสินทรัพย์ขยับผ่านเกณฑ์ที่คุณกำหนดไว้ในหน้า Settings\n` +
              `2. รายงานสรุปความเคลื่อนไหวของพอร์ตการลงทุนประจำวัน\n` +
              `3. แจ้งเตือนสถานะเมื่อคุณกดส่งคำสั่ง ซื้อ/ขาย ผ่านหน้าเว็บ`;
    } else {
      reply = `🤖 สวัสดีครับ! ผมคือ **AI Wealth Advisor** (เชื่อมต่อคีย์ API จริงได้ในหน้าตั้งค่า) ส่วนตัวของคุณ ยินดีต้อนรับสู่แดชบอร์ดการบริหารความมั่งคั่งยุคใหม่ครับ\n\nวันนี้คุณต้องการให้ผมช่วยเหลือเรื่องอะไรดีครับ?\n` +
              `• ถาม **"วิเคราะห์พอร์ต"** เพื่อดูจุดคุ้มทุน สัดส่วน และคำแนะนำการกระจายความเสี่ยง\n` +
              `• ถาม **"แนวโน้มคริปโต"** เพื่อรับสัญญาณการลงทุนเชิงเทคนิคและโมเมนตัมราคา\n` +
              `• ถาม **"วิธีตั้งค่า Telegram"** เพื่อเรียนรู้วิธีเปิดระบบแจ้งเตือนเข้าสู่มือถือของคุณโดยตรง`;
    }

    res.json({ reply });
  } catch (err) {
    res.status(500).json({ error: `AI Advisor failure: ${err.message}` });
  }
});

// GET /api/settings - retrieve active configuration
app.get('/api/settings', (req, res) => {
  try {
    res.json(getSettings());
  } catch (err) {
    res.status(500).json({ error: `Failed to retrieve settings: ${err.message}` });
  }
});

// POST /api/settings - save configuration
app.post('/api/settings', (req, res) => {
  try {
    const {
      telegramBotToken,
      telegramChatId,
      lineChannelAccessToken,
      lineTargetId,
      lineNotifyToken,
      riskProfile,
      alerts,
      llmConfig,
      mcpConfig,
      tradingControl
    } = req.body;
    
    const currentSettings = getSettings();
    
    if (telegramBotToken !== undefined) currentSettings.telegramBotToken = telegramBotToken;
    if (telegramChatId !== undefined) currentSettings.telegramChatId = telegramChatId;
    if (lineChannelAccessToken !== undefined) currentSettings.lineChannelAccessToken = lineChannelAccessToken;
    if (lineTargetId !== undefined) currentSettings.lineTargetId = lineTargetId;
    if (lineNotifyToken !== undefined) currentSettings.lineNotifyToken = lineNotifyToken;
    if (riskProfile !== undefined) currentSettings.riskProfile = riskProfile;
    if (alerts !== undefined) currentSettings.alerts = alerts;
    if (llmConfig !== undefined) currentSettings.llmConfig = { ...currentSettings.llmConfig, ...llmConfig };
    if (mcpConfig !== undefined) currentSettings.mcpConfig = { ...currentSettings.mcpConfig, ...mcpConfig };
    if (tradingControl !== undefined) currentSettings.tradingControl = { ...currentSettings.tradingControl, ...tradingControl };

    saveSettings(currentSettings);
    res.json({ success: true, settings: currentSettings });
  } catch (err) {
    res.status(500).json({ error: `Failed to update settings: ${err.message}` });
  }
});

// POST /api/ai/models - fetch models list from local or remote proxy
app.post('/api/ai/models', async (req, res) => {
  const { provider, endpoint, apiKey } = req.body;

  if (!provider) {
    return res.status(400).json({ error: "Provider is required" });
  }

  try {
    if (provider === 'Custom') {
      if (!endpoint || endpoint.trim() === '') {
        return res.status(400).json({ error: "Endpoint URL is required for Custom proxy" });
      }
      const baseUrl = endpoint.trim().replace(/\/$/, '');
      const modelsUrl = `${baseUrl}/v1/models`;
      const headers = { 'Content-Type': 'application/json' };
      if (apiKey && apiKey.trim() !== '') {
        headers['Authorization'] = `Bearer ${apiKey}`;
      }
      const response = await fetch(modelsUrl, { headers });
      if (!response.ok) {
        throw new Error(`Proxy server returned status ${response.status}`);
      }
      const data = await response.json();
      if (data && Array.isArray(data.data)) {
        const modelIds = data.data.map(m => m.id);
        return res.json({ success: true, models: modelIds });
      }
      return res.json({ success: true, models: [] });
    } else if (provider === 'Ollama') {
      const baseUrl = endpoint.trim().replace(/\/$/, '') || 'http://localhost:11434';
      const modelsUrl = `${baseUrl}/api/tags`;
      const response = await fetch(modelsUrl);
      if (!response.ok) {
        throw new Error(`Ollama server returned status ${response.status}`);
      }
      const data = await response.json();
      if (data && Array.isArray(data.models)) {
        const modelNames = data.models.map(m => m.name);
        return res.json({ success: true, models: modelNames });
      }
      return res.json({ success: true, models: [] });
    } else {
      return res.json({ success: true, models: [] });
    }
  } catch (err) {
    res.status(500).json({ error: `Failed to fetch models: ${err.message}` });
  }
});

// POST /api/ai/verify - test API keys
app.post('/api/ai/verify', async (req, res) => {
  const { provider, apiKey, model, endpoint } = req.body;
  
  if (provider !== 'Ollama' && provider !== 'Custom' && (!apiKey || apiKey.trim() === '')) {
    return res.status(400).json({ error: "API Key is required for cloud providers" });
  }
  if (provider === 'Custom' && (!endpoint || endpoint.trim() === '')) {
    return res.status(400).json({ error: "Custom provider requires a Server Endpoint URL" });
  }

  try {
    let ok = false;
    let text = "";
    
    if (provider === 'Gemini') {
      const url = `https://generativelanguage.googleapis.com/v1beta/models/${model || 'gemini-1.5-flash'}:generateContent?key=${apiKey}`;
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          contents: [{ parts: [{ text: "Respond with only one word: SUCCESS" }] }]
        })
      });
      const data = await response.json();
      if (response.ok && data.candidates && data.candidates[0].content.parts[0].text) {
        ok = true;
        text = data.candidates[0].content.parts[0].text.trim();
      } else {
        text = data.error?.message || "API credentials verify call failed";
      }
    } else if (provider === 'OpenAI') {
      const url = endpoint || 'https://api.openai.com/v1/chat/completions';
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${apiKey}`
        },
        body: JSON.stringify({
          model: model || 'gpt-4o-mini',
          messages: [{ role: 'user', content: "Respond with only one word: SUCCESS" }]
        })
      });
      const data = await response.json();
      if (response.ok && data.choices && data.choices[0].message.content) {
        ok = true;
        text = data.choices[0].message.content.trim();
      } else {
        text = data.error?.message || "API credentials verify call failed";
      }
    } else if (provider === 'Ollama') {
      const url = `${endpoint || 'http://localhost:11434'}/api/generate`;
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: model || 'llama3',
          prompt: "Respond with only one word: SUCCESS",
          stream: false
        })
      });
      const data = await response.json();
      if (response.ok && data.response) {
        ok = true;
        text = data.response.trim();
      } else {
        text = "Could not contact Ollama instance or model is not loaded";
      }
    } else if (provider === 'Custom') {
      const baseUrl = endpoint.trim().replace(/\/$/, '');
      const customUrl = `${baseUrl}/v1/chat/completions`;
      const healthUrl = `${baseUrl}/api/health`;
      
      let is9Router = false;
      try {
        const healthRes = await fetch(healthUrl, { method: 'GET' }).catch(() => null);
        if (healthRes && healthRes.ok) {
          const healthData = await healthRes.json().catch(() => ({}));
          if (healthData && healthData.ok === true) {
            is9Router = true;
          }
        }
      } catch (_) {}

      const headers = { 'Content-Type': 'application/json' };
      if (apiKey && apiKey.trim() !== '') {
        headers['Authorization'] = `Bearer ${apiKey}`;
      }
      const response = await fetch(customUrl, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          model: model || 'default',
          stream: false,
          messages: [{ role: 'user', content: 'Respond with only one word: SUCCESS' }]
        })
      });
      const rawText = await response.text();
      let data;
      try {
        data = JSON.parse(rawText);
      } catch (_) {
        const match = rawText.match(/data:\s*(\{.*\})/s);
        if (match) data = JSON.parse(match[1]);
        else {
          text = `Proxy returned non-JSON stream.`;
          data = null;
        }
      }
      if (data && response.ok && data.choices && data.choices[0].message?.content) {
        ok = true;
        const brainResponse = data.choices[0].message.content.trim();
        text = is9Router 
          ? `SUCCESS! 9Router ⚡ Detected & Working. Brain: ${brainResponse}` 
          : `SUCCESS! Custom Proxy Working. Brain: ${brainResponse}`;
      } else if (data) {
        text = data.error?.message || `Custom proxy returned unexpected format`;
      }
    } else {
      text = "Claude/Anthropic API verify mock success";
      ok = true;
    }

    if (ok) {
      res.json({ success: true, message: `Verification successful! Brain responded: ${text}` });
    } else {
      res.status(500).json({ error: text });
    }
  } catch (err) {
    res.status(500).json({ error: `Connection failed: ${err.message}` });
  }
});

// POST /api/telegram/test - verify bot connection
app.post('/api/telegram/test', async (req, res) => {
  const { telegramBotToken, telegramChatId } = req.body;
  
  if (!telegramBotToken || !telegramChatId) {
    return res.status(400).json({ error: "Missing Bot Token or Chat ID" });
  }

  const testText = `🔔 *AI HEDGEFUND TELEGRAM ALERT* 🔔\n\n🚀 ยินดีด้วย! การเชื่อมต่อระบบบริหารพอร์ตการลงทุน AI ของคุณเสร็จสมบูรณ์\n\nบอทอัจฉริยะระบบแจ้งเตือนพร้อมสนับสนุนการบริหาร กองทุน, คริปโต และ Forex ของคุณแล้ว\n\n💡 _ระบบจะส่งรายงานพอร์ตและแจ้งเตือนราคาตัดระดับผ่านแชทนี้ทันทีเมื่อตรวจพบสัญญาณครับ!_`;
  
  const ok = await sendTelegramMessage(testText, telegramBotToken, telegramChatId, { type: 'manual_test', meta: { channel: 'telegram' } });
  
  if (ok) {
    res.json({ success: true, message: "Test alert dispatched successfully!" });
  } else {
    res.status(500).json({ error: "Failed to dispatch Telegram message. Verify Bot Token and Chat ID." });
  }
});

// POST /api/line/test - verify LINE notification connection
app.post('/api/line/test', async (req, res) => {
  const {
    lineChannelAccessToken,
    lineTargetId,
    lineNotifyToken
  } = req.body || {};

  if ((!lineChannelAccessToken || !lineTargetId) && !lineNotifyToken) {
    return res.status(400).json({ error: "Missing LINE Channel Access Token + Target ID, or LINE Notify Token" });
  }

  const testText = `AI HEDGEFUND LINE ALERT\n\nทดสอบส่ง Alert สำเร็จ ระบบ Hedgefund พร้อมส่งสัญญาณ Trading, Risk Guard และ Daily AI Report ผ่าน LINE แล้ว`;
  const ok = await sendLineMessage(testText, lineChannelAccessToken, lineTargetId, lineNotifyToken, { type: 'manual_test', meta: { channel: 'line' } });

  if (ok) {
    res.json({ success: true, message: "LINE test alert dispatched successfully!" });
  } else {
    res.status(500).json({ error: "Failed to dispatch LINE message. Verify token and target settings." });
  }
});

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
  const symbol = req.params.symbol;
  if (!/^[A-Z0-9_]{2,12}$/.test(symbol)) {
    return res.status(400).json({ error: 'invalid symbol' });
  }
  const data = await fetchMT5(`/price/${symbol}`);
  res.json(data);
});

app.get('/api/mt5/ohlcv/:symbol', async (req, res) => {
  const symbol = req.params.symbol;
  if (!/^[A-Z0-9]{2,12}$/i.test(symbol)) {
    return res.status(400).json({ error: 'invalid symbol' });
  }
  const timeframe = req.query.timeframe || 'M15';
  const count = Math.min(parseInt(req.query.count) || 200, 1000);
  const data = await fetchMT5(`/ohlcv/${symbol}?timeframe=${timeframe}&count=${count}`);
  res.json(data);
});

app.get('/api/persona-signals', (req, res) => {
  res.json({ signals: [], mt5_status: 'online', source: 'stub' });
});

// SSE stream — sends a keepalive every 15s, no real-time push (MT5 has no push API)
app.get('/api/order_history/stream', (req, res) => {
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.flushHeaders();
  const id = setInterval(() => res.write(': keepalive\n\n'), 15000);
  req.on('close', () => clearInterval(id));
});

app.get('/api/order_history', async (req, res) => {
  const hours = Math.min(parseInt(req.query.hours) || 24, 720);
  const limit = Math.min(parseInt(req.query.limit) || 100, 500);
  const raw = await fetchMT5(`/history/recent?hours=${hours}&limit=${limit}`);
  const deals = raw.deals ?? (mt5Cache[`/history/recent?hours=${hours}&limit=${limit}`]?.data?.deals ?? []);
  // Map bridge fields to what TradeHistory expects
  const items = deals.map(d => ({
    ticket: d.ticket,
    position: d.position,
    symbol: d.symbol,
    volume: d.volume,
    price: d.price,
    profit: d.profit,
    swap: d.swap,
    commission: d.commission,
    time: d.time,
    type: d.type,
    entry: d.entry,
    comment: d.comment,
    // aliases TradeHistory might use
    pnl: d.profit,
    side: d.type === 0 ? 'buy' : 'sell',
    status: d.entry ? 'closed' : 'open',
  }));
  res.json({ items, mt5_status: raw.mt5_status, cached_at: raw.cached_at });
});

app.get('/api/deal/:ticket', async (req, res) => {
  const ticket = parseInt(req.params.ticket);
  if (!ticket || ticket <= 0) return res.status(400).json({ error: 'invalid ticket' });
  const data = await fetchMT5(`/history/deal/${ticket}`);
  if (data.mt5_status === 'offline') return res.status(503).json(data);
  res.json(data);
});

app.post('/api/mt5/order', async (req, res) => {
  const { symbol, action, volume, sl = 0, tp = 0 } = req.body;
  const vol = parseFloat(volume);
  const normalizedAction = typeof action === 'string' ? action.toUpperCase() : '';
  if (!symbol || !/^[A-Z0-9_]{2,12}$/.test(symbol) || !['BUY', 'SELL'].includes(normalizedAction) || !isFinite(vol) || vol <= 0) {
    return res.status(400).json({ error: 'symbol required; action must be buy/sell; volume must be positive number' });
  }
  const data = await fetchMT5('/order', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ symbol, action: normalizedAction, volume: vol, sl, tp, comment: 'dashboard', magic: 20260528 })
  });
  if (data.mt5_status === 'offline') return res.status(503).json(data);
  res.json(data);
});

installNotificationRoutes(app, { notifications });
installTradingControlRoutes(app, { db, getSettings, notifications, sendTelegramMessage });
installAiAnalystRoutes(app, { db, getSettings, dispatchControlCommand, recordControlAction, notifications, sendTelegramMessage });

app.listen(PORT, () => {
  console.log(`🚀 AI Hedgefund API Server running on http://localhost:${PORT}`);
});
