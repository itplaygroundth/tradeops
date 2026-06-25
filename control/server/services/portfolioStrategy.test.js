import test from 'node:test';
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { portfolioStrategyInternals } from './portfolioStrategy.js';

function createDb() {
  const db = new DatabaseSync(':memory:');
  db.exec(`
    CREATE TABLE portfolio (
      id TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      type TEXT NOT NULL,
      units REAL NOT NULL,
      avgBuyPrice REAL NOT NULL,
      currentPrice REAL NOT NULL,
      code_symbol_pair TEXT NOT NULL
    );
  `);
  const insert = db.prepare('INSERT INTO portfolio VALUES (?, ?, ?, ?, ?, ?, ?)');
  insert.run('FUND', 'Fund', 'funds', 50, 1, 1, 'FUND');
  insert.run('BTC', 'Bitcoin', 'crypto', 20, 1, 1, 'BTC');
  insert.run('EUR_USD', 'EUR/USD', 'forex', 30, 1, 1, 'EUR/USD');
  return db;
}

test('normalizes OpenAI-compatible endpoints without duplicating v1', () => {
  assert.equal(portfolioStrategyInternals.normalizeOpenAiBase('http://localhost:20128/v1'), 'http://localhost:20128');
  assert.equal(portfolioStrategyInternals.normalizeOpenAiBase('http://localhost:20128/'), 'http://localhost:20128');
});

test('balanced strategy preserves a balanced portfolio', () => {
  const result = portfolioStrategyInternals.strategyRecommendation(createDb(), 'Balanced');
  assert.deepEqual(result.targetWeights, { funds: 50, crypto: 20, forex: 30 });
  assert.ok(result.recommendations.every((item) => item.action === 'HOLD'));
});

test('unknown risk profile falls back to Balanced', () => {
  const result = portfolioStrategyInternals.strategyRecommendation(createDb(), 'Unknown');
  assert.equal(result.riskProfile, 'Balanced');
});

test('recovers content from a malformed OpenAI-compatible envelope', () => {
  const malformed = '{"choices":[{"message":{"content":"{\\"summary\\":\\"ok\\"}","reasoning":"useful analysis"}}]} trailing';
  const result = portfolioStrategyInternals.parseOpenAiPayload(malformed);
  assert.equal(result.choices[0].message.content, '{"summary":"ok"}');
  assert.equal(result.choices[0].message.reasoning, 'useful analysis');
});

test('extracts a useful summary from truncated model JSON', () => {
  const analysis = portfolioStrategyInternals.parseLlmJson('{"summary":"พอร์ตต้องปรับสมดุล","rationale":"ข้อความยังไม่จบ');
  assert.equal(analysis.summary, 'พอร์ตต้องปรับสมดุล');
});
