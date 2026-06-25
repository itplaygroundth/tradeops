import { createHash } from 'crypto';

const DEFAULT_MADS_URL = process.env.MADS_API_URL || 'http://127.0.0.1:4311';
const DEFAULT_SYNC_MINUTES = 5;

function nowIso() {
  return new Date().toISOString();
}

function compactEngine(engine) {
  return {
    id: engine.id,
    name: engine.name,
    type: engine.type,
    status: engine.status,
    guardMode: engine.guardMode || 'UNKNOWN',
    dailyPnl: Number(engine.daily?.value || 0),
    floatingPnl: Number(engine.floatingPnl || 0),
    openPositions: Number(engine.openPositions || 0),
    runtimeMode: engine.runtimeMode || 'unknown',
    executionMode: engine.executionMode || 'unknown',
    network: engine.network || '',
    credentialStatus: engine.credentialStatus || '',
    lastActivityAt: engine.lastActivityAt || null,
    activityType: engine.activityType || 'unknown',
    idleReason: engine.idleReason || '',
    marketRegime: engine.marketRegime || 'UNKNOWN',
    regimes: engine.regimes || {},
    recentWins: Number(engine.recentWins || 0),
    recentLosses: Number(engine.recentLosses || 0),
    performance: engine.performance || {},
    recommendations: (engine.recommendations || []).slice(0, 5),
    error: engine.error || '',
  };
}

export function compactTradingOverview(overview) {
  return {
    timestamp: overview.timestamp,
    portfolio: {
      guardMode: overview.portfolio?.guardMode || 'UNKNOWN',
      dailyPnl: Number(overview.portfolio?.dailyPnl || 0),
      floatingPnl: Number(overview.portfolio?.floatingPnl || 0),
      openPositions: Number(overview.portfolio?.openPositions || 0),
    },
    engines: (overview.engines || []).map(compactEngine),
  };
}

export function parseMadsSse(text) {
  let result = null;
  for (const block of String(text || '').split(/\n\n+/)) {
    const line = block.split('\n').find((item) => item.startsWith('data:'));
    if (!line) continue;
    try {
      const event = JSON.parse(line.slice(5).trim());
      if (event.type === 'result') result = event;
      if (event.type === 'error') throw new Error(event.message || 'MADS task failed');
    } catch (error) {
      if (error instanceof SyntaxError) continue;
      throw error;
    }
  }
  if (!result) throw new Error('MADS returned no result event');
  return result;
}

function supervisorSettings(getSettings) {
  const configured = getSettings().madsSupervisor || {};
  return {
    enabled: configured.enabled !== false,
    apiUrl: configured.apiUrl || DEFAULT_MADS_URL,
    syncIntervalMinutes: Math.max(
      1,
      Number(configured.syncIntervalMinutes || DEFAULT_SYNC_MINUTES),
    ),
    autoDailyReview: configured.autoDailyReview !== false,
    dailyReviewTime: configured.dailyReviewTime || '23:58',
  };
}

function ensureSchema(db) {
  db.exec(`
    CREATE TABLE IF NOT EXISTS mads_supervisor_sync (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      created_at TEXT NOT NULL,
      status TEXT NOT NULL,
      event_count INTEGER NOT NULL DEFAULT 0,
      dedupe_key TEXT NOT NULL UNIQUE,
      error TEXT NOT NULL DEFAULT '',
      payload TEXT NOT NULL
    );
  `);
  db.exec(`
    CREATE TABLE IF NOT EXISTS mads_supervisor_reviews (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      created_at TEXT NOT NULL,
      status TEXT NOT NULL,
      vetoed INTEGER NOT NULL DEFAULT 0,
      output TEXT NOT NULL DEFAULT '',
      reason TEXT NOT NULL DEFAULT '',
      task_id TEXT NOT NULL DEFAULT '',
      trigger_key TEXT NOT NULL DEFAULT '',
      payload TEXT NOT NULL
    );
  `);
}

async function postJson(fetchImpl, url, body, timeoutMs = 20000) {
  let lastError = null;
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    try {
      const response = await fetchImpl(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(timeoutMs),
      });
      const text = await response.text();
      if (!response.ok) throw new Error(`MADS HTTP ${response.status}: ${text.slice(0, 200)}`);
      return text ? JSON.parse(text) : {};
    } catch (error) {
      lastError = error;
      if (attempt < 3) {
        await new Promise((resolve) => setTimeout(resolve, attempt * 250));
      }
    }
  }
  throw lastError;
}

export async function publishOverviewToMads({ fetchImpl, apiUrl, overview }) {
  const snapshot = compactTradingOverview(overview);
  const events = [
    {
      service: 'tradeops',
      event: 'portfolio_snapshot',
      level: snapshot.portfolio.guardMode === 'HARD_STOP' ? 'error' : 'info',
      data: snapshot.portfolio,
    },
    ...snapshot.engines.map((engine) => ({
      service: `tradeops-${engine.id}`,
      event: engine.status === 'online' ? 'engine_snapshot' : 'engine_offline',
      level: engine.status !== 'online'
        ? 'error'
        : ['DEFENSE', 'HARD_STOP'].includes(engine.guardMode) ? 'warn' : 'info',
      data: engine,
    })),
  ];

  for (const event of events) {
    await postJson(fetchImpl, `${apiUrl}/api/events`, event);
  }
  return { snapshot, eventCount: events.length };
}

function snapshotKey(snapshot) {
  const stable = {
    portfolio: snapshot.portfolio,
    engines: snapshot.engines.map((engine) => ({
      id: engine.id,
      status: engine.status,
      guardMode: engine.guardMode,
      dailyPnl: engine.dailyPnl,
      floatingPnl: engine.floatingPnl,
      openPositions: engine.openPositions,
      runtimeMode: engine.runtimeMode,
      executionMode: engine.executionMode,
      network: engine.network,
      credentialStatus: engine.credentialStatus,
      activityType: engine.activityType,
      idleReason: engine.idleReason,
      marketRegime: engine.marketRegime,
      regimes: Object.fromEntries(
        Object.entries(engine.regimes || {}).map(([symbol, value]) => [
          symbol,
          value?.regime || value,
        ]),
      ),
      performance: engine.performance,
      recommendations: engine.recommendations,
      error: engine.error,
    })),
  };
  return createHash('sha256')
    .update(JSON.stringify(stable))
    .digest('hex');
}

function automaticReviewTrigger(previous, current) {
  if (!previous) return '';
  const oldGuard = previous.portfolio?.guardMode || 'UNKNOWN';
  const newGuard = current.portfolio?.guardMode || 'UNKNOWN';
  if (oldGuard !== newGuard) return `guard:${oldGuard}->${newGuard}`;
  const stressed = current.engines.find((engine) => (
    ['DEFENSE', 'HARD_STOP'].includes(engine.guardMode)
    || (
      Number(engine.performance?.sampleSize || 0) >= 10
      && Number(engine.performance?.expectancy || 0) < 0
    )
  ));
  if (stressed) {
    return `stress:${stressed.id}:${stressed.guardMode}:${stressed.performance?.expectancy ?? 'guard'}`;
  }
  return '';
}

function isClosedTrade(trade) {
  return String(trade?.status || '').toLowerCase() === 'closed'
    || String(trade?.type || '').toLowerCase() === 'closed'
    || String(trade?.action || '').toUpperCase() === 'CLOSE';
}

function compactTrade(trade, entry = null) {
  const entryPrice = Number(trade.entry_price || entry?.entry_price || entry?.price || 0);
  const volume = Number(trade.volume ?? trade.qty ?? entry?.volume ?? entry?.qty ?? 0);
  return {
    trade_id: trade.trade_id || trade.deal_ticket || trade.ticket || '',
    timestamp: trade.timestamp || trade.time || null,
    symbol: trade.symbol || '',
    action: trade.action || '',
    agent: trade.agent || entry?.agent || '',
    strategy: trade.strategy || entry?.strategy || '',
    timeframe: trade.timeframe || entry?.timeframe || '',
    volume,
    price: Number(trade.price || 0),
    entry_price: entryPrice,
    exit_price: Number(trade.exit_price || trade.price || 0),
    entry_notional: Number((entryPrice * volume).toFixed(8)),
    pnl: Number(trade.pnl || 0),
    pnl_pct: Number(trade.pnl_pct || 0),
    fees: Number(trade.fees || trade.commission || 0),
    reason: trade.reason || trade.exit_reason || '',
    network: trade.network || '',
    type: trade.type || '',
  };
}

export async function publishClosedTradesToMads({ fetchImpl, apiUrl, overview }) {
  const results = [];
  for (const engine of overview.engines || []) {
    if (engine.status !== 'online') continue;
    const history = engine.recentTrades || [];
    const trades = history.filter(isClosedTrade).map((trade) => {
      const closeTime = Number(trade.timestamp || trade.time || Number.POSITIVE_INFINITY);
      const entry = history.find((candidate) => (
        !isClosedTrade(candidate)
        && String(candidate.symbol || '') === String(trade.symbol || '')
        && (!trade.agent || !candidate.agent || candidate.agent === trade.agent)
        && Number(candidate.timestamp || candidate.time || 0) <= closeTime
      ));
      return compactTrade(trade, entry || null);
    });
    if (trades.length === 0) continue;
    const result = await postJson(fetchImpl, `${apiUrl}/api/trading/review`, {
      engine_id: engine.id,
      trades,
      performance: engine.performance || {},
      context: {
        guard_mode: engine.guardMode || 'UNKNOWN',
        runtime_mode: engine.runtimeMode || 'unknown',
        execution_mode: engine.executionMode || 'unknown',
        network: engine.network || '',
        market_regime: engine.marketRegime || 'UNKNOWN',
        regimes: engine.regimes || {},
        recommendations: engine.recommendations || [],
      },
    }, 180000);
    results.push({ engineId: engine.id, ...result });
  }
  return results;
}

export async function requestMadsTradingReview({ fetchImpl, apiUrl, overview }) {
  const snapshot = compactTradingOverview(overview);
  const task = [
    'Review this TradeOps Forex and Crypto snapshot as a hedge-fund supervisory council.',
    'Advisory only: do not place orders and do not request direct position closure.',
    'Evaluate regime fit, loss concentration, drawdown risk, guard state, and strategy weaknesses.',
    'Use executionMode, credentialStatus, lastActivityAt, activityType, and idleReason before calling an engine silent or unhealthy.',
    'Judge strategy edge from expectancy, profitFactor, payoffRatio, and sampleSize; win rate alone is insufficient.',
    'Return a concise Thai report with market mode NORMAL/CAUTION/DEFENSE/HARD_STOP, evidence, and next actions.',
    `Snapshot JSON:\n${JSON.stringify(snapshot)}`,
  ].join('\n');

  const response = await fetchImpl(`${apiUrl}/api/zeus/task`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ task, forceFull: true }),
    signal: AbortSignal.timeout(360000),
  });
  const text = await response.text();
  if (!response.ok) throw new Error(`MADS HTTP ${response.status}: ${text.slice(0, 200)}`);
  const result = parseMadsSse(text);
  return {
    status: result.success ? 'completed' : 'vetoed',
    vetoed: Boolean(result.vetoed),
    output: result.output || '',
    reason: result.reason || '',
    taskId: result.taskId || '',
    council: result.council || null,
    shadow: result.shadow || null,
    snapshot,
  };
}

export function installMadsSupervisorRoutes(
  app,
  { db, getSettings, collectTradingOverview, dispatchControlCommand, fetchImpl },
) {
  ensureSchema(db);
  let syncRunning = false;
  let reviewRunning = false;
  let lastDailyReviewDate = '';
  let syncTimer = null;
  let dailyTimer = null;

  async function sync() {
    if (syncRunning) return { ok: false, skipped: 'sync already running' };
    const cfg = supervisorSettings(getSettings);
    if (!cfg.enabled) return { ok: false, skipped: 'MADS supervisor disabled' };
    syncRunning = true;
    try {
      const overview = await collectTradingOverview(getSettings);
      const snapshot = compactTradingOverview(overview);
      const tradeReviews = await publishClosedTradesToMads({
        fetchImpl,
        apiUrl: cfg.apiUrl.replace(/\/$/, ''),
        overview,
      });
      for (const review of tradeReviews) {
        const policy = review.defensive_policy
          || review.strategy_research?.campaign?.defensive_policy;
        if (!policy || !dispatchControlCommand) continue;
        await dispatchControlCommand(getSettings, {
          engineId: review.engineId,
          action: 'set-risk-policy',
          payload: policy,
        });
      }
      const dedupeKey = snapshotKey(snapshot);
      const duplicate = db.prepare(
        "SELECT id FROM mads_supervisor_sync WHERE dedupe_key = ? AND status = 'ok' LIMIT 1",
      ).get(dedupeKey);
      if (duplicate) {
        return {
          ok: true,
          skipped: 'unchanged snapshot',
          eventCount: 0,
          tradeReviews,
        };
      }
      const previousRow = db.prepare(
        "SELECT payload FROM mads_supervisor_sync WHERE status = 'ok' ORDER BY id DESC LIMIT 1",
      ).get();
      const previous = previousRow ? JSON.parse(previousRow.payload) : null;
      const result = await publishOverviewToMads({
        fetchImpl,
        apiUrl: cfg.apiUrl.replace(/\/$/, ''),
        overview,
      });
      db.prepare(`
        INSERT INTO mads_supervisor_sync (created_at, status, event_count, dedupe_key, payload)
        VALUES (?, 'ok', ?, ?, ?)
      `).run(nowIso(), result.eventCount, dedupeKey, JSON.stringify(snapshot));
      const trigger = automaticReviewTrigger(previous, snapshot);
      if (trigger) {
        setTimeout(() => review(trigger).catch(() => {}), 0).unref?.();
      }
      return { ok: true, eventCount: result.eventCount, tradeReviews, snapshot };
    } catch (error) {
      db.prepare(`
        INSERT INTO mads_supervisor_sync (created_at, status, dedupe_key, error, payload)
        VALUES (?, 'error', ?, ?, '{}')
      `).run(nowIso(), `error:${Date.now()}`, error.message);
      return { ok: false, error: error.message };
    } finally {
      syncRunning = false;
    }
  }

  async function review(triggerKey = 'manual') {
    if (reviewRunning) return { ok: false, skipped: 'review already running' };
    const cfg = supervisorSettings(getSettings);
    if (!cfg.enabled) return { ok: false, skipped: 'MADS supervisor disabled' };
    reviewRunning = true;
    try {
      const overview = await collectTradingOverview(getSettings);
      const today = nowIso().slice(0, 10);
      const normalizedTrigger = `${today}:${triggerKey}`;
      const duplicate = db.prepare(
        "SELECT id FROM mads_supervisor_reviews WHERE trigger_key = ? AND status IN ('completed', 'vetoed') LIMIT 1",
      ).get(normalizedTrigger);
      if (triggerKey !== 'manual' && duplicate) {
        return { ok: true, skipped: 'review trigger already processed' };
      }
      const result = await requestMadsTradingReview({
        fetchImpl,
        apiUrl: cfg.apiUrl.replace(/\/$/, ''),
        overview,
      });
      db.prepare(`
        INSERT INTO mads_supervisor_reviews
          (created_at, status, vetoed, output, reason, task_id, trigger_key, payload)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
      `).run(
        nowIso(),
        result.status,
        result.vetoed ? 1 : 0,
        result.output,
        result.reason,
        result.taskId,
        normalizedTrigger,
        JSON.stringify({
          council: result.council,
          shadow: result.shadow,
          snapshot: result.snapshot,
        }),
      );
      return { ok: true, ...result };
    } catch (error) {
      db.prepare(`
        INSERT INTO mads_supervisor_reviews (created_at, status, reason, trigger_key, payload)
        VALUES (?, 'error', ?, ?, '{}')
      `).run(nowIso(), error.message, `${nowIso().slice(0, 10)}:${triggerKey}`);
      return { ok: false, error: error.message };
    } finally {
      reviewRunning = false;
    }
  }

  const statusHandler = (_req, res) => {
    const latestSync = db.prepare(
      'SELECT * FROM mads_supervisor_sync ORDER BY id DESC LIMIT 1',
    ).get() || null;
    const latestReview = db.prepare(
      'SELECT * FROM mads_supervisor_reviews ORDER BY id DESC LIMIT 1',
    ).get() || null;
    res.json({
      settings: supervisorSettings(getSettings),
      running: { sync: syncRunning, review: reviewRunning },
      latestSync,
      latestReview,
    });
  };
  app.get('/api/mads/supervisor/status', statusHandler);
  app.get('/api/trading/supervisor/status', statusHandler);

  const reviewsHandler = (_req, res) => {
    const rows = db.prepare(
      'SELECT * FROM mads_supervisor_reviews ORDER BY id DESC LIMIT 30',
    ).all();
    res.json({
      items: rows.map((row) => ({
        ...row,
        payload: JSON.parse(row.payload || '{}'),
      })),
    });
  };
  app.get('/api/mads/reviews', reviewsHandler);
  app.get('/api/trading/supervisor/reviews', reviewsHandler);

  app.post('/api/mads/sync', async (_req, res) => {
    const result = await sync();
    res.status(result.ok || result.skipped ? 200 : 502).json(result);
  });

  app.post('/api/mads/review', async (_req, res) => {
    const result = await review('manual');
    res.status(result.ok || result.skipped ? 200 : 502).json(result);
  });
  app.post('/api/trading/supervisor/review', async (_req, res) => {
    const result = await review('manual');
    res.status(result.ok || result.skipped ? 200 : 502).json(result);
  });

  function start() {
    const cfg = supervisorSettings(getSettings);
    if (!cfg.enabled) return;
    const syncMs = cfg.syncIntervalMinutes * 60 * 1000;
    setTimeout(() => sync().catch(() => {}), 10000).unref?.();
    syncTimer = setInterval(() => sync().catch(() => {}), syncMs);
    syncTimer.unref?.();
    dailyTimer = setInterval(() => {
      const current = new Date();
      const bangkok = new Intl.DateTimeFormat('en-CA', {
        timeZone: 'Asia/Bangkok',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
      }).formatToParts(current).reduce((acc, item) => {
        acc[item.type] = item.value;
        return acc;
      }, {});
      const date = `${bangkok.year}-${bangkok.month}-${bangkok.day}`;
      const time = `${bangkok.hour}:${bangkok.minute}`;
      const latestCfg = supervisorSettings(getSettings);
      if (
        latestCfg.enabled
        && latestCfg.autoDailyReview
        && time === latestCfg.dailyReviewTime
        && lastDailyReviewDate !== date
      ) {
        lastDailyReviewDate = date;
        review('daily').catch(() => {});
      }
    }, 30000);
    dailyTimer.unref?.();
  }

  function stop() {
    if (syncTimer) clearInterval(syncTimer);
    if (dailyTimer) clearInterval(dailyTimer);
  }

  return { start, stop, sync, review };
}

export const madsSupervisorInternals = {
  compactEngine,
  supervisorSettings,
  snapshotKey,
  automaticReviewTrigger,
  isClosedTrade,
  compactTrade,
};
