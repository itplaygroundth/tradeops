import fetch from 'node-fetch';

const MIN_TRADES = Number(process.env.LIVE_MIN_CLOSED_TRADES || 30);
const MIN_PROFIT_FACTOR = Number(process.env.LIVE_MIN_PROFIT_FACTOR || 1.05);
const MIN_SOAK_HOURS = Number(process.env.LIVE_MIN_SOAK_HOURS || 24);

function check(id, status, observed, requirement) {
  return { id, status, observed, requirement };
}

function ensureSchema(db) {
  db.exec(`
    CREATE TABLE IF NOT EXISTS live_readiness_runs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      created_at TEXT NOT NULL,
      test_ready INTEGER NOT NULL,
      live_ready INTEGER NOT NULL,
      payload TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS live_readiness_soaks (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      engine_id TEXT NOT NULL,
      started_at TEXT NOT NULL,
      required_hours REAL NOT NULL,
      status TEXT NOT NULL,
      baseline TEXT NOT NULL,
      result TEXT
    );
    CREATE TABLE IF NOT EXISTS live_promotion_approvals (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      engine_id TEXT NOT NULL,
      created_at TEXT NOT NULL,
      expires_at TEXT NOT NULL,
      readiness_run_id INTEGER NOT NULL,
      status TEXT NOT NULL DEFAULT 'approved'
    );
    CREATE TABLE IF NOT EXISTS live_readiness_round_trips (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      engine_id TEXT NOT NULL,
      created_at TEXT NOT NULL,
      network TEXT NOT NULL,
      symbol TEXT NOT NULL,
      status TEXT NOT NULL,
      payload TEXT NOT NULL
    );
  `);
}

async function getJson(url) {
  try {
    const response = await fetch(url, { signal: AbortSignal.timeout(5000) });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return { ok: true, data: await response.json() };
  } catch (error) {
    return { ok: false, error: error.message };
  }
}

function latestPassedSoak(db, engineId) {
  return db.prepare(`
    SELECT * FROM live_readiness_soaks
    WHERE engine_id = ? AND status = 'passed'
    ORDER BY id DESC LIMIT 1
  `).get(engineId);
}

function latestPassedRoundTrip(db, engineId) {
  return db.prepare(`
    SELECT * FROM live_readiness_round_trips
    WHERE engine_id = ? AND status = 'passed'
    ORDER BY id DESC LIMIT 1
  `).get(engineId);
}

export function evaluateEngine(engine, evidence, soak, roundTrip) {
  const checks = [];
  const isForex = engine.id === 'mtai';
  const mode = evidence.mode?.mode || engine.runtimeMode;
  const control = evidence.control || engine.control || {};
  const performance = engine.performance || {};

  checks.push(check('engine_online', engine.status === 'online' ? 'PASS' : 'FAIL', engine.status, 'online'));
  checks.push(check(
    'safe_test_environment',
    isForex
      ? (mode === 'demo' && evidence.mode?.demo_account_verified === true ? 'PASS' : 'FAIL')
      : (mode === 'demo' && evidence.mode?.network === 'testnet' ? 'PASS' : 'FAIL'),
    isForex
      ? { mode, demo_account_verified: evidence.mode?.demo_account_verified ?? false }
      : { mode, network: evidence.mode?.network },
    isForex ? 'mode=demo and MT5 account verified as demo' : 'mode=demo and network=testnet',
  ));
  checks.push(check(
    'execution_credentials',
    isForex || evidence.control?.credential_verified === true ? 'PASS' : 'FAIL',
    isForex
      ? 'MT5 bridge'
      : {
          configured: evidence.mode?.credential_status,
          verified: evidence.control?.credential_verified ?? false,
          error: evidence.control?.credential_error || '',
        },
    isForex ? 'connected MT5 demo bridge' : 'authenticated Testnet account query',
  ));
  checks.push(check(
    'entries_paused',
    control.entries_paused === true ? 'PASS' : 'FAIL',
    control.entries_paused === true,
    'true during readiness and round-trip tests',
  ));
  checks.push(check(
    'flat_book',
    Number(engine.openPositions || 0) === 0 ? 'PASS' : 'FAIL',
    Number(engine.openPositions || 0),
    '0 open positions before test',
  ));
  checks.push(check(
    'risk_guard',
    ['HARD_STOP', 'DEFENSE'].includes(String(engine.guardMode).toUpperCase()) ? 'FAIL' : 'PASS',
    engine.guardMode,
    'not HARD_STOP or DEFENSE',
  ));

  const testReady = checks.every((item) => item.status === 'PASS');
  checks.push(check(
    'closed_trade_sample',
    Number(performance.sampleSize || 0) >= MIN_TRADES ? 'PASS' : 'FAIL',
    Number(performance.sampleSize || 0),
    `>= ${MIN_TRADES}`,
  ));
  checks.push(check(
    'positive_expectancy',
    Number(performance.expectancy || 0) > 0 ? 'PASS' : 'FAIL',
    Number(performance.expectancy || 0),
    '> 0',
  ));
  checks.push(check(
    'profit_factor',
    Number(performance.profitFactor || 0) >= MIN_PROFIT_FACTOR ? 'PASS' : 'FAIL',
    performance.profitFactor,
    `>= ${MIN_PROFIT_FACTOR}`,
  ));
  checks.push(check(
    'soak_certification',
    soak ? 'PASS' : 'FAIL',
    soak ? { id: soak.id, started_at: soak.started_at } : null,
    `passed soak >= ${MIN_SOAK_HOURS} hours`,
  ));
  checks.push(check(
    'controlled_round_trip',
    roundTrip ? 'PASS' : 'FAIL',
    roundTrip ? { id: roundTrip.id, network: roundTrip.network, symbol: roundTrip.symbol } : null,
    'verified open/close round-trip with flat cleanup',
  ));

  return {
    engineId: engine.id,
    testReady,
    liveReady: checks.every((item) => item.status === 'PASS'),
    checks,
  };
}

export function installLiveReadinessRoutes(app, {
  db,
  getSettings,
  collectTradingOverview,
  dispatchControlCommand,
}) {
  ensureSchema(db);

  async function runAssessment() {
    const settings = getSettings();
    const trading = settings.tradingControl || {};
    const overview = await collectTradingOverview(getSettings);
    const [forexMode, forexControl, cryptoMode, cryptoControl] = await Promise.all([
      getJson(`${trading.mtaiUrl || 'http://127.0.0.1:3003'}/api/mode`),
      getJson(`${trading.mtaiUrl || 'http://127.0.0.1:3003'}/api/control/status`),
      getJson(`${trading.cryptoUrl || 'http://127.0.0.1:3006'}/api/mode`),
      getJson(`${trading.cryptoUrl || 'http://127.0.0.1:3006'}/api/control/status`),
    ]);
    const evidenceById = {
      mtai: { mode: forexMode.data, control: forexControl.data },
      'crypto-ai': { mode: cryptoMode.data, control: cryptoControl.data },
    };
    const engines = overview.engines.map((engine) => evaluateEngine(
      engine,
      evidenceById[engine.id] || {},
      latestPassedSoak(db, engine.id),
      latestPassedRoundTrip(db, engine.id),
    ));
    const payload = {
      timestamp: new Date().toISOString(),
      testReady: engines.every((item) => item.testReady),
      liveReady: engines.every((item) => item.liveReady),
      engines,
    };
    const result = db.prepare(`
      INSERT INTO live_readiness_runs (created_at, test_ready, live_ready, payload)
      VALUES (?, ?, ?, ?)
    `).run(payload.timestamp, payload.testReady ? 1 : 0, payload.liveReady ? 1 : 0, JSON.stringify(payload));
    return { id: Number(result.lastInsertRowid), ...payload };
  }

  app.get('/api/live-readiness', (_req, res) => {
    const row = db.prepare('SELECT * FROM live_readiness_runs ORDER BY id DESC LIMIT 1').get();
    res.json(row ? { id: row.id, ...JSON.parse(row.payload) } : { status: 'not_assessed' });
  });

  app.post('/api/live-readiness/run', async (_req, res) => {
    try {
      res.json(await runAssessment());
    } catch (error) {
      res.status(503).json({ error: error.message });
    }
  });

  app.post('/api/live-readiness/round-trip/prepare', async (req, res) => {
    const engineId = req.body?.engineId;
    if (!['mtai', 'crypto-ai'].includes(engineId)) {
      return res.status(400).json({ error: 'engineId must be mtai or crypto-ai' });
    }
    await dispatchControlCommand(getSettings, {
      engineId,
      action: 'pause',
      payload: { reason: 'readiness round-trip preparation' },
    });
    const assessment = await runAssessment();
    const engine = assessment.engines.find((item) => item.engineId === engineId);
    return res.status(engine?.testReady ? 200 : 409).json({
      prepared: engine?.testReady === true,
      executionStarted: false,
      message: engine?.testReady
        ? 'Preflight passed. Execution remains manual and locked until explicit test implementation.'
        : 'Preflight failed; no order was sent.',
      assessment,
    });
  });

  app.post('/api/live-readiness/round-trip/evidence', (req, res) => {
    const payload = req.body || {};
    const engineId = payload.engineId;
    const valid = engineId === 'crypto-ai'
      && payload.network === 'testnet'
      && payload.success === true
      && payload.orderTestPassed === true
      && payload.buy?.status === 'FILLED'
      && payload.sell?.status === 'FILLED'
      && Number.isFinite(Number(payload.baseDeltaAfterCleanup))
      && Math.abs(Number(payload.baseDeltaAfterCleanup)) < 1e-8;
    if (!valid) {
      return res.status(400).json({ error: 'round-trip evidence failed validation' });
    }
    const result = db.prepare(`
      INSERT INTO live_readiness_round_trips
      (engine_id, created_at, network, symbol, status, payload)
      VALUES (?, ?, ?, ?, 'passed', ?)
    `).run(
      engineId,
      new Date().toISOString(),
      payload.network,
      payload.symbol || '',
      JSON.stringify(payload),
    );
    return res.json({ recorded: true, id: Number(result.lastInsertRowid), status: 'passed' });
  });

  app.post('/api/live-readiness/soak/start', async (req, res) => {
    const engineId = req.body?.engineId;
    if (!['mtai', 'crypto-ai'].includes(engineId)) {
      return res.status(400).json({ error: 'engineId must be mtai or crypto-ai' });
    }
    const assessment = await runAssessment();
    const engine = assessment.engines.find((item) => item.engineId === engineId);
    if (!engine?.testReady) return res.status(409).json({ error: 'test preflight has not passed', assessment });
    const hours = Math.max(MIN_SOAK_HOURS, Number(req.body?.hours || MIN_SOAK_HOURS));
    const result = db.prepare(`
      INSERT INTO live_readiness_soaks (engine_id, started_at, required_hours, status, baseline)
      VALUES (?, ?, ?, 'running', ?)
    `).run(engineId, new Date().toISOString(), hours, JSON.stringify(engine));
    return res.json({ id: Number(result.lastInsertRowid), engineId, requiredHours: hours, status: 'running' });
  });

  app.post('/api/live-readiness/soak/evaluate', async (req, res) => {
    const soak = db.prepare('SELECT * FROM live_readiness_soaks WHERE id = ?').get(Number(req.body?.id));
    if (!soak) return res.status(404).json({ error: 'soak not found' });
    const elapsedHours = (Date.now() - Date.parse(soak.started_at)) / 3_600_000;
    const assessment = await runAssessment();
    const engine = assessment.engines.find((item) => item.engineId === soak.engine_id);
    // Active demo soak must be allowed to trade. Pause/flat-book are required
    // for preflight and final promotion, not continuously during forward test.
    const soakChecks = engine?.checks.filter((item) => ![
      'soak_certification',
      'entries_paused',
      'flat_book',
      'closed_trade_sample',
      'positive_expectancy',
      'profit_factor',
    ].includes(item.id));
    const passed = elapsedHours >= soak.required_hours
      && soakChecks?.every((item) => item.status === 'PASS');
    const status = passed ? 'passed' : (elapsedHours >= soak.required_hours ? 'failed' : 'running');
    db.prepare('UPDATE live_readiness_soaks SET status = ?, result = ? WHERE id = ?')
      .run(status, JSON.stringify({ elapsedHours, assessment: engine }), soak.id);
    return res.json({ id: soak.id, status, elapsedHours, requiredHours: soak.required_hours, assessment: engine });
  });

  app.post('/api/live-readiness/promote', async (req, res) => {
    if (req.body?.confirm !== 'PROMOTE_TO_LIVE') {
      return res.status(400).json({ error: 'confirm must equal PROMOTE_TO_LIVE' });
    }
    const assessment = await runAssessment();
    const engine = assessment.engines.find((item) => item.engineId === req.body?.engineId);
    if (!engine?.liveReady) return res.status(409).json({ error: 'live readiness checks failed', assessment: engine });
    const expiresAt = new Date(Date.now() + 15 * 60_000).toISOString();
    const result = db.prepare(`
      INSERT INTO live_promotion_approvals (engine_id, created_at, expires_at, readiness_run_id)
      VALUES (?, ?, ?, ?)
    `).run(engine.engineId, new Date().toISOString(), expiresAt, assessment.id);
    return res.json({
      approved: true,
      approvalId: Number(result.lastInsertRowid),
      expiresAt,
      note: 'Approval is recorded; production mode still requires the deployment promotion token.',
    });
  });

  return { runAssessment };
}
