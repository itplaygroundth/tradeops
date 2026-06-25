import test from 'node:test';
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';

import {
  buildClosedTradeMessage,
  buildDailyMessage,
  createTradeNotificationMonitor,
  normalizeClosedTrades,
  summarizeTrades,
  tradeNotificationInternals,
} from './tradeNotificationMonitor.js';

test('normalizes crypto close and finds its entry metadata', () => {
  const rows = [
    {
      timestamp: 200,
      action: 'CLOSE',
      status: 'closed',
      ticket: 10,
      symbol: 'BTCUSDT',
      agent: 'CX-BTC',
      price: 102,
      pnl: 2,
      pnl_pct: 0.2,
      reason: 'take_profit',
    },
    {
      timestamp: 100,
      action: 'BUY',
      ticket: 10,
      symbol: 'BTCUSDT',
      agent: 'CX-BTC',
      price: 100,
      strategy: 'momentum',
      timeframe: 'M15',
    },
  ];
  const [trade] = normalizeClosedTrades('crypto-ai', rows);
  assert.equal(trade.entryPrice, 100);
  assert.equal(trade.exitPrice, 102);
  assert.equal(trade.strategy, 'momentum');
  assert.equal(trade.side, 'BUY');
});

test('summarizes wins, losses and profit factor', () => {
  const result = summarizeTrades([{ pnl: 10 }, { pnl: -4 }, { pnl: 2 }]);
  assert.equal(result.trades, 3);
  assert.equal(result.wins, 2);
  assert.equal(result.losses, 1);
  assert.equal(result.net, 8);
  assert.equal(result.profitFactor, 3);
});

test('closed trade message contains engine, pnl and daily total', () => {
  const text = buildClosedTradeMessage({
    engineName: 'Forex MT5',
    symbol: 'XAUUSD',
    side: 'SELL',
    pnl: 4.25,
    pnlPct: 0,
    volume: 0.02,
    entryPrice: 4100,
    exitPrice: 4098,
    strategy: 'trend_follow',
    timeframe: 'M15',
    agent: 'FX-1',
    reason: 'take_profit',
    closedAt: '2026-06-15T10:00:00.000Z',
  }, 7.5);
  assert.match(text, /Forex MT5/);
  assert.match(text, /\+4.25/);
  assert.match(text, /\+7.50/);
});

test('daily message combines forex and crypto', () => {
  const text = buildDailyMessage('2026-06-15', {
    mtai: [{ pnl: 5 }, { pnl: -2 }],
    'crypto-ai': [{ pnl: 3 }],
  }, { mtai: 0, 'crypto-ai': 1 });
  assert.match(text, /Forex: 2/);
  assert.match(text, /Crypto: 1/);
  assert.match(text, /Net PnL: \+6.00/);
});

test('event key uses canonical trade id for idempotency', () => {
  assert.equal(
    tradeNotificationInternals.incomingEventKey({
      engine_id: 'mtai',
      event_id: 'event-123',
      trade: { canonical_trade_id: 'EURUSDm:123:1781550247.781:-1.95' },
    }),
    'mtai:EURUSDm:123:2026-06-15T19:04:07.781Z:-1.95',
  );
});

test('processes producer event once and deduplicates retries', async () => {
  const db = new DatabaseSync(':memory:');
  const calls = [];
  const monitor = createTradeNotificationMonitor({
    db,
    getSettings: () => ({
      telegramBotToken: 'token',
      telegramChatId: 'chat',
      lineChannelAccessToken: 'line-token',
      lineTargetId: 'line-target',
      madsSupervisor: { enabled: false },
    }),
    notifications: {
      sendTelegramMessage: async () => {
        calls.push('telegram');
        return true;
      },
      sendLineMessage: async () => {
        calls.push('line');
        return true;
      },
    },
    fetchImpl: async () => ({ ok: true, json: async () => ({}) }),
  });
  const event = {
    event_id: 'close-1',
    event_type: 'trade.closed',
    engine_id: 'crypto-ai',
    occurred_at: 1_781_520_000,
    trade: {
      timestamp: 1_781_520_000,
      symbol: 'BTCUSDT',
      canonical_trade_id: 'BTCUSDT:10:1781520000.000:1.00',
      action: 'CLOSE',
      side: 'BUY',
      price: 101,
      entry_price: 100,
      pnl: 1,
      status: 'closed',
    },
  };

  const first = await monitor.processEvent(event);
  const second = await monitor.processEvent({ ...event, event_id: 'retry-with-new-uuid' });
  assert.equal(first.duplicate, false);
  assert.equal(second.duplicate, true);
  assert.deepEqual(calls, ['telegram', 'line']);
});

test('uses MT5 position ticket before deal ticket', () => {
  const [trade] = normalizeClosedTrades('mtai', [{
    timestamp: 1_781_550_247.780979,
    symbol: 'EURUSDm',
    ticket: 2085032488,
    deal_ticket: 1869749774,
    action: 'CLOSE',
    status: 'closed',
    pnl: -1.95,
  }]);
  assert.equal(
    trade.eventKey,
    'mtai:EURUSDm:2085032488:2026-06-15T19:04:07.780Z:-1.95',
  );
});

test('deduplicates MT5 exit deal when richer agent close exists', () => {
  const trades = normalizeClosedTrades('mtai', [
    {
      timestamp: 1_781_550_247.780979,
      agent: 'FX-EUR-000',
      symbol: 'EURUSDm',
      ticket: 2085032488,
      action: 'CLOSE',
      status: 'closed',
      pnl: -1.95,
      strategy: 'momentum',
      timeframe: 'M15',
      entry_price: 1.16104,
    },
    {
      timestamp: 1_781_550_246,
      agent: '[sl 1.15909]',
      symbol: 'EURUSDm',
      ticket: 1869749774,
      deal_ticket: 1869749774,
      deal_entry: 1,
      status: 'closed',
      type: 'closed',
      pnl: -1.95,
    },
  ]);
  assert.equal(trades.length, 1);
  assert.equal(trades[0].raw.ticket, 2085032488);
});
