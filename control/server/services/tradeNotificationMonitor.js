import fetch from 'node-fetch';

const DEFAULT_POLL_MS = 5 * 60_000;
const DEFAULT_MTAI_URL = 'http://127.0.0.1:3003';
const DEFAULT_CRYPTO_URL = 'http://127.0.0.1:3006';

function safeNumber(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function bangkokParts(date = new Date()) {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Bangkok',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(date).reduce((parts, item) => {
    parts[item.type] = item.value;
    return parts;
  }, {});
}

function bangkokDateKey(value = new Date()) {
  const parts = bangkokParts(value instanceof Date ? value : new Date(value));
  return `${parts.year}-${parts.month}-${parts.day}`;
}

function tradeTimestamp(trade) {
  const value = trade.timestamp ?? trade.time ?? trade.closed_at ?? trade.close_time;
  if (typeof value === 'string' && value.trim()) {
    const parsed = Date.parse(value);
    if (Number.isFinite(parsed)) return new Date(parsed).toISOString();
  }
  const number = Number(value);
  if (Number.isFinite(number) && number > 0) {
    return new Date(number < 10_000_000_000 ? number * 1000 : number).toISOString();
  }
  return new Date().toISOString();
}

function isClosedTrade(trade) {
  return String(trade.status || '').toLowerCase() === 'closed'
    || String(trade.action || '').toUpperCase() === 'CLOSE';
}

function canonicalTradeKey(engineId, trade) {
  const provided = String(trade.canonical_trade_id || '').trim();
  if (provided) {
    const value = provided.startsWith(`${engineId}:`)
      ? provided.slice(engineId.length + 1)
      : provided;
    const match = value.match(/^([^:]+):([^:]+):([0-9.]+):(-?\d+(?:\.\d+)?)$/);
    if (match) {
      const [, symbol, identity, timestamp, pnl] = match;
      return `${engineId}:${symbol}:${identity}:${tradeTimestamp({ timestamp })}:${safeNumber(pnl).toFixed(2)}`;
    }
    return provided.startsWith(`${engineId}:`) ? provided : `${engineId}:${provided}`;
  }
  const closedAt = tradeTimestamp(trade);
  const identity = trade.ticket
    ?? trade.position
    ?? trade.deal_ticket
    ?? trade.position_id
    ?? trade.order_id
    ?? `${trade.symbol || 'unknown'}:${closedAt}:${trade.pnl ?? trade.profit ?? 0}`;
  const symbol = trade.symbol || 'UNKNOWN';
  const pnl = safeNumber(trade.pnl ?? trade.profit).toFixed(2);
  return `${engineId}:${symbol}:${identity}:${closedAt}:${pnl}`;
}

function eventKey(engineId, trade) {
  return canonicalTradeKey(engineId, trade);
}

function incomingEventKey(event) {
  return canonicalTradeKey(event.engine_id, event.trade || {});
}

function findCryptoEntry(trade, history) {
  return history.find((item) => (
    String(item.action || '').toUpperCase() === 'BUY'
    && item.symbol === trade.symbol
    && (!trade.agent || item.agent === trade.agent)
    && safeNumber(item.timestamp) <= safeNumber(trade.timestamp)
  )) || null;
}

export function normalizeClosedTrades(engineId, rows = []) {
  const normalized = rows.filter(isClosedTrade).map((trade) => {
    const entry = engineId === 'crypto-ai' ? findCryptoEntry(trade, rows) : null;
    const side = String(trade.side || trade.action || '').toUpperCase();
    return {
      eventKey: eventKey(engineId, trade),
      canonicalTradeId: canonicalTradeKey(engineId, trade),
      engineId,
      engineName: engineId === 'mtai' ? 'Forex MT5' : 'Crypto AI',
      symbol: trade.symbol || 'UNKNOWN',
      side: side === 'CLOSE' ? String(entry?.action || 'BUY').toUpperCase() : side,
      volume: safeNumber(trade.volume ?? trade.qty ?? trade.lots),
      entryPrice: safeNumber(trade.entry_price ?? trade.open_price ?? entry?.price),
      exitPrice: safeNumber(trade.exit_price ?? trade.close_price ?? trade.price),
      pnl: safeNumber(trade.pnl ?? trade.profit),
      pnlPct: safeNumber(trade.pnl_pct),
      commission: safeNumber(trade.commission),
      swap: safeNumber(trade.swap),
      strategy: trade.strategy || entry?.strategy || '',
      timeframe: trade.timeframe || entry?.timeframe || '',
      agent: trade.agent || entry?.agent || '',
      reason: trade.reason || trade.comment || '',
      closedAt: tradeTimestamp(trade),
      raw: trade,
    };
  });
  return normalized.filter((trade, index) => {
    const raw = trade.raw || {};
    const isBrokerExitDeal = raw.deal_entry != null && raw.deal_ticket != null;
    if (!isBrokerExitDeal) return true;
    const closedAtMs = Date.parse(trade.closedAt);
    return !normalized.some((candidate, candidateIndex) => {
      if (candidateIndex === index) return false;
      if (candidate.symbol !== trade.symbol) return false;
      if (Math.abs(safeNumber(candidate.pnl) - safeNumber(trade.pnl)) > 0.01) return false;
      if (Math.abs(Date.parse(candidate.closedAt) - closedAtMs) > 5_000) return false;
      const candidateRaw = candidate.raw || {};
      return candidateRaw.deal_entry == null && (
        candidate.strategy
        || candidate.timeframe
        || candidate.entryPrice
        || candidate.agent
      );
    });
  });
}

function money(value) {
  const number = safeNumber(value);
  return `${number >= 0 ? '+' : ''}${number.toFixed(2)}`;
}

function clean(value) {
  return String(value || '-').replaceAll('_', '-');
}

export function buildClosedTradeMessage(trade, dailyNet) {
  const outcome = trade.pnl >= 0 ? 'กำไร' : 'ขาดทุน';
  const lines = [
    `ปิดออเดอร์ ${trade.engineName}`,
    `${clean(trade.symbol)} ${clean(trade.side)} | ${outcome}`,
    `PnL: ${money(trade.pnl)}${trade.pnlPct ? ` (${money(trade.pnlPct)}%)` : ''}`,
  ];
  if (trade.volume) lines.push(`ขนาด: ${trade.volume}`);
  if (trade.entryPrice || trade.exitPrice) {
    lines.push(`ราคา: ${trade.entryPrice || '-'} -> ${trade.exitPrice || '-'}`);
  }
  if (trade.strategy || trade.timeframe || trade.agent) {
    lines.push(`ระบบ: ${clean(trade.strategy)} | TF ${clean(trade.timeframe)} | ${clean(trade.agent)}`);
  }
  if (trade.reason) lines.push(`เหตุผลปิด: ${clean(trade.reason)}`);
  lines.push(`ยอดสุทธิวันนี้ (${trade.engineName}): ${money(dailyNet)}`);
  lines.push(`เวลา: ${new Date(trade.closedAt).toLocaleString('th-TH', { timeZone: 'Asia/Bangkok' })}`);
  return lines.join('\n');
}

export function summarizeTrades(trades) {
  const wins = trades.filter((trade) => trade.pnl > 0);
  const losses = trades.filter((trade) => trade.pnl < 0);
  const grossProfit = wins.reduce((sum, trade) => sum + trade.pnl, 0);
  const grossLoss = Math.abs(losses.reduce((sum, trade) => sum + trade.pnl, 0));
  const net = trades.reduce((sum, trade) => sum + trade.pnl, 0);
  return {
    trades: trades.length,
    wins: wins.length,
    losses: losses.length,
    winRate: trades.length ? (wins.length / trades.length) * 100 : 0,
    grossProfit,
    grossLoss,
    net,
    profitFactor: grossLoss > 0 ? grossProfit / grossLoss : null,
  };
}

export function buildDailyMessage(dateKey, engineTrades, openPositions = {}) {
  const forex = summarizeTrades(engineTrades.mtai || []);
  const crypto = summarizeTrades(engineTrades['crypto-ai'] || []);
  const combined = summarizeTrades([...(engineTrades.mtai || []), ...(engineTrades['crypto-ai'] || [])]);
  const engineLine = (name, stats, open) => (
    `${name}: ${stats.trades} ไม้ | W/L ${stats.wins}/${stats.losses} | PnL ${money(stats.net)} | เปิดอยู่ ${open || 0}`
  );
  return [
    `สรุปผลการเทรดประจำวัน ${dateKey}`,
    engineLine('Forex', forex, openPositions.mtai),
    engineLine('Crypto', crypto, openPositions['crypto-ai']),
    '',
    `รวม: ${combined.trades} ไม้ | Win rate ${combined.winRate.toFixed(1)}%`,
    `Gross profit: ${money(combined.grossProfit)} | Gross loss: -${combined.grossLoss.toFixed(2)}`,
    `Net PnL: ${money(combined.net)}`,
    `Profit factor: ${combined.profitFactor == null ? 'N/A' : combined.profitFactor.toFixed(2)}`,
  ].join('\n');
}

function ensureSchema(db) {
  db.exec(`
    CREATE TABLE IF NOT EXISTS trade_notification_events (
      event_key TEXT PRIMARY KEY,
      engine_id TEXT NOT NULL,
      closed_at TEXT NOT NULL,
      pnl REAL NOT NULL DEFAULT 0,
      payload TEXT NOT NULL,
      notified_at TEXT
    );
    CREATE TABLE IF NOT EXISTS trade_notification_state (
      key TEXT PRIMARY KEY,
      value TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS trade_notification_deliveries (
      event_key TEXT NOT NULL,
      channel TEXT NOT NULL,
      delivered_at TEXT NOT NULL,
      PRIMARY KEY (event_key, channel)
    );
    CREATE TABLE IF NOT EXISTS daily_trade_notifications (
      date TEXT PRIMARY KEY,
      sent_at TEXT NOT NULL,
      payload TEXT NOT NULL
    );
  `);
}

async function fetchJson(url, fetchImpl) {
  const response = await fetchImpl(url);
  if (!response.ok) throw new Error(`${url} returned HTTP ${response.status}`);
  return response.json();
}

export function createTradeNotificationMonitor({
  db,
  getSettings,
  notifications,
  fetchImpl = fetch,
  pollMs = Number(process.env.TRADE_NOTIFICATION_POLL_MS || DEFAULT_POLL_MS),
  postCloseAnalyzer = null,
}) {
  ensureSchema(db);
  let timer = null;
  let running = false;
  let lastError = '';
  let lastPollAt = null;

  const isInitialized = (engineId) => Boolean(
    db.prepare('SELECT value FROM trade_notification_state WHERE key = ?').get(`initialized:${engineId}`),
  );
  const markInitialized = (engineId) => db.prepare(
    'INSERT OR REPLACE INTO trade_notification_state (key, value) VALUES (?, ?)',
  ).run(`initialized:${engineId}`, new Date().toISOString());
  const exists = (key) => Boolean(
    db.prepare('SELECT event_key FROM trade_notification_events WHERE event_key = ?').get(key),
  );
  const insert = (trade, notifiedAt = null) => db.prepare(`
    INSERT OR IGNORE INTO trade_notification_events
      (event_key, engine_id, closed_at, pnl, payload, notified_at)
    VALUES (?, ?, ?, ?, ?, ?)
  `).run(
    trade.eventKey,
    trade.engineId,
    trade.closedAt,
    trade.pnl,
    JSON.stringify(trade),
    notifiedAt,
  );

  function channelDelivered(eventKeyValue, channel) {
    return Boolean(db.prepare(`
      SELECT event_key FROM trade_notification_deliveries
      WHERE event_key = ? AND channel = ?
    `).get(eventKeyValue, channel));
  }

  function markChannelDelivered(eventKeyValue, channel) {
    db.prepare(`
      INSERT OR IGNORE INTO trade_notification_deliveries (event_key, channel, delivered_at)
      VALUES (?, ?, ?)
    `).run(eventKeyValue, channel, new Date().toISOString());
  }

  async function publishTradeEventToMads(trade) {
    const configured = getSettings().madsSupervisor || {};
    if (configured.enabled === false) return false;
    const apiUrl = String(configured.apiUrl || 'http://127.0.0.1:4311').replace(/\/$/, '');
    try {
      const response = await fetchImpl(`${apiUrl}/api/events`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          service: `tradeops-${trade.engineId}`,
          event: 'trade.closed',
          level: trade.pnl < 0 ? 'warn' : 'info',
          data: trade,
        }),
      });
      return response.ok;
    } catch (_) {
      return false;
    }
  }

  async function deliverTrade(trade) {
    const settings = getSettings();
    const text = buildClosedTradeMessage(
      trade,
      todayTrades(trade.engineId, bangkokDateKey(trade.closedAt))
        .reduce((sum, item) => sum + safeNumber(item.pnl), 0),
    );
    const expected = [];
    if (settings.telegramBotToken && settings.telegramChatId) expected.push('telegram');
    if (
      (settings.lineChannelAccessToken && settings.lineTargetId)
      || settings.lineNotifyToken
    ) expected.push('line');
    if (expected.length === 0) throw new Error('No notification channel configured');

    if (expected.includes('telegram') && !channelDelivered(trade.eventKey, 'telegram')) {
      const ok = await notifications.sendTelegramMessage(
        text,
        settings.telegramBotToken,
        settings.telegramChatId,
        { type: 'trade_closed', meta: { eventKey: trade.eventKey, engineId: trade.engineId } },
      );
      if (ok) markChannelDelivered(trade.eventKey, 'telegram');
    }
    if (expected.includes('line') && !channelDelivered(trade.eventKey, 'line')) {
      const ok = await notifications.sendLineMessage(
        text,
        settings.lineChannelAccessToken,
        settings.lineTargetId,
        settings.lineNotifyToken,
        { type: 'trade_closed', meta: { eventKey: trade.eventKey, engineId: trade.engineId } },
      );
      if (ok) markChannelDelivered(trade.eventKey, 'line');
    }
    const complete = expected.every((channel) => channelDelivered(trade.eventKey, channel));
    if (!complete) throw new Error('Trade event notification delivery incomplete');
    db.prepare('UPDATE trade_notification_events SET notified_at = ? WHERE event_key = ?')
      .run(new Date().toISOString(), trade.eventKey);
    const madsPublished = await publishTradeEventToMads(trade);
    let analysisTriggered = false;
    if (typeof postCloseAnalyzer === 'function') {
      try {
        await postCloseAnalyzer(trade);
        analysisTriggered = true;
      } catch (error) {
        console.warn('Post-close trade analysis failed for ' + trade.eventKey + ': ' + error.message);
      }
    }
    return { delivered: true, channels: expected, madsPublished, analysisTriggered };
  }

  async function load() {
    const trading = getSettings().tradingControl || {};
    const mtaiUrl = trading.mtaiUrl || DEFAULT_MTAI_URL;
    const cryptoUrl = trading.cryptoUrl || DEFAULT_CRYPTO_URL;
    const [forex, crypto, forexPositions, cryptoPositions] = await Promise.all([
      fetchJson(`${mtaiUrl}/api/order_history?limit=500`, fetchImpl),
      fetchJson(`${cryptoUrl}/live_state.json`, fetchImpl),
      fetchJson(`${mtaiUrl}/api/mt5/positions`, fetchImpl).catch(() => ({ positions: [] })),
      fetchJson(`${cryptoUrl}/api/positions`, fetchImpl).catch(() => ({ positions: [] })),
    ]);
    return {
      trades: {
        mtai: normalizeClosedTrades('mtai', forex.items || []),
        'crypto-ai': normalizeClosedTrades('crypto-ai', crypto.order_history || []),
      },
      openPositions: {
        mtai: (forexPositions.positions || []).length,
        'crypto-ai': (cryptoPositions.positions || []).length,
      },
    };
  }

  function todayTrades(engineId, dateKey) {
    return db.prepare(`
      SELECT payload FROM trade_notification_events
      WHERE engine_id = ? AND substr(datetime(closed_at, '+7 hours'), 1, 10) = ?
      ORDER BY closed_at ASC
    `).all(engineId, dateKey).map((row) => JSON.parse(row.payload));
  }

  async function processEngine(engineId, trades) {
    if (!isInitialized(engineId)) {
      for (const trade of trades) insert(trade);
      markInitialized(engineId);
      return { seeded: trades.length, sent: 0 };
    }
    let sent = 0;
    for (const trade of [...trades].sort((a, b) => a.closedAt.localeCompare(b.closedAt))) {
      if (!exists(trade.eventKey)) insert(trade);
      const stored = db.prepare(
        'SELECT notified_at FROM trade_notification_events WHERE event_key = ?',
      ).get(trade.eventKey);
      if (stored?.notified_at) continue;
      await deliverTrade(trade);
      sent += 1;
    }
    return { seeded: 0, sent };
  }

  async function processEvent(event) {
    if (event?.event_type !== 'trade.closed') {
      throw new Error('Unsupported event_type');
    }
    if (!['mtai', 'crypto-ai'].includes(event.engine_id)) {
      throw new Error('Unsupported engine_id');
    }
    const [trade] = normalizeClosedTrades(event.engine_id, [{
      ...(event.trade || {}),
      status: 'closed',
    }]);
    if (!trade) throw new Error('Invalid closed trade event');
    trade.eventKey = incomingEventKey(event);
    trade.closedAt = tradeTimestamp({ timestamp: event.occurred_at || event.trade?.timestamp });
    if (!exists(trade.eventKey)) insert(trade);
    const existing = db.prepare(
      'SELECT notified_at FROM trade_notification_events WHERE event_key = ?',
    ).get(trade.eventKey);
    if (existing?.notified_at) return { duplicate: true, eventKey: trade.eventKey };
    const delivery = await deliverTrade(trade);
    return { duplicate: false, eventKey: trade.eventKey, ...delivery };
  }

  async function sendDaily(force = false) {
    const settings = getSettings();
    const trading = settings.tradingControl || {};
    const parts = bangkokParts();
    const dateKey = `${parts.year}-${parts.month}-${parts.day}`;
    const target = trading.dailyReportTime || '23:55';
    const current = `${parts.hour}:${parts.minute}`;
    if (!force && (!trading.autoSendDailyReport || current !== target)) return { sent: false, reason: 'not_due' };
    if (!force && db.prepare('SELECT date FROM daily_trade_notifications WHERE date = ?').get(dateKey)) {
      return { sent: false, reason: 'already_sent' };
    }
    const loaded = await load();
    const engineTrades = {
      mtai: loaded.trades.mtai.filter((trade) => bangkokDateKey(trade.closedAt) === dateKey),
      'crypto-ai': loaded.trades['crypto-ai'].filter((trade) => bangkokDateKey(trade.closedAt) === dateKey),
    };
    const text = buildDailyMessage(dateKey, engineTrades, loaded.openPositions);
    const result = await notifications.sendChannels({
      text,
      type: 'daily_trade_summary',
      meta: { date: dateKey },
    });
    if ((result.telegram || result.line) && !force) {
      db.prepare(`
        INSERT OR REPLACE INTO daily_trade_notifications (date, sent_at, payload)
        VALUES (?, ?, ?)
      `).run(dateKey, new Date().toISOString(), JSON.stringify({ engineTrades, openPositions: loaded.openPositions }));
    }
    return { sent: Boolean(result.telegram || result.line), channels: result, text };
  }

  async function poll() {
    if (running) return;
    running = true;
    try {
      const loaded = await load();
      const forex = await processEngine('mtai', loaded.trades.mtai);
      const crypto = await processEngine('crypto-ai', loaded.trades['crypto-ai']);
      await sendDaily(false);
      lastPollAt = new Date().toISOString();
      lastError = '';
      return { forex, crypto, lastPollAt };
    } catch (error) {
      lastError = error.message;
      console.warn(`Trade notification monitor failed: ${error.message}`);
      return { error: error.message };
    } finally {
      running = false;
    }
  }

  function start() {
    if (timer) return;
    void poll();
    timer = setInterval(poll, pollMs);
  }

  function stop() {
    if (timer) clearInterval(timer);
    timer = null;
  }

  function status() {
    return {
      running: Boolean(timer),
      pollMs,
      lastPollAt,
      lastError,
      initialized: {
        mtai: isInitialized('mtai'),
        crypto: isInitialized('crypto-ai'),
      },
      deliveredTrades: db.prepare(
        'SELECT COUNT(*) AS count FROM trade_notification_events WHERE notified_at IS NOT NULL',
      ).get().count,
      lastTrade: db.prepare(`
        SELECT event_key, engine_id, closed_at, pnl, notified_at
        FROM trade_notification_events
        ORDER BY closed_at DESC LIMIT 1
      `).get() || null,
    };
  }

  return { start, stop, poll, processEvent, sendDaily, status };
}

export function installTradeNotificationRoutes(app, { monitor }) {
  app.get('/api/trading/notifications/status', (_req, res) => res.json(monitor.status()));
  app.post('/api/trading/notifications/send-daily', async (_req, res) => {
    try {
      res.json({ success: true, ...(await monitor.sendDaily(true)) });
    } catch (error) {
      res.status(500).json({ success: false, error: error.message });
    }
  });
  app.post('/api/trading/events', async (req, res) => {
    try {
      res.status(202).json({ accepted: true, ...(await monitor.processEvent(req.body || {})) });
    } catch (error) {
      res.status(503).json({ accepted: false, error: error.message });
    }
  });
}

export const tradeNotificationInternals = {
  bangkokDateKey,
  eventKey,
  incomingEventKey,
  isClosedTrade,
};
