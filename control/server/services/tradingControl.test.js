import test from 'node:test';
import assert from 'node:assert/strict';

import {
  analyzeEngine,
  normalizeCryptoState,
  normalizeMtaiState,
  tradingControlInternals,
} from './tradingControl.js';

test('performance metrics recognize profitable low win-rate payoff', () => {
  const closed = [
    { pnl: 10 }, { pnl: 10 }, { pnl: 10 }, { pnl: 10 },
    { pnl: -2 }, { pnl: -2 }, { pnl: -2 }, { pnl: -2 }, { pnl: -2 }, { pnl: -2 },
  ];
  const metrics = tradingControlInternals.performanceMetrics(closed);
  assert.equal(metrics.winRate, 40);
  assert.equal(metrics.expectancy, 2.8);
  assert.equal(metrics.profitFactor, 3.33);
});

test('engine recommendation uses expectancy instead of loss count alone', () => {
  const result = analyzeEngine({
    name: 'engine',
    guardMode: 'NORMAL',
    dailyPnl: {},
    openPositions: 0,
    floatingPnl: 0,
    recentTrades: [
      { status: 'closed', pnl: 10 }, { status: 'closed', pnl: 10 },
      { status: 'closed', pnl: 10 }, { status: 'closed', pnl: 10 },
      ...Array.from({ length: 6 }, () => ({ status: 'closed', pnl: -2 })),
    ],
  });
  assert.equal(result.performance.expectancy, 2.8);
  assert.equal(result.recommendations.some((item) => item.action === 'REVIEW_NEGATIVE_EXPECTANCY'), false);
});

test('portfolio guard escalates to caution for measured negative expectancy', () => {
  const engine = analyzeEngine({
    name: 'losing engine',
    guardMode: 'NORMAL',
    dailyPnl: {},
    openPositions: 0,
    floatingPnl: 0,
    recentTrades: Array.from({ length: 10 }, () => ({ status: 'closed', pnl: -1 })),
  });
  const portfolio = tradingControlInternals.summarizePortfolio([engine]);
  assert.equal(portfolio.guardMode, 'CAUTION');
});

test('crypto signal-only mode explains blocked activity', () => {
  const state = {
    summary: {
      execution_mode: 'signal_only',
      mode: 'demo',
      network: 'testnet',
      credential_status: 'missing',
      control: { credential_verified: false },
      uptime_seconds: 10,
      strategy_performance_guard: { guard_mode: 'NORMAL' },
      regime_service: { BTCUSDT: { regime: 'TREND_UP', age_s: 2 } },
    },
    order_history: [{
      timestamp: 1_781_421_324,
      type: 'signal_only',
      status: 'blocked',
      reason: 'testnet credentials missing',
    }],
  };
  const result = normalizeCryptoState(state, { positions: [] });
  assert.equal(result.activityType, 'market_data_monitoring');
  assert.match(result.idleReason, /credentials missing/);
  assert.equal(result.regimes.BTCUSDT.regime, 'TREND_UP');
});

test('forex weekend guard explains entry inactivity', () => {
  const state = {
    timestamp: 1_781_425_383,
    paper_mode: false,
    summary: {
      adaptive_guard: { mode: 'NORMAL' },
      weekend_reopen_guard: {
        pre_close: { status: 'active', reason: 'pre-weekend entry block active' },
      },
      regime: { current_regime: 'MIXED' },
      regime_service: { XAUUSDm: { regime: 'TREND_DOWN', age_s: 3 } },
      entry_audit: [{ timestamp: 1_781_425_382, status: 'blocked' }],
    },
    account: {},
  };
  const result = normalizeMtaiState(state, { items: [] }, { positions: [] }, {
    mode: 'demo',
    execution_environment: 'broker_demo',
    demo_account_verified: true,
  });
  assert.equal(result.idleReason, 'pre-weekend entry block active');
  assert.equal(result.activityType, 'entry_blocked');
  assert.equal(result.marketRegime, 'MIXED');
  assert.equal(result.runtimeMode, 'demo');
  assert.equal(result.executionMode, 'broker_demo');
  assert.equal(result.credentialStatus, 'verified');
});
