import test from 'node:test';
import assert from 'node:assert/strict';

import {
  compactTradingOverview,
  madsSupervisorInternals,
  parseMadsSse,
  publishClosedTradesToMads,
  publishOverviewToMads,
  requestMadsTradingReview,
} from './madsSupervisor.js';

const overview = {
  timestamp: '2026-06-14T12:00:00.000Z',
  portfolio: { guardMode: 'CAUTION', dailyPnl: -3, floatingPnl: -1, openPositions: 2 },
  engines: [{
    id: 'crypto-ai',
    name: 'Crypto AI',
    type: 'crypto',
    status: 'online',
    guardMode: 'DEFENSE',
    daily: { value: -2 },
    floatingPnl: -1,
    openPositions: 1,
    recentWins: 1,
    recentLosses: 3,
    recommendations: [{ action: 'REDUCE_RISK', reason: 'loss streak' }],
  }],
};

test('compacts trading overview without full agent payloads', () => {
  const result = compactTradingOverview(overview);
  assert.equal(result.engines[0].guardMode, 'DEFENSE');
  assert.equal(result.engines[0].dailyPnl, -2);
  assert.equal(result.engines[0].recentLosses, 3);
});

test('publishes closed forex and crypto trades for post-trade review', async () => {
  const calls = [];
  const fetchImpl = async (url, options) => {
    calls.push({ url, body: JSON.parse(options.body) });
    return { ok: true, status: 200, text: async () => '{"ok":true}' };
  };
  const mixed = {
    ...overview,
    engines: [
      {
        ...overview.engines[0],
        id: 'mtai',
        recentTrades: [
          { status: 'closed', deal_ticket: 10, symbol: 'EURUSDm', pnl: -2 },
          { status: 'open', ticket: 11, symbol: 'EURUSDm', pnl: 0 },
        ],
        performance: { sampleSize: 12, expectancy: -0.2 },
      },
      {
        ...overview.engines[0],
        id: 'crypto-ai',
        recentTrades: [
          { action: 'CLOSE', ticket: 20, symbol: 'ETHUSDT', pnl: -4, pnl_pct: -1 },
          { action: 'BUY', ticket: 19, symbol: 'ETHUSDT', price: 1700, volume: 0.2, strategy: 'momentum', timeframe: 'M15' },
        ],
      },
    ],
  };
  const result = await publishClosedTradesToMads({
    fetchImpl,
    apiUrl: 'http://mads',
    overview: mixed,
  });
  assert.equal(result.length, 2);
  assert.equal(calls[0].url, 'http://mads/api/trading/review');
  assert.equal(calls[0].body.trades.length, 1);
  assert.equal(calls[1].body.engine_id, 'crypto-ai');
  assert.equal(calls[1].body.trades[0].entry_price, 1700);
  assert.equal(calls[1].body.trades[0].strategy, 'momentum');
});

test('closed trade detection is independent from snapshot changes', () => {
  assert.equal(
    madsSupervisorInternals.isClosedTrade({ status: 'closed' }),
    true,
  );
  assert.equal(
    madsSupervisorInternals.isClosedTrade({ action: 'CLOSE' }),
    true,
  );
  assert.equal(
    madsSupervisorInternals.isClosedTrade({ status: 'open' }),
    false,
  );
});

test('triggers advisory review when portfolio guard changes', () => {
  const previous = compactTradingOverview(overview);
  const current = structuredClone(previous);
  current.portfolio.guardMode = 'HARD_STOP';
  assert.equal(
    madsSupervisorInternals.automaticReviewTrigger(previous, current),
    'guard:CAUTION->HARD_STOP',
  );
});

test('snapshot fingerprint ignores activity timestamps and regime ages', () => {
  const first = compactTradingOverview(overview);
  first.engines[0].lastActivityAt = '2026-06-14T01:00:00Z';
  first.engines[0].regimes = { BTCUSDT: { regime: 'TREND_UP', age_s: 1 } };
  const second = structuredClone(first);
  second.timestamp = '2026-06-14T01:05:00Z';
  second.engines[0].lastActivityAt = '2026-06-14T01:05:00Z';
  second.engines[0].regimes.BTCUSDT.age_s = 301;
  assert.equal(
    madsSupervisorInternals.snapshotKey(first),
    madsSupervisorInternals.snapshotKey(second),
  );
});

test('parses the final MADS SSE result', () => {
  const result = parseMadsSse([
    'data: {"type":"progress","stage":"shadow"}',
    '',
    'data: {"type":"result","success":true,"output":"review","taskId":"abc"}',
    '',
  ].join('\n'));
  assert.equal(result.output, 'review');
  assert.equal(result.taskId, 'abc');
});

test('publishes portfolio and engine events', async () => {
  const calls = [];
  const fetchImpl = async (url, options) => {
    calls.push({ url, body: JSON.parse(options.body) });
    return { ok: true, status: 200, text: async () => '{"ok":true}' };
  };

  const result = await publishOverviewToMads({
    fetchImpl,
    apiUrl: 'http://mads',
    overview,
  });

  assert.equal(result.eventCount, 2);
  assert.equal(calls[0].url, 'http://mads/api/events');
  assert.equal(calls[1].body.level, 'warn');
});

test('forces the full MADS pipeline for trading reviews', async () => {
  let requestBody = null;
  const fetchImpl = async (_url, options) => {
    requestBody = JSON.parse(options.body);
    return {
      ok: true,
      status: 200,
      text: async () => 'data: {"type":"result","success":true,"output":"ok","council":{},"shadow":{}}\n\n',
    };
  };

  const result = await requestMadsTradingReview({
    fetchImpl,
    apiUrl: 'http://mads',
    overview,
  });

  assert.equal(requestBody.forceFull, true);
  assert.deepEqual(result.council, {});
  assert.deepEqual(result.shadow, {});
});
