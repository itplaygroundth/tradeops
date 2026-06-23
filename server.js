import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';
import crypto from 'node:crypto';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const publicDir = path.join(__dirname, 'public');
const port = Number(process.env.PORT || 5175);
const tradeopsApiBase = process.env.TRADEOPS_API_BASE || 'http://127.0.0.1:5001';
const tradeopsRoot = process.env.TRADEOPS_ROOT || '/home/alfred/tradeops';
const dataDir = path.join(__dirname, 'data');
const experimentDir = path.join(dataDir, 'experiments');
const experimentLog = path.join(dataDir, 'experiments.jsonl');

const contentTypes = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
};

function send(res, statusCode, body, headers = {}) {
  res.writeHead(statusCode, headers);
  res.end(body);
}

function sendJson(res, statusCode, value) {
  send(res, statusCode, JSON.stringify(value, null, 2), { 'content-type': 'application/json; charset=utf-8' });
}

async function readJsonBody(req) {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  if (!chunks.length) return {};
  return JSON.parse(Buffer.concat(chunks).toString('utf8'));
}

function safePublicPath(urlPath) {
  const requested = urlPath === '/' ? '/index.html' : urlPath;
  const normalized = path.normalize(decodeURIComponent(requested)).replace(/^(\.\.[/\\])+/, '');
  const fullPath = path.join(publicDir, normalized);
  return fullPath.startsWith(publicDir) ? fullPath : null;
}

async function proxyApi(req, res) {
  const target = new URL(req.url, tradeopsApiBase);
  const headers = { ...req.headers };
  delete headers.host;

  try {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    const response = await fetch(target, {
      method: req.method,
      headers,
      body: chunks.length ? Buffer.concat(chunks) : undefined,
    });
    const body = Buffer.from(await response.arrayBuffer());
    const responseHeaders = Object.fromEntries(response.headers.entries());
    delete responseHeaders['content-encoding'];
    delete responseHeaders['content-length'];
    send(res, response.status, body, responseHeaders);
  } catch (error) {
    send(
      res,
      502,
      JSON.stringify({ error: 'TradeOps API proxy failed', detail: error.message, tradeopsApiBase }),
      { 'content-type': 'application/json; charset=utf-8' },
    );
  }
}

function readJsonSafe(filePath, fallback = null) {
  try {
    return JSON.parse(fs.readFileSync(filePath, 'utf8'));
  } catch {
    return fallback;
  }
}

function listStrategyProposals() {
  const roots = [
    path.join(tradeopsRoot, 'strategy_lab', 'strategies'),
    path.join(tradeopsRoot, 'strategy_lab', 'strategies', 'generated'),
  ];
  const proposals = [];
  for (const root of roots) {
    if (!fs.existsSync(root)) continue;
    for (const name of fs.readdirSync(root).filter((item) => item.endsWith('.json')).sort()) {
      const filePath = path.join(root, name);
      const raw = readJsonSafe(filePath);
      if (!raw) continue;
      proposals.push({
        id: path.relative(path.join(tradeopsRoot, 'strategy_lab'), filePath).replaceAll(path.sep, '/'),
        path: filePath,
        name: raw.name || name.replace(/\.json$/, ''),
        version: raw.version || 1,
        market: raw.market || 'unknown',
        symbols: raw.symbols || [],
        type: raw.type || 'unknown',
        timeframe: raw.timeframes?.entry || 'M15',
        status: raw.status || 'draft',
      });
    }
  }
  return proposals;
}

function resolveProposal(id) {
  const proposal = listStrategyProposals().find((item) => item.id === id || item.name === id);
  if (!proposal) throw new Error(`unknown proposal: ${id}`);
  if (!proposal.path.startsWith(path.join(tradeopsRoot, 'strategy_lab'))) {
    throw new Error('proposal path escapes strategy_lab');
  }
  return proposal;
}

function syntheticCandles({ regime = 'baseline', count = 520, start = 65000 }) {
  const candles = [];
  let close = Number(start) || 65000;
  const limit = Math.max(120, Math.min(Number(count) || 520, 1000));
  for (let index = 0; index < limit; index += 1) {
    const wave = Math.sin(index / 9) * 0.004 + Math.cos(index / 23) * 0.003;
    const regimeDrift = regime === 'crash'
      ? (index > limit * 0.55 ? -0.006 : 0.001)
      : regime === 'sideways'
        ? 0
        : regime === 'high_volatility'
          ? Math.sin(index / 3) * 0.012
          : 0.0015;
    const shock = regime === 'high_volatility' && index % 37 === 0 ? -0.035 : 0;
    const open = close;
    close = Math.max(1, close * (1 + wave + regimeDrift + shock));
    const spread = Math.abs(close - open) + close * (regime === 'high_volatility' ? 0.012 : 0.004);
    candles.push({
      time: 1700000000 + index * 900,
      open,
      high: Math.max(open, close) + spread,
      low: Math.max(1, Math.min(open, close) - spread),
      close,
      volume: 100 + (index % 50) * 3,
      taker_buy: 50 + (index % 20),
    });
  }
  return candles;
}

function runCommand(command, args, { cwd = tradeopsRoot, timeoutMs = 120000 } = {}) {
  return new Promise((resolve) => {
    const startedAt = Date.now();
    const child = spawn(command, args, { cwd, stdio: ['ignore', 'pipe', 'pipe'] });
    let stdout = '';
    let stderr = '';
    const timer = setTimeout(() => {
      child.kill('SIGTERM');
      stderr += '\nprocess timeout';
    }, timeoutMs);
    child.stdout.on('data', (chunk) => { stdout += chunk.toString(); });
    child.stderr.on('data', (chunk) => { stderr += chunk.toString(); });
    child.on('close', (code) => {
      clearTimeout(timer);
      resolve({ command: `${command} ${args.join(' ')}`, code, ok: code === 0, stdout, stderr, durationMs: Date.now() - startedAt });
    });
  });
}

function evaluateExperiment(experiment) {
  const baseline = experiment.results.baseline?.report || {};
  const optimized = experiment.results.optimization?.report || {};
  const stressReports = Object.values(experiment.results.stress || {}).map((item) => item.report || {});
  const blockers = [];
  const advice = [];
  if ((baseline.trades || 0) < 5) blockers.push('baseline มีจำนวน trades น้อยเกินไป');
  if ((baseline.expectancy_pct || 0) <= 0) blockers.push('baseline expectancy ยังไม่เป็นบวก');
  if ((optimized.best?.score || optimized.best?.metrics?.sortino || 0) <= 0 && !experiment.results.optimization?.passed) {
    advice.push('optimization ยังไม่พบ parameter set ที่ชนะ gate ชัดเจน');
  }
  for (const report of stressReports) {
    if ((report.max_drawdown_pct || 0) > 8) blockers.push(`stress ${report.symbol || ''} drawdown เกิน 8%`);
    if ((report.expectancy_pct || 0) <= 0) advice.push(`stress ${report.symbol || ''} expectancy ไม่เป็นบวก`);
  }
  const passed = blockers.length === 0 && stressReports.every((report) => report.approved_for_forward_test);
  return {
    source: 'deterministic_agent_evaluator',
    verdict: passed ? 'PASS_FOR_SHADOW_REVIEW' : 'NEEDS_TUNING',
    score: passed ? 82 : Math.max(25, 70 - blockers.length * 12 - advice.length * 5),
    summary_th: passed
      ? 'ระบบผ่าน baseline และ synthetic stress เบื้องต้น สามารถส่งต่อเข้า shadow/testnet review ได้'
      : 'ระบบยังไม่ควร promote ควรปรับ strategy/parameter และทดสอบซ้ำก่อนเข้า shadow/testnet',
    blockers,
    advice,
  };
}

function appendExperiment(experiment) {
  fs.mkdirSync(dataDir, { recursive: true });
  fs.appendFileSync(experimentLog, `${JSON.stringify(experiment)}\n`);
}

function listExperiments() {
  if (!fs.existsSync(experimentLog)) return [];
  return fs.readFileSync(experimentLog, 'utf8')
    .split('\n')
    .filter(Boolean)
    .map((line) => JSON.parse(line))
    .reverse();
}

function fileMeta(relativePath) {
  const fullPath = path.join(tradeopsRoot, relativePath);
  try {
    const stat = fs.statSync(fullPath);
    return { exists: true, updated_at: stat.mtime.toISOString(), path: relativePath };
  } catch {
    return { exists: false, updated_at: null, path: relativePath };
  }
}

function localFileMeta(relativePath) {
  const fullPath = path.join(__dirname, relativePath);
  try {
    const stat = fs.statSync(fullPath);
    return { exists: true, updated_at: stat.mtime.toISOString(), path: relativePath };
  } catch {
    return { exists: false, updated_at: null, path: relativePath };
  }
}

function agentState({ id, name, role, mode = 'manual_or_api_triggered', evidence = [], latest = null, canSelectStrategy = false, canExecuteOrders = false }) {
  const readyEvidence = evidence.filter((item) => item.exists);
  const status = readyEvidence.length ? 'ready' : 'idle';
  return {
    id,
    name,
    role,
    status,
    mode,
    latest_at: latest?.updated_at || readyEvidence.map((item) => item.updated_at).filter(Boolean).sort().at(-1) || null,
    evidence,
    can_select_strategy: canSelectStrategy,
    can_execute_orders: canExecuteOrders,
  };
}

function listAgentStatus() {
  const experiments = listExperiments();
  const latestExperiment = experiments[0] || null;
  const latestExperimentMeta = localFileMeta('data/experiments.jsonl');
  const registry = fileMeta('strategy_lab/registry/approved_strategies.json');
  const shadowDeployments = fileMeta('strategy_lab/shadow/deployments.json');
  const shadowSignals = fileMeta('strategy_lab/shadow/signals.jsonl');
  const madsReviews = fileMeta('strategy_lab/reports/research_reviews.jsonl');
  const latestReview = fileMeta('strategy_lab/reports/latest_research_review.json');
  const batchSummary = fileMeta('strategy_lab/reports/batch_summary.json');
  const papers = fileMeta('research_lab/reports/latest_papers.json');
  const hypotheses = fileMeta('research_lab/reports/latest_hypotheses.json');
  const proposals = fileMeta('research_lab/reports/latest_generated_proposals.json');
  const handoff = fileMeta('strategy_lab/handoff/execution_handoff.json');
  const dispatchResults = fileMeta('strategy_lab/handoff/staged_dispatch_results.jsonl');

  const agents = [
    agentState({
      id: 'research-scout-agent',
      name: 'Research Scout Agent',
      role: 'ค้น paper/idea แล้วแปลงเป็น research candidates',
      evidence: [papers],
    }),
    agentState({
      id: 'hypothesis-agent',
      name: 'Hypothesis & Proposal Agent',
      role: 'ย่อย paper เป็น hypothesis และสร้าง strategy proposal',
      evidence: [hypotheses, proposals],
    }),
    agentState({
      id: 'experiment-agent',
      name: 'Experiment Runner Agent',
      role: 'รัน baseline backtest, optimization, synthetic stress และบันทึก experiment registry',
      evidence: [latestExperimentMeta],
      latest: latestExperimentMeta,
      canSelectStrategy: true,
    }),
    agentState({
      id: 'optimizer-agent',
      name: 'Optimizer Agent',
      role: 'ค้น parameter set จาก Strategy Lab แล้วเลือก candidate ที่ผ่าน gate',
      evidence: [batchSummary, registry],
      canSelectStrategy: true,
    }),
    agentState({
      id: 'robustness-agent',
      name: 'Robustness Test Agent',
      role: 'ทดสอบ strategy กับ synthetic regimes เช่น sideways, high volatility, crash',
      evidence: [latestExperimentMeta],
      latest: latestExperimentMeta,
      canSelectStrategy: true,
    }),
    agentState({
      id: 'mads-review-agent',
      name: 'MADS AI Review Agent',
      role: 'ให้ LLM/MADS review ผล research, gate, shadow และเสนอ safe actions',
      evidence: [madsReviews, latestReview],
    }),
    agentState({
      id: 'promotion-gate-agent',
      name: 'Promotion Gate Agent',
      role: 'ตัดสินใจ promote strategy เข้า shadow/testnet จาก policy และ evidence',
      evidence: [registry, shadowDeployments],
      canSelectStrategy: true,
    }),
    agentState({
      id: 'shadow-signal-agent',
      name: 'Shadow Signal Agent',
      role: 'ประเมิน signal-only shadow deployment โดยไม่เปิด order',
      evidence: [shadowDeployments, shadowSignals],
      canSelectStrategy: true,
    }),
    agentState({
      id: 'dispatch-safety-agent',
      name: 'Dispatch Safety Gate',
      role: 'ตรวจ approval/handoff แล้วส่งเฉพาะ demo/testnet staged controls แบบ fail-closed',
      evidence: [handoff, dispatchResults],
    }),
  ];

  const selection = {
    enabled: true,
    mode: 'evidence_gated_manual_or_api_triggered',
    latest_experiment: latestExperiment ? {
      id: latestExperiment.id,
      created_at: latestExperiment.created_at,
      strategy: latestExperiment.proposal?.name,
      symbol: latestExperiment.symbol,
      verdict: latestExperiment.evaluation?.verdict,
      score: latestExperiment.evaluation?.score,
      selected_for_shadow_review: latestExperiment.evaluation?.verdict === 'PASS_FOR_SHADOW_REVIEW',
    } : null,
    order_execution: 'disabled_in_research_os',
    note: 'Agents can test and select candidates for review/shadow gates, but do not place live orders from this dashboard.',
  };

  return {
    status: 'ready',
    generated_at: new Date().toISOString(),
    agents,
    selection,
  };
}

async function runExperiment(body = {}) {
  const proposal = resolveProposal(body.proposal || 'strategies/btc_eth_mean_reversion_v1.json');
  const symbol = String(body.symbol || proposal.symbols[0] || 'BTCUSDT').toUpperCase();
  const count = Math.max(160, Math.min(Number(body.count) || 520, 1000));
  const id = `exp-${new Date().toISOString().replace(/[-:.TZ]/g, '').slice(0, 14)}-${crypto.randomBytes(3).toString('hex')}`;
  const runDir = path.join(experimentDir, id);
  fs.mkdirSync(runDir, { recursive: true });

  const baselineCandles = path.join(runDir, 'baseline_candles.json');
  fs.writeFileSync(baselineCandles, JSON.stringify(syntheticCandles({ regime: 'baseline', count }), null, 2));
  const baselineOut = path.join(runDir, 'baseline_report.json');
  const baselineStep = await runCommand('python3', ['-m', 'strategy_lab.run_backtest', '--proposal', proposal.path, '--symbol', symbol, '--candles', baselineCandles, '--out', baselineOut]);

  const optimizeOut = path.join(runDir, 'optimization_report.json');
  const optimizeStep = await runCommand('python3', ['-m', 'strategy_lab.run_optimize', '--proposal', proposal.path, '--symbol', symbol, '--candles', baselineCandles, '--top', '5', '--out', optimizeOut]);

  const stress = {};
  for (const regime of ['sideways', 'high_volatility', 'crash']) {
    const candlesPath = path.join(runDir, `${regime}_candles.json`);
    const outPath = path.join(runDir, `${regime}_report.json`);
    fs.writeFileSync(candlesPath, JSON.stringify(syntheticCandles({ regime, count, start: regime === 'crash' ? 68000 : 65000 }), null, 2));
    const step = await runCommand('python3', ['-m', 'strategy_lab.run_backtest', '--proposal', proposal.path, '--symbol', symbol, '--candles', candlesPath, '--out', outPath]);
    stress[regime] = { step, report: readJsonSafe(outPath, {}) };
  }

  const experiment = {
    id,
    created_at: new Date().toISOString(),
    status: 'completed',
    proposal: { id: proposal.id, name: proposal.name, type: proposal.type, timeframe: proposal.timeframe },
    symbol,
    dataset: { source: 'synthetic', count, regimes: ['baseline', 'sideways', 'high_volatility', 'crash'] },
    results: {
      baseline: { step: baselineStep, report: readJsonSafe(baselineOut, {}) },
      optimization: { step: optimizeStep, report: readJsonSafe(optimizeOut, {}), passed: optimizeStep.code === 0 },
      stress,
    },
  };
  experiment.evaluation = evaluateExperiment(experiment);
  appendExperiment(experiment);
  return experiment;
}

async function handleExperimentApi(req, res) {
  const url = new URL(req.url, `http://${req.headers.host}`);
  try {
    if (req.method === 'GET' && url.pathname === '/api/experiments') {
      sendJson(res, 200, { status: 'ready', items: listExperiments().slice(0, 50) });
      return true;
    }
    if (req.method === 'GET' && url.pathname === '/api/experiments/proposals') {
      sendJson(res, 200, { status: 'ready', items: listStrategyProposals() });
      return true;
    }
    if (req.method === 'POST' && url.pathname === '/api/experiments/run') {
      const experiment = await runExperiment(await readJsonBody(req));
      sendJson(res, 200, { ok: true, experiment });
      return true;
    }
    if (req.method === 'GET' && url.pathname === '/api/experiments/agents/status') {
      sendJson(res, 200, listAgentStatus());
      return true;
    }
  } catch (error) {
    sendJson(res, 500, { error: error.message });
    return true;
  }
  return false;
}

const server = http.createServer(async (req, res) => {
  if (req.url.startsWith('/api/experiments')) {
    if (await handleExperimentApi(req, res)) return;
  }
  if (req.url.startsWith('/api/')) {
    await proxyApi(req, res);
    return;
  }

  const filePath = safePublicPath(new URL(req.url, `http://${req.headers.host}`).pathname);
  if (!filePath) {
    send(res, 403, 'Forbidden', { 'content-type': 'text/plain; charset=utf-8' });
    return;
  }

  fs.readFile(filePath, (error, data) => {
    if (error) {
      fs.readFile(path.join(publicDir, 'index.html'), (fallbackError, fallback) => {
        if (fallbackError) {
          send(res, 404, 'Not found', { 'content-type': 'text/plain; charset=utf-8' });
          return;
        }
        send(res, 200, fallback, { 'content-type': contentTypes['.html'] });
      });
      return;
    }
    send(res, 200, data, { 'content-type': contentTypes[path.extname(filePath)] || 'application/octet-stream' });
  });
});

server.listen(port, '0.0.0.0', () => {
  console.log(`Research OS Dashboard running on http://0.0.0.0:${port}`);
  console.log(`Proxying TradeOps API from ${tradeopsApiBase}`);
});
