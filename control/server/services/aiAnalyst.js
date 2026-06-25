import fetch from 'node-fetch';
import { collectTradingOverview } from './tradingControl.js';

const ANALYST_TIMEOUT_MS = Number(process.env.AI_ANALYST_TIMEOUT_MS || 45000);
let dailyReportTimer = null;
let lastDailyReportKey = '';

function nowIso() {
  return new Date().toISOString();
}

function safeNumber(value, fallback = 0) {
  const num = Number(value);
  return Number.isFinite(num) ? num : fallback;
}

function ensureAiSchema(db) {
  db.exec(`
    CREATE TABLE IF NOT EXISTS ai_analyst_reports (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      created_at TEXT NOT NULL,
      source TEXT NOT NULL,
      market_mode TEXT NOT NULL,
      summary TEXT NOT NULL,
      report_th TEXT NOT NULL,
      payload TEXT NOT NULL
    );
  `);
}

function normalizeAction(action) {
  return {
    engineId: action.engineId || action.engine_id || '',
    action: action.action || '',
    reason: action.reason || '',
    confidence: Math.max(0, Math.min(1, safeNumber(action.confidence, 0))),
    requiresConfirm: Boolean(action.requiresConfirm ?? action.requires_confirm),
    payload: action.payload || {},
  };
}

function safetyFilterActions(actions, overview) {
  const engines = Object.fromEntries((overview.engines || []).map((engine) => [engine.id, engine]));
  const safe = [];
  const rejected = [];

  for (const raw of actions || []) {
    const action = normalizeAction(raw);
    const engine = engines[action.engineId];
    const reject = (reason) => rejected.push({ ...action, rejectedReason: reason });

    if (!engine) {
      reject('unknown engine');
      continue;
    }
    if (!['pause', 'resume', 'close-position'].includes(action.action)) {
      reject('unsupported action');
      continue;
    }
    if (action.action === 'resume' && String(engine.guardMode || '').toUpperCase() === 'HARD_STOP') {
      reject('resume blocked while engine is HARD_STOP');
      continue;
    }
    if (action.action === 'close-position') {
      reject('close-position requires manual confirmation outside AI auto-apply');
      continue;
    }
    if (action.confidence < 0.6) {
      reject('confidence below 0.60');
      continue;
    }

    safe.push(action);
  }

  return { safe, rejected };
}

function fallbackAnalysis(overview) {
  const actions = [];
  const notes = [];
  let mode = overview.portfolio?.guardMode || 'NORMAL';

  for (const engine of overview.engines || []) {
    const guard = String(engine.guardMode || 'UNKNOWN').toUpperCase();
    const daily = safeNumber(engine.daily?.value);
    const floating = safeNumber(engine.floatingPnl);
    const losses = safeNumber(engine.recentLosses);
    const wins = safeNumber(engine.recentWins);

    if (guard === 'HARD_STOP') {
      mode = 'HARD_STOP';
      actions.push({
        engineId: engine.id,
        action: 'pause',
        reason: `${engine.name} is HARD_STOP; keep new entries paused until drawdown resets.`,
        confidence: 0.95,
      });
      notes.push(`${engine.name}: hard stop active, do not resume.`);
      continue;
    }

    if (daily <= -10 || floating <= -10 || losses > wins + 2) {
      mode = mode === 'HARD_STOP' ? mode : 'DEFENSE';
      actions.push({
        engineId: engine.id,
        action: 'pause',
        reason: `${engine.name} loss profile is weak: daily=${daily.toFixed(2)}, floating=${floating.toFixed(2)}, W/L=${wins}/${losses}.`,
        confidence: 0.78,
      });
      notes.push(`${engine.name}: reduce breadth and review losing strategies.`);
    } else if (daily >= 20) {
      actions.push({
        engineId: engine.id,
        action: 'pause',
        reason: `${engine.name} daily target reached; lock profit and stop new entries.`,
        confidence: 0.85,
      });
    } else {
      notes.push(`${engine.name}: no forced action; monitor open risk.`);
    }
  }

  const reportTh = [
    `โหมดรวม: ${mode}`,
    `Daily PnL รวม: ${safeNumber(overview.portfolio?.dailyPnl).toFixed(2)}`,
    `Floating PnL รวม: ${safeNumber(overview.portfolio?.floatingPnl).toFixed(2)}`,
    `Open positions: ${safeNumber(overview.portfolio?.openPositions)}`,
    '',
    ...notes.map((note) => `- ${note}`),
  ].join('\n');

  return {
    market_mode: mode,
    summary: notes.join(' '),
    actions,
    strategy_notes: notes,
    report_th: reportTh,
    source: 'fallback',
  };
}

function buildPrompt(overview, recentActions) {
  return [
    'You are a hedge fund trading risk analyst supervising two automated engines.',
    'Return ONLY valid JSON. Do not include markdown or prose.',
    'You may recommend pause/resume only. close-position must be marked requiresConfirm=true and should be rare.',
    'Never recommend resume while an engine is HARD_STOP.',
    '',
    `Current overview JSON: ${JSON.stringify(overview).slice(0, 12000)}`,
    `Recent control actions JSON: ${JSON.stringify(recentActions).slice(0, 4000)}`,
    '',
    'Return schema:',
    '{"market_mode":"NORMAL|CAUTION|DEFENSE|HARD_STOP","summary":"short English summary","actions":[{"engineId":"mtai|crypto-ai","action":"pause|resume|close-position","reason":"...","confidence":0.0,"requiresConfirm":false,"payload":{}}],"strategy_notes":["..."],"report_th":"Thai report text"}',
  ].join('\n');
}

function extractJson(text) {
  try {
    return JSON.parse(text);
  } catch (_) {
    const start = text.indexOf('{');
    const end = text.lastIndexOf('}');
    if (start >= 0 && end > start) {
      return JSON.parse(text.slice(start, end + 1));
    }
    throw new Error('LLM returned no JSON object');
  }
}

async function callLlm(settings, prompt) {
  const cfg = settings.llmConfig || {};
  const provider = cfg.provider || 'Gemini';
  const apiKey = cfg.apiKey || '';
  const model = cfg.model || 'default';
  const endpoint = cfg.endpoint || '';
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), ANALYST_TIMEOUT_MS);

  try {
    if (provider === 'Gemini') {
      if (!apiKey) throw new Error('Gemini API key not configured');
      const res = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${model || 'gemini-1.5-flash'}:generateContent?key=${apiKey}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: controller.signal,
        body: JSON.stringify({ contents: [{ role: 'user', parts: [{ text: prompt }] }] }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error?.message || `Gemini HTTP ${res.status}`);
      return extractJson(data.candidates?.[0]?.content?.parts?.[0]?.text || '{}');
    }

    const baseUrl = provider === 'Ollama'
      ? `${endpoint || 'http://127.0.0.1:11434'}/api/chat`
      : provider === 'Custom'
        ? `${endpoint.replace(/\/$/, '')}/v1/chat/completions`
        : endpoint || 'https://api.openai.com/v1/chat/completions';

    const headers = { 'Content-Type': 'application/json' };
    if (apiKey) headers.Authorization = `Bearer ${apiKey}`;
    const body = provider === 'Ollama'
      ? { model: model || 'llama3', stream: false, messages: [{ role: 'user', content: prompt }] }
      : { model: model || 'gpt-4o-mini', stream: false, messages: [{ role: 'user', content: prompt }] };
    const res = await fetch(baseUrl, { method: 'POST', headers, signal: controller.signal, body: JSON.stringify(body) });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error?.message || `${provider} HTTP ${res.status}`);
    const content = provider === 'Ollama' ? data.message?.content : data.choices?.[0]?.message?.content;
    return extractJson(content || '{}');
  } finally {
    clearTimeout(timer);
  }
}

function persistReport(db, report) {
  const payload = JSON.stringify(report);
  const row = db.prepare(`
    INSERT INTO ai_analyst_reports (created_at, source, market_mode, summary, report_th, payload)
    VALUES (?, ?, ?, ?, ?, ?)
  `).run(
    report.created_at,
    report.source,
    report.market_mode,
    report.summary,
    report.report_th,
    payload,
  );
  return row.lastInsertRowid;
}

function buildOutboundReport(report) {
  const overview = report.overview || {};
  const portfolio = overview.portfolio || {};
  const lines = [
    '*Hedge Fund AI Analyst Report*',
    `เวลา: ${new Date(report.created_at || nowIso()).toLocaleString('th-TH', { timeZone: 'Asia/Bangkok' })}`,
    `Mode: ${report.market_mode || 'UNKNOWN'} | Source: ${report.source || '-'}`,
    `Daily PnL: ${safeNumber(portfolio.dailyPnl).toFixed(2)} | Floating: ${safeNumber(portfolio.floatingPnl).toFixed(2)} | Open: ${safeNumber(portfolio.openPositions)}`,
    '',
    report.report_th || report.summary || 'No report text.',
  ];
  if ((report.safe_actions || []).length) {
    lines.push('', '*Safe actions*');
    for (const action of report.safe_actions) {
      lines.push(`- ${action.engineId} ${action.action}: ${action.reason}`);
    }
  }
  if ((report.rejected_actions || []).length) {
    lines.push('', '*Rejected actions*');
    for (const action of report.rejected_actions.slice(0, 5)) {
      lines.push(`- ${action.engineId} ${action.action}: ${action.rejectedReason}`);
    }
  }
  return lines.join('\n');
}

async function sendAnalystReport({ db, getSettings, notifications, sendTelegramMessage, forceAnalyze = false }) {
  let report = forceAnalyze ? await analyze({ db, getSettings }) : readLatest(db)?.payload;
  if (!report) report = await analyze({ db, getSettings });
  const settings = getSettings();
  const text = buildOutboundReport(report);
  const sent = notifications
    ? await notifications.sendChannels({ text, settings, type: 'ai_analyst_report', meta: { reportId: report.id || null } })
    : {
        telegram: await sendTelegramMessage(text, settings.telegramBotToken, settings.telegramChatId),
        line: false,
      };
  const { telegram, line } = sent;
  return { telegram, line, report };
}

function shouldSendDaily(settings) {
  const trading = settings.tradingControl || {};
  if (!trading.autoSendDailyReport) return null;
  const target = trading.dailyReportTime || '23:55';
  const now = new Date();
  const bangkok = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Bangkok',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(now).reduce((acc, part) => {
    acc[part.type] = part.value;
    return acc;
  }, {});
  const dateKey = `${bangkok.year}-${bangkok.month}-${bangkok.day}`;
  const timeKey = `${bangkok.hour}:${bangkok.minute}`;
  if (timeKey !== target) return null;
  return `${dateKey}T${target}`;
}

function readRecentControlActions(db) {
  try {
    return db.prepare('SELECT * FROM trading_control_actions ORDER BY created_at DESC LIMIT 20').all();
  } catch (_) {
    return [];
  }
}

export async function analyze({ db, getSettings }) {
  const settings = getSettings();
  const overview = await collectTradingOverview(getSettings);
  const recentActions = readRecentControlActions(db);
  let analysis;

  try {
    analysis = await callLlm(settings, buildPrompt(overview, recentActions));
    analysis.source = 'llm';
  } catch (err) {
    analysis = fallbackAnalysis(overview);
    analysis.llm_error = err.message;
  }

  const safety = safetyFilterActions(analysis.actions || [], overview);
  const report = {
    id: null,
    created_at: nowIso(),
    source: analysis.source || 'unknown',
    market_mode: analysis.market_mode || overview.portfolio?.guardMode || 'UNKNOWN',
    summary: analysis.summary || '',
    report_th: analysis.report_th || '',
    actions: (analysis.actions || []).map(normalizeAction),
    safe_actions: safety.safe,
    rejected_actions: safety.rejected,
    strategy_notes: analysis.strategy_notes || [],
    llm_error: analysis.llm_error || '',
    overview,
  };
  report.id = persistReport(db, report);
  return report;
}

function readLatest(db) {
  const row = db.prepare('SELECT * FROM ai_analyst_reports ORDER BY created_at DESC LIMIT 1').get();
  if (!row) return null;
  return { ...row, payload: JSON.parse(row.payload) };
}

function readReports(db) {
  const rows = db.prepare('SELECT * FROM ai_analyst_reports ORDER BY created_at DESC LIMIT 30').all();
  return rows.map((row) => ({ ...row, payload: JSON.parse(row.payload) }));
}

export function installAiAnalystRoutes(app, { db, getSettings, dispatchControlCommand, recordControlAction, notifications, sendTelegramMessage }) {
  ensureAiSchema(db);

  app.post('/api/trading/ai/analyze', async (req, res) => {
    try {
      res.json({ success: true, report: await analyze({ db, getSettings }) });
    } catch (err) {
      res.status(500).json({ success: false, error: err.message });
    }
  });

  app.get('/api/trading/ai/latest', (req, res) => {
    try {
      res.json({ report: readLatest(db) });
    } catch (err) {
      res.status(500).json({ error: err.message });
    }
  });

  app.get('/api/trading/ai/reports', (req, res) => {
    try {
      res.json({ items: readReports(db) });
    } catch (err) {
      res.status(500).json({ error: err.message });
    }
  });

  app.post('/api/trading/ai/send-report', async (req, res) => {
    try {
      const result = await sendAnalystReport({
        db,
        getSettings,
        notifications,
        sendTelegramMessage,
        forceAnalyze: Boolean(req.body?.forceAnalyze),
      });
      res.json({ success: true, ...result });
    } catch (err) {
      res.status(500).json({ success: false, error: err.message });
    }
  });

  app.post('/api/trading/ai/apply', async (req, res) => {
    try {
      const latest = readLatest(db);
      if (!latest) return res.status(404).json({ success: false, error: 'no AI report available' });
      const actions = latest.payload.safe_actions || [];
      const results = [];
      for (const action of actions) {
        const payload = { ...(action.payload || {}), reason: action.reason };
        const result = await dispatchControlCommand(getSettings, {
          engineId: action.engineId,
          action: action.action,
          payload,
        });
        recordControlAction(db, {
          engineId: action.engineId,
          action: action.action,
          status: result.ok ? 'success' : 'failed',
          reason: action.reason,
          payload,
          result,
        });
        results.push({ action, result });
      }
      res.json({ success: true, applied: results });
    } catch (err) {
      res.status(500).json({ success: false, error: err.message });
    }
  });

  if (!dailyReportTimer) {
    dailyReportTimer = setInterval(async () => {
      try {
        const sendKey = shouldSendDaily(getSettings());
        if (!sendKey || sendKey === lastDailyReportKey) return;
        lastDailyReportKey = sendKey;
        await sendAnalystReport({ db, getSettings, notifications, sendTelegramMessage, forceAnalyze: true });
      } catch (err) {
        console.warn(`AI analyst daily report failed: ${err.message}`);
      }
    }, 60 * 1000);
  }
}
