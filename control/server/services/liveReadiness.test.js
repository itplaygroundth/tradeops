import test from 'node:test';
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { evaluateEngine, roundTripCleanupOk, supersedeRunningSoaks } from './liveReadiness.js';

const profitable = {
  id: 'crypto-ai',
  status: 'online',
  runtimeMode: 'demo',
  control: { entries_paused: true },
  openPositions: 0,
  guardMode: 'NORMAL',
  performance: { sampleSize: 40, expectancy: 0.5, profitFactor: 1.2 },
};

test('testnet engine passes test preflight but needs soak for live', () => {
  const result = evaluateEngine(profitable, {
    mode: { mode: 'demo', network: 'testnet', credential_status: 'configured' },
    control: { entries_paused: true, credential_verified: true },
  }, null, { id: 1, network: 'testnet', symbol: 'BTCUSDT' });
  assert.equal(result.testReady, true);
  assert.equal(result.liveReady, false);
  assert.equal(result.checks.find((item) => item.id === 'soak_certification').status, 'FAIL');
});

test('missing credentials fail closed', () => {
  const result = evaluateEngine(profitable, {
    mode: { mode: 'demo', network: 'testnet', credential_status: 'missing' },
    control: { entries_paused: true, credential_verified: false },
  }, null, null);
  assert.equal(result.testReady, false);
});

test('forex requires explicit MT5 demo evidence', () => {
  const result = evaluateEngine({ ...profitable, id: 'mtai' }, {
    mode: { mode: 'demo', demo_account_verified: false },
    control: { entries_paused: true },
  }, null, null);
  assert.equal(result.testReady, false);
});

test('round-trip evidence accepts exchange lot-size dust after cleanup', () => {
  assert.equal(roundTripCleanupOk({ baseDeltaAfterCleanup: 0.00001 }), true);
  assert.equal(roundTripCleanupOk({ baseDeltaAfterCleanup: -0.00001 }), true);
  assert.equal(roundTripCleanupOk({ baseDeltaAfterCleanup: 0.00002 }), false);
});

test('starting a new soak supersedes only running soaks for the same engine', () => {
  const db = new DatabaseSync(':memory:');
  db.exec(`
    CREATE TABLE live_readiness_soaks (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      engine_id TEXT NOT NULL,
      started_at TEXT NOT NULL,
      required_hours REAL NOT NULL,
      status TEXT NOT NULL,
      baseline TEXT NOT NULL,
      result TEXT
    );
    INSERT INTO live_readiness_soaks (engine_id, started_at, required_hours, status, baseline)
    VALUES
      ('mtai', '2026-06-14T00:00:00.000Z', 24, 'running', '{}'),
      ('mtai', '2026-06-14T01:00:00.000Z', 24, 'passed', '{}'),
      ('crypto-ai', '2026-06-14T02:00:00.000Z', 24, 'running', '{}');
  `);

  const result = supersedeRunningSoaks(db, 'mtai', '2026-06-25T00:00:00.000Z');

  assert.equal(result.changes, 1);
  assert.equal(db.prepare('SELECT status FROM live_readiness_soaks WHERE id = 1').get().status, 'superseded');
  assert.equal(db.prepare('SELECT status FROM live_readiness_soaks WHERE id = 2').get().status, 'passed');
  assert.equal(db.prepare('SELECT status FROM live_readiness_soaks WHERE id = 3').get().status, 'running');
  const stored = JSON.parse(db.prepare('SELECT result FROM live_readiness_soaks WHERE id = 1').get().result);
  assert.equal(stored.reason, 'new soak started for engine');
});
