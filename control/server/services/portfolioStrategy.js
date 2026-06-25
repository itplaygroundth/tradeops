import crypto from 'crypto';

const TARGETS = {
  Conservative: { funds: 75, crypto: 5, forex: 20 },
  Balanced: { funds: 50, crypto: 20, forex: 30 },
  Aggressive: { funds: 25, crypto: 55, forex: 20 },
};

const PLAN_TO_RISK = {
  saving: 'Conservative',
  balance: 'Balanced',
  risk: 'Aggressive',
};

const previews = new Map();
const PREVIEW_TTL_MS = 10 * 60 * 1000;

function round(value, digits = 2) {
  return Number(Number(value || 0).toFixed(digits));
}

function portfolioSnapshot(db) {
  const assets = db.prepare('SELECT * FROM portfolio').all();
  const values = { funds: 0, crypto: 0, forex: 0 };
  for (const asset of assets) {
    values[asset.type] = (values[asset.type] || 0) + asset.units * asset.currentPrice;
  }
  const totalValue = Object.values(values).reduce((sum, value) => sum + value, 0);
  const weights = Object.fromEntries(
    Object.entries(values).map(([key, value]) => [key, totalValue > 0 ? round(value / totalValue * 100) : 0]),
  );
  return { assets, values, weights, totalValue: round(totalValue) };
}

function strategyRecommendation(db, riskProfile = 'Balanced') {
  const risk = TARGETS[riskProfile] ? riskProfile : 'Balanced';
  const targetWeights = TARGETS[risk];
  const snapshot = portfolioSnapshot(db);
  const recommendations = Object.keys(targetWeights).map((category) => {
    const difference = round(targetWeights[category] - snapshot.weights[category]);
    return {
      category,
      currentWeight: snapshot.weights[category],
      targetWeight: targetWeights[category],
      difference,
      amount: round(difference / 100 * snapshot.totalValue),
      action: difference > 2 ? 'BUY_MORE' : difference < -2 ? 'TAKE_PROFIT' : 'HOLD',
    };
  });
  return { riskProfile: risk, ...snapshot, targetWeights, recommendations };
}

function normalizeOpenAiBase(endpoint) {
  return String(endpoint || '').trim().replace(/\/+$/, '').replace(/\/v1$/i, '');
}

async function fetchWithTimeout(fetchImpl, url, options, timeoutMs = 45000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetchImpl(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

async function callLlm(settings, payload, fetchImpl) {
  const { provider, apiKey, model, endpoint } = settings.llmConfig || {};
  const system = [
    'You are an institutional portfolio strategist.',
    'Analyze only the supplied portfolio and deterministic risk-model output.',
    'Do not invent prices, returns, or holdings. Do not issue or execute trades.',
    'Respond in Thai as strict JSON with keys summary, rationale, risks, actions.',
    'summary and rationale are strings. risks and actions are arrays of short strings.',
    'Actions must respect the supplied target weights and approval-required workflow.',
  ].join(' ');
  const user = JSON.stringify(payload);

  if (!provider) throw new Error('LLM provider is not configured');
  if (provider === 'Gemini') {
    if (!apiKey) throw new Error('Gemini API key is not configured');
    const url = `https://generativelanguage.googleapis.com/v1beta/models/${model || 'gemini-1.5-flash'}:generateContent?key=${apiKey}`;
    const response = await fetchWithTimeout(fetchImpl, url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ contents: [{ role: 'user', parts: [{ text: `${system}\n\n${user}` }] }] }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error?.message || `Gemini HTTP ${response.status}`);
    return data.candidates?.[0]?.content?.parts?.[0]?.text || '';
  }

  if (provider === 'Ollama') {
    const response = await fetchWithTimeout(fetchImpl, `${String(endpoint || 'http://localhost:11434').replace(/\/+$/, '')}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: model || 'llama3',
        stream: false,
        format: 'json',
        messages: [{ role: 'system', content: system }, { role: 'user', content: user }],
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `Ollama HTTP ${response.status}`);
    return data.message?.content || '';
  }

  const base = provider === 'OpenAI'
    ? normalizeOpenAiBase(endpoint || 'https://api.openai.com')
    : normalizeOpenAiBase(endpoint);
  if (!base) throw new Error(`${provider} endpoint is not configured`);
  if (provider === 'OpenAI' && !apiKey) throw new Error('OpenAI API key is not configured');
  const headers = { 'Content-Type': 'application/json' };
  if (apiKey) headers.Authorization = `Bearer ${apiKey}`;
  const response = await fetchWithTimeout(fetchImpl, `${base}/v1/chat/completions`, {
    method: 'POST',
    headers,
    body: JSON.stringify({
      model: model || 'default',
      temperature: 0.2,
      max_tokens: 2500,
      messages: [{ role: 'system', content: system }, { role: 'user', content: user }],
    }),
  });
  const text = await response.text();
  let data;
  try {
    data = parseOpenAiPayload(text);
  } catch {
    throw new Error(`LLM returned invalid HTTP payload: ${text.slice(0, 160)}`);
  }
  if (!response.ok) throw new Error(data.error?.message || `LLM HTTP ${response.status}`);
  const message = data.choices?.[0]?.message || {};
  const content = String(message.content || '').trim();
  const reasoning = String(message.reasoning || '').trim();
  return content.length >= 80 ? content : (reasoning || content);
}

function parseLlmJson(text) {
  const cleaned = String(text || '').trim().replace(/^```json\s*/i, '').replace(/```$/i, '').trim();
  const start = cleaned.indexOf('{');
  const end = cleaned.lastIndexOf('}');
  if (start >= 0 && end > start) {
    try {
      const result = JSON.parse(cleaned.slice(start, end + 1));
      return {
        summary: String(result.summary || ''),
        rationale: String(result.rationale || ''),
        risks: Array.isArray(result.risks) ? result.risks.map(String).slice(0, 8) : [],
        actions: Array.isArray(result.actions) ? result.actions.map(String).slice(0, 8) : [],
      };
    } catch {
      // Some OpenAI-compatible proxies do not honor JSON mode.
    }
  }
  if (!cleaned) throw new Error('LLM returned an empty response');
  const readStringField = (field) => {
    const match = cleaned.match(new RegExp(`"${field}"\\s*:\\s*"((?:\\\\.|[^"\\\\])*)"`));
    if (!match) return '';
    try {
      return JSON.parse(`"${match[1]}"`);
    } catch {
      return match[1];
    }
  };
  const partialSummary = readStringField('summary');
  const partialRationale = readStringField('rationale');
  const bullets = cleaned.split('\n')
    .map((line) => line.replace(/^\s*[-*•]\s*/, '').trim())
    .filter((line) => line && line.length < 240)
    .slice(0, 8);
  return {
    summary: partialSummary || cleaned.slice(0, 1600),
    rationale: partialRationale || 'LLM provider returned free-form analysis; deterministic target weights remain authoritative.',
    risks: [],
    actions: bullets,
  };
}

function parseOpenAiPayload(text) {
  try {
    return JSON.parse(text);
  } catch (outerError) {
    const contentMatch = String(text).match(/"content"\s*:\s*("(?:\\.|[^"\\])*")/s);
    if (!contentMatch) throw outerError;
    const reasoningMatch = String(text).match(/"reasoning"\s*:\s*("(?:\\.|[^"\\])*")/s);
    return {
      choices: [{
        message: {
          content: JSON.parse(contentMatch[1]),
          reasoning: reasoningMatch ? JSON.parse(reasoningMatch[1]) : '',
        },
      }],
    };
  }
}

function buildPreview(db, riskProfile) {
  const strategy = strategyRecommendation(db, riskProfile);
  const trades = strategy.recommendations.flatMap((rec) => {
    if (rec.action === 'HOLD' || Math.abs(rec.amount) < 1) return [];
    const assets = strategy.assets
      .filter((asset) => asset.type === rec.category && asset.currentPrice > 0)
      .sort((a, b) => (b.units * b.currentPrice) - (a.units * a.currentPrice));
    const asset = assets[0];
    if (!asset) return [];
    const action = rec.amount > 0 ? 'buy' : 'sell';
    let units = Math.abs(rec.amount) / asset.currentPrice;
    if (action === 'sell') units = Math.min(units, asset.units);
    units = round(units, 4);
    if (units <= 0) return [];
    return [{
      category: rec.category,
      assetId: asset.id,
      assetName: asset.name,
      action,
      units,
      price: round(asset.currentPrice, 4),
      notional: round(units * asset.currentPrice),
      reason: `${rec.currentWeight}% -> ${rec.targetWeight}%`,
    }];
  });
  const token = crypto.randomUUID();
  const expiresAt = new Date(Date.now() + PREVIEW_TTL_MS).toISOString();
  const preview = {
    token,
    expiresAt,
    riskProfile: strategy.riskProfile,
    totalValue: strategy.totalValue,
    currentWeights: strategy.weights,
    targetWeights: strategy.targetWeights,
    trades,
    warnings: [
      'Preview adjusts the Hedgefund portfolio ledger only; it does not place broker or exchange orders.',
      'Values currently follow the dashboard valuation model and may mix source currencies.',
      'LLM commentary cannot change trade amounts or bypass approval.',
    ],
  };
  previews.set(token, preview);
  return preview;
}

function executePreview(db, token) {
  const preview = previews.get(token);
  if (!preview) throw new Error('Preview token is invalid or already used');
  if (Date.parse(preview.expiresAt) <= Date.now()) {
    previews.delete(token);
    throw new Error('Preview token expired');
  }

  db.exec('BEGIN IMMEDIATE;');
  try {
    for (const trade of preview.trades) {
      const asset = db.prepare('SELECT * FROM portfolio WHERE id = ? AND type = ?').get(trade.assetId, trade.category);
      if (!asset) throw new Error(`Asset ${trade.assetId} no longer exists`);
      let newUnits;
      let newAvgPrice = asset.avgBuyPrice;
      if (trade.action === 'buy') {
        newUnits = round(asset.units + trade.units, 4);
        newAvgPrice = round(((asset.units * asset.avgBuyPrice) + (trade.units * trade.price)) / newUnits, 4);
      } else {
        if (asset.units < trade.units) throw new Error(`Insufficient ${trade.assetId} units`);
        newUnits = round(asset.units - trade.units, 4);
      }
      db.prepare('UPDATE portfolio SET units = ?, avgBuyPrice = ? WHERE id = ?')
        .run(newUnits, newAvgPrice, trade.assetId);
      db.prepare('INSERT INTO transactions (assetId, type, action, units, price) VALUES (?, ?, ?, ?, ?)')
        .run(trade.assetId, trade.category, trade.action, trade.units, trade.price);
    }
    db.exec('COMMIT;');
    previews.delete(token);
    return { executed: true, trades: preview.trades, strategy: strategyRecommendation(db, preview.riskProfile) };
  } catch (error) {
    db.exec('ROLLBACK;');
    throw error;
  }
}

export function installPortfolioStrategyRoutes(app, { db, getSettings, fetchImpl }) {
  app.get('/api/portfolio/strategy', (req, res) => {
    const riskProfile = req.query.riskProfile || getSettings().riskProfile;
    res.json(strategyRecommendation(db, riskProfile));
  });

  app.post('/api/portfolio/strategy/analyze', async (req, res) => {
    try {
      const settings = getSettings();
      const riskProfile = req.body?.riskProfile || settings.riskProfile;
      const plan = req.body?.plan || Object.keys(PLAN_TO_RISK).find((key) => PLAN_TO_RISK[key] === riskProfile) || 'balance';
      const scenario = req.body?.scenario || 'normal';
      const strategy = strategyRecommendation(db, riskProfile);
      const strategyForLlm = {
        riskProfile: strategy.riskProfile,
        totalValue: strategy.totalValue,
        currentWeights: strategy.weights,
        targetWeights: strategy.targetWeights,
        recommendations: strategy.recommendations,
        holdings: strategy.assets.map((asset) => ({
          id: asset.id,
          type: asset.type,
          value: round(asset.units * asset.currentPrice),
        })),
      };
      const raw = await callLlm(settings, {
        request: 'Analyze portfolio strategy and proposed allocation. Approval is required before execution.',
        selectedPlan: plan,
        selectedScenario: scenario,
        deterministicModel: strategyForLlm,
      }, fetchImpl);
      res.json({
        mode: 'llm',
        provider: settings.llmConfig?.provider,
        model: settings.llmConfig?.model,
        generatedAt: new Date().toISOString(),
        analysis: parseLlmJson(raw),
        strategy,
      });
    } catch (error) {
      res.status(502).json({ error: `LLM strategy analysis failed: ${error.message}` });
    }
  });

  app.post('/api/portfolio/strategy/preview', (req, res) => {
    try {
      res.json(buildPreview(db, req.body?.riskProfile || getSettings().riskProfile));
    } catch (error) {
      res.status(400).json({ error: error.message });
    }
  });

  app.post('/api/portfolio/strategy/execute', (req, res) => {
    try {
      if (!req.body?.confirm || !req.body?.token) {
        return res.status(400).json({ error: 'confirm=true and preview token are required' });
      }
      return res.json(executePreview(db, req.body.token));
    } catch (error) {
      return res.status(400).json({ error: error.message });
    }
  });
}

export const portfolioStrategyInternals = {
  normalizeOpenAiBase,
  parseLlmJson,
  parseOpenAiPayload,
  portfolioSnapshot,
  strategyRecommendation,
};
