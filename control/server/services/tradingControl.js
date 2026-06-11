import fetch from 'node-fetch';

const DEFAULT_MTAI_URL = process.env.MTAI_API_URL || 'http://127.0.0.1:3003';
const DEFAULT_CRYPTO_URL = process.env.CRYPTO_AI_API_URL || 'http://127.0.0.1:3006';
const FETCH_TIMEOUT_MS = Number(process.env.TRADING_CONTROL_TIMEOUT_MS || 5000);

function nowIso() {
  return new Date().toISOString();
}

function safeNumber(value, fallback = 0) {
  const num = Number(value);
  return Number.isFinite(num) ? num : fallback;
}

async function fetchJson(url) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  try {
    const res = await fetch(url, { signal: controller.signal });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return { ok: true, data: await res.json() };
  } catch (err) {
    return { ok: false, error: err.message };
  } finally {
    clearTimeout(timer);
  }
}

function normalizeDailyPnl(dailyPnl = {}) {
  const keys = Object.keys(dailyPnl).sort();
  const today = keys[keys.length - 1] || null;
  return {
    date: today,
    value: today ? safeNumber(dailyPnl[today]) : 0,
    byDate: dailyPnl,
  };
}

function analyzeEngine(engine) {
  const daily = normalizeDailyPnl(engine.dailyPnl);
  const openPositions = safeNumber(engine.openPositions);
  const floatingPnl = safeNumber(engine.floatingPnl);
  const guardMode = String(engine.guardMode || 'UNKNOWN').toUpperCase();
  const closed = engine.recentTrades.filter((trade) => String(trade.status || '').toLowerCase() === 'closed');
  const wins = closed.filter((trade) => safeNumber(trade.pnl ?? trade.profit) > 0).length;
  const losses = closed.filter((trade) => safeNumber(trade.pnl ?? trade.profit) < 0).length;
  const netPnl = closed.reduce((sum, trade) => sum + safeNumber(trade.pnl ?? trade.profit), 0);
  const recommendations = [];

  if (guardMode === 'HARD_STOP') {
    recommendations.push({
      severity: 'critical',
      action: 'KEEP_HALTED',
      reason: `${engine.name} is in HARD_STOP; keep entries disabled until manual review.`,
    });
  } else if (guardMode === 'DEFENSE') {
    recommendations.push({
      severity: 'high',
      action: 'REDUCE_RISK',
      reason: `${engine.name} is in DEFENSE; keep lot multiplier low and trade only best strategy/symbol.`,
    });
  } else if (guardMode === 'CAUTION') {
    recommendations.push({
      severity: 'medium',
      action: 'TRADE_SELECTIVELY',
      reason: `${engine.name} is in CAUTION; avoid duplicate symbol/direction entries.`,
    });
  }

  if (losses >= 2 && losses > wins) {
    recommendations.push({
      severity: 'medium',
      action: 'PAUSE_RECENT_LOSERS',
      reason: `${engine.name} recent closed trades show ${losses} losses vs ${wins} wins.`,
    });
  }

  if (daily.value >= 20) {
    recommendations.push({
      severity: 'low',
      action: 'LOCK_DAILY_TARGET',
      reason: `${engine.name} daily PnL target reached (${daily.value.toFixed(2)}). Keep new entries paused.`,
    });
  } else if (daily.value <= -10) {
    recommendations.push({
      severity: 'high',
      action: 'ENTER_DEFENSE',
      reason: `${engine.name} daily PnL is ${daily.value.toFixed(2)}; reduce size and strategy breadth.`,
    });
  }

  return {
    ...engine,
    daily,
    recentClosed: closed.length,
    recentWins: wins,
    recentLosses: losses,
    recentNetPnl: Number(netPnl.toFixed(2)),
    floatingPnl,
    openPositions,
    recommendations,
  };
}

function summarizePortfolio(engines) {
  const totals = engines.reduce(
    (acc, engine) => {
      acc.openPositions += engine.openPositions;
      acc.floatingPnl += engine.floatingPnl;
      acc.dailyPnl += engine.daily.value;
      acc.recentNetPnl += engine.recentNetPnl;
      acc.recommendations += engine.recommendations.length;
      return acc;
    },
    { openPositions: 0, floatingPnl: 0, dailyPnl: 0, recentNetPnl: 0, recommendations: 0 },
  );
  const modes = engines.map((engine) => engine.guardMode);
  const guardMode = modes.includes('HARD_STOP')
    ? 'HARD_STOP'
    : modes.includes('DEFENSE')
      ? 'DEFENSE'
      : modes.includes('CAUTION')
        ? 'CAUTION'
        : 'NORMAL';
  return {
    guardMode,
    openPositions: totals.openPositions,
    floatingPnl: Number(totals.floatingPnl.toFixed(2)),
    dailyPnl: Number(totals.dailyPnl.toFixed(2)),
    recentNetPnl: Number(totals.recentNetPnl.toFixed(2)),
    recommendationCount: totals.recommendations,
  };
}

function normalizeMtaiState(state, history) {
  const summary = state?.summary || {};
  const accountRisk = summary.account_risk || {};
  const adaptive = summary.adaptive_guard || {};
  return {
    id: 'mtai',
    name: 'MTAI Forex',
    type: 'forex',
    status: 'online',
    guardMode: adaptive.mode || accountRisk.mode || 'UNKNOWN',
    guardReason: adaptive.reason || accountRisk.reason || '',
    account: {
      balance: safeNumber(accountRisk.balance ?? state?.account?.balance),
      equity: safeNumber(accountRisk.equity ?? state?.account?.equity),
      currency: state?.account?.currency || 'USD',
    },
    openPositions: safeNumber(accountRisk.open_positions),
    floatingPnl: safeNumber(accountRisk.floating_pnl),
    dailyPnl: summary.trade_journal?.daily_pnl || {},
    guard: {
      accountRisk,
      adaptive,
      performance: summary.performance_guard || {},
      positionDedup: summary.position_dedup_guard || {},
      timeframeFilter: summary.timeframe_filter || {},
    },
    recentTrades: history?.items || state?.order_history || [],
  };
}

function normalizeCryptoState(state, positions) {
  const summary = state?.summary || {};
  const strategyGuard = summary.strategy_performance_guard || {};
  return {
    id: 'crypto-ai',
    name: 'Crypto AI',
    type: 'crypto',
    status: 'online',
    guardMode: strategyGuard.guard_mode || 'UNKNOWN',
    guardReason: '',
    account: {
      balance: safeNumber(summary.total_equity),
      equity: safeNumber(summary.total_equity),
      currency: 'USDT',
    },
    openPositions: safeNumber(summary.open_positions ?? positions?.positions?.length),
    floatingPnl: (positions?.positions || []).reduce((sum, pos) => sum + safeNumber(pos.profit), 0),
    dailyPnl: {},
    guard: {
      strategyPerformance: strategyGuard,
    },
    recentTrades: state?.order_history || [],
  };
}

function ensureTradingSchema(db) {
  db.exec(`
    CREATE TABLE IF NOT EXISTS trading_snapshots (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      captured_at TEXT NOT NULL,
      engine_id TEXT NOT NULL,
      payload TEXT NOT NULL
    );
  `);
  db.exec(`
    CREATE TABLE IF NOT EXISTS daily_summaries (
      date TEXT NOT NULL,
      engine_id TEXT NOT NULL,
      net_pnl REAL NOT NULL DEFAULT 0,
      win_rate REAL NOT NULL DEFAULT 0,
      open_positions INTEGER NOT NULL DEFAULT 0,
      guard_mode TEXT NOT NULL DEFAULT 'UNKNOWN',
      recommendation_count INTEGER NOT NULL DEFAULT 0,
      payload TEXT NOT NULL,
      PRIMARY KEY (date, engine_id)
    );
  `);
  db.exec(`
    CREATE TABLE IF NOT EXISTS agent_recommendations (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      created_at TEXT NOT NULL,
      engine_id TEXT NOT NULL,
      severity TEXT NOT NULL,
      action TEXT NOT NULL,
      reason TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'pending'
    );
  `);
  db.exec(`
    CREATE TABLE IF NOT EXISTS guard_events (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      created_at TEXT NOT NULL,
      engine_id TEXT NOT NULL,
      guard_mode TEXT NOT NULL,
      reason TEXT NOT NULL
    );
  `);
}

function persistOverview(db, overview) {
  const capturedAt = overview.timestamp;
  const insertSnapshot = db.prepare(
    'INSERT INTO trading_snapshots (captured_at, engine_id, payload) VALUES (?, ?, ?)',
  );
  const upsertDaily = db.prepare(`
    INSERT INTO daily_summaries (date, engine_id, net_pnl, win_rate, open_positions, guard_mode, recommendation_count, payload)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(date, engine_id) DO UPDATE SET
      net_pnl=excluded.net_pnl,
      win_rate=excluded.win_rate,
      open_positions=excluded.open_positions,
      guard_mode=excluded.guard_mode,
      recommendation_count=excluded.recommendation_count,
      payload=excluded.payload
  `);
  const insertRecommendation = db.prepare(`
    INSERT INTO agent_recommendations (created_at, engine_id, severity, action, reason)
    VALUES (?, ?, ?, ?, ?)
  `);
  const findPendingRecommendation = db.prepare(`
    SELECT id FROM agent_recommendations
    WHERE engine_id = ? AND action = ? AND reason = ? AND status = 'pending'
    LIMIT 1
  `);

  for (const engine of overview.engines) {
    insertSnapshot.run(capturedAt, engine.id, JSON.stringify(engine));
    const date = engine.daily.date || capturedAt.slice(0, 10);
    const winRate = engine.recentClosed ? (engine.recentWins / engine.recentClosed) * 100 : 0;
    upsertDaily.run(
      date,
      engine.id,
      engine.daily.value,
      Number(winRate.toFixed(1)),
      engine.openPositions,
      engine.guardMode,
      engine.recommendations.length,
      JSON.stringify(engine),
    );
    for (const rec of engine.recommendations.slice(0, 5)) {
      const existing = findPendingRecommendation.get(engine.id, rec.action, rec.reason);
      if (!existing) {
        insertRecommendation.run(capturedAt, engine.id, rec.severity, rec.action, rec.reason);
      }
    }
  }
}

function buildReportText(overview) {
  const lines = [
    '*Hedge Fund AI Daily Control*',
    `เวลา: ${new Date(overview.timestamp).toLocaleString('th-TH', { timeZone: 'Asia/Bangkok' })}`,
    `Guard รวม: ${overview.portfolio.guardMode}`,
    `Open positions: ${overview.portfolio.openPositions}`,
    `Daily PnL รวม: ${overview.portfolio.dailyPnl.toFixed(2)}`,
    '',
  ];
  for (const engine of overview.engines) {
    lines.push(
      `*${engine.name}*`,
      `Mode: ${engine.guardMode}`,
      `Daily PnL: ${engine.daily.value.toFixed(2)} | Floating: ${engine.floatingPnl.toFixed(2)}`,
      `Recent W/L: ${engine.recentWins}/${engine.recentLosses}`,
    );
    for (const rec of engine.recommendations.slice(0, 3)) {
      lines.push(`- ${rec.action}: ${rec.reason}`);
    }
    lines.push('');
  }
  return lines.join('\n');
}

async function sendLineMessage(settings, text) {
  const token = settings.lineChannelAccessToken || process.env.LINE_CHANNEL_ACCESS_TOKEN;
  const to = settings.lineTargetId || process.env.LINE_TARGET_ID;
  if (token && to) {
    const res = await fetch('https://api.line.me/v2/bot/message/push', {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ to, messages: [{ type: 'text', text }] }),
    });
    return res.ok;
  }

  const legacyToken = settings.lineNotifyToken || process.env.LINE_NOTIFY_TOKEN;
  if (legacyToken) {
    const res = await fetch('https://notify-api.line.me/api/notify', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${legacyToken}`,
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: new URLSearchParams({ message: text }),
    });
    return res.ok;
  }
  return false;
}

async function collectOverview(getSettings) {
  const settings = getSettings();
  const trading = settings.tradingControl || {};
  const mtaiUrl = trading.mtaiUrl || DEFAULT_MTAI_URL;
  const cryptoUrl = trading.cryptoUrl || DEFAULT_CRYPTO_URL;

  const [mtaiState, mtaiHistory, cryptoState, cryptoPositions] = await Promise.all([
    fetchJson(`${mtaiUrl}/live_state.json`),
    fetchJson(`${mtaiUrl}/api/order_history?limit=200`),
    fetchJson(`${cryptoUrl}/live_state.json`),
    fetchJson(`${cryptoUrl}/api/positions`),
  ]);

  const engines = [];
  if (mtaiState.ok) engines.push(analyzeEngine(normalizeMtaiState(mtaiState.data, mtaiHistory.data)));
  else engines.push({ id: 'mtai', name: 'MTAI Forex', type: 'forex', status: 'offline', error: mtaiState.error, recommendations: [] });
  if (cryptoState.ok) engines.push(analyzeEngine(normalizeCryptoState(cryptoState.data, cryptoPositions.data)));
  else engines.push({ id: 'crypto-ai', name: 'Crypto AI', type: 'crypto', status: 'offline', error: cryptoState.error, recommendations: [] });

  return {
    timestamp: nowIso(),
    engines,
    portfolio: summarizePortfolio(engines.filter((engine) => engine.status === 'online')),
  };
}

export function installTradingControlRoutes(app, { db, getSettings, sendTelegramMessage }) {
  ensureTradingSchema(db);

  app.get('/api/trading/overview', async (req, res) => {
    try {
      const overview = await collectOverview(getSettings);
      persistOverview(db, overview);
      res.json(overview);
    } catch (err) {
      res.status(500).json({ error: err.message });
    }
  });

  app.get('/api/trading/daily-summary', (req, res) => {
    try {
      const rows = db.prepare('SELECT * FROM daily_summaries ORDER BY date DESC, engine_id ASC LIMIT 30').all();
      res.json({ items: rows.map((row) => ({ ...row, payload: JSON.parse(row.payload) })) });
    } catch (err) {
      res.status(500).json({ error: err.message });
    }
  });

  app.get('/api/trading/recommendations', (req, res) => {
    try {
      const rows = db.prepare('SELECT * FROM agent_recommendations ORDER BY created_at DESC LIMIT 50').all();
      res.json({ items: rows });
    } catch (err) {
      res.status(500).json({ error: err.message });
    }
  });

  app.post('/api/trading/report', async (req, res) => {
    try {
      const overview = await collectOverview(getSettings);
      persistOverview(db, overview);
      const text = buildReportText(overview);
      const settings = getSettings();
      const telegram = await sendTelegramMessage(text, settings.telegramBotToken, settings.telegramChatId);
      const line = await sendLineMessage(settings, text);
      res.json({ success: true, telegram, line, overview });
    } catch (err) {
      res.status(500).json({ error: err.message });
    }
  });
}
