import test from 'node:test';
import assert from 'node:assert/strict';
import { evaluateEngine } from './liveReadiness.js';

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
