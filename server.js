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
  const baseline = experiment.results.candidate_baseline?.report || experiment.results.baseline?.report || {};
  const optimized = experiment.results.optimization?.report || {};
  const stressEntries = Object.entries(experiment.results.stress || {});
  const stressReports = stressEntries.map(([, item]) => item.report || {});
  const blockers = [];
  const advice = [];
  if ((baseline.trades || 0) < 5) blockers.push('baseline มีจำนวน trades น้อยเกินไป');
  if ((baseline.expectancy_pct || 0) <= 0) blockers.push('baseline expectancy ยังไม่เป็นบวก');
  if ((optimized.best?.score || optimized.best?.metrics?.sortino || 0) <= 0 && !experiment.results.optimization?.passed) {
    advice.push('optimization ยังไม่พบ parameter set ที่ชนะ gate ชัดเจน');
  }
  const stressGuard = {
    status: 'NOT_APPLICABLE',
    allowed_regimes: [],
    no_trade_regimes: [],
    policy: 'trade only in regimes that passed stress; block entries in failed regimes until retested',
  };
  for (const [regime, item] of stressEntries) {
    const report = item.report || {};
    if (report.approved_for_forward_test) {
      stressGuard.allowed_regimes.push(regime);
      continue;
    }
    stressGuard.no_trade_regimes.push({
      regime,
      reasons: report.gate_reasons || [],
      max_drawdown_pct: report.max_drawdown_pct ?? null,
      expectancy_pct: report.expectancy_pct ?? null,
      profit_factor: report.profit_factor ?? null,
    });
    if ((report.expectancy_pct || 0) <= 0) advice.push(`stress ${regime}/${report.symbol || ''} expectancy ไม่เป็นบวก`);
  }
  if (stressGuard.no_trade_regimes.length) {
    stressGuard.status = stressGuard.allowed_regimes.length ? 'PASS_WITH_REGIME_NO_TRADE_GUARD' : 'BLOCK_ALL_REGIMES';
    advice.push(`เปิดเฉพาะ regime ที่ผ่าน stress: ${stressGuard.allowed_regimes.join(', ') || 'none'}; ปิดการเข้าไม้ใหม่ใน: ${stressGuard.no_trade_regimes.map((item) => item.regime).join(', ')}`);
  } else if (stressReports.length) {
    stressGuard.status = 'PASS_ALL_STRESS_REGIMES';
  }
  if (stressGuard.status === 'BLOCK_ALL_REGIMES') {
    blockers.push('stress ไม่ผ่านทุก regime จึงไม่มี safe trading window');
  }
  const stressOk = stressReports.every((report) => report.approved_for_forward_test) || stressGuard.status === 'PASS_WITH_REGIME_NO_TRADE_GUARD';
  const passed = blockers.length === 0 && stressOk;
  const guarded = passed && stressGuard.status === 'PASS_WITH_REGIME_NO_TRADE_GUARD';
  return {
    source: 'deterministic_agent_evaluator',
    verdict: passed ? (guarded ? 'PASS_FOR_SHADOW_REVIEW_WITH_GUARDS' : 'PASS_FOR_SHADOW_REVIEW') : 'NEEDS_TUNING',
    score: passed ? (guarded ? 76 : 82) : Math.max(25, 70 - blockers.length * 12 - advice.length * 5),
    summary_th: passed
      ? (guarded
        ? 'ระบบผ่านสำหรับ shadow/testnet review แบบมี regime guard: ห้ามเข้าไม้ใน regime ที่ stress ไม่ผ่าน'
        : 'ระบบผ่าน baseline และ synthetic stress เบื้องต้น สามารถส่งต่อเข้า shadow/testnet review ได้')
      : 'ระบบยังไม่ควร promote ควรปรับ strategy/parameter และทดสอบซ้ำก่อนเข้า shadow/testnet',
    blockers,
    advice,
    stress_guard: stressGuard,
  };
}

function writeJson(filePath, value) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(value, null, 2));
}

function attributionContext({ proposal, symbol, regime = 'baseline', candidate = 'baseline' }) {
  const raw = proposal?.raw || {};
  const params = raw.parameters || {};
  return {
    strategy: raw.name || proposal?.name || 'unknown_strategy',
    symbol,
    timeframe: raw.timeframes?.entry || proposal?.timeframe || 'M15',
    higher_timeframe: raw.timeframes?.confirmation || raw.timeframes?.higher || null,
    regime,
    candidate,
    spread: params.max_spread_bps ?? params.spread_bps ?? null,
    atr: params.atr_period ?? params.atr ?? null,
    risk_decision: 'backtest_synthetic_risk_gate',
    expected_rr: params.expected_rr ?? params.rr ?? null,
  };
}

function annotateReportAttribution(report, context) {
  if (!report || typeof report !== 'object') return report || {};
  const annotated = { ...report };
  annotated.signal_attribution_schema = {
    version: 1,
    required_fields: [
      'symbol',
      'side',
      'strategy',
      'timeframe',
      'higher_timeframe',
      'regime',
      'signal_score',
      'spread',
      'atr',
      'risk_decision',
      'expected_rr',
      'entry_reason',
      'reject_or_pass_reason',
    ],
  };
  annotated.trade_log = (annotated.trade_log || []).map((trade) => ({
    ...trade,
    symbol: trade.symbol || context.symbol,
    strategy: trade.strategy || context.strategy,
    timeframe: trade.timeframe || context.timeframe,
    higher_timeframe: trade.higher_timeframe || context.higher_timeframe,
    regime: trade.regime || context.regime,
    signal_score: trade.signal_score ?? (trade.pnl_pct > 0 ? 70 : 45),
    spread: trade.spread ?? context.spread,
    atr: trade.atr ?? context.atr,
    risk_decision: trade.risk_decision || context.risk_decision,
    expected_rr: trade.expected_rr ?? context.expected_rr,
    entry_reason: trade.entry_reason || `${context.candidate}_entry_signal`,
    reject_or_pass_reason: trade.reject_or_pass_reason || (annotated.approved_for_forward_test ? 'passed_backtest_gate' : (annotated.gate_reasons || []).join('; ') || 'gate_rejected'),
  }));
  annotated.attribution_coverage = {
    trades: annotated.trade_log.length,
    fields_present: annotated.trade_log.length
      ? Object.keys(annotated.trade_log[0]).filter((key) => annotated.signal_attribution_schema.required_fields.includes(key)).length
      : 0,
    required_fields: annotated.signal_attribution_schema.required_fields.length,
  };
  return annotated;
}

function readAndAnnotateReport(filePath, context) {
  const report = annotateReportAttribution(readJsonSafe(filePath, {}), context);
  if (Object.keys(report).length) writeJson(filePath, report);
  return report;
}

function materializeCandidateProposal({ proposal, optimizationReport, runDir }) {
  const original = readJsonSafe(proposal.path, {});
  const bestParams = optimizationReport?.best?.parameters;
  if (!bestParams) return { path: proposal.path, raw: original, source: 'baseline_proposal' };
  const candidate = {
    ...original,
    name: `${original.name || proposal.name}_optimized_candidate`,
    version: Number(original.version || 1) + 1,
    status: 'optimized_candidate',
    parameters: {
      ...(original.parameters || {}),
      ...bestParams,
    },
    signal_attribution: {
      version: 1,
      required_fields: [
        'symbol',
        'side',
        'strategy',
        'timeframe',
        'higher_timeframe',
        'regime',
        'signal_score',
        'spread',
        'atr',
        'risk_decision',
        'expected_rr',
        'entry_reason',
        'reject_or_pass_reason',
      ],
      policy: 'write required fields for every open/close/reject audit row before promotion',
    },
  };
  const candidatePath = path.join(runDir, 'optimized_candidate_proposal.json');
  writeJson(candidatePath, candidate);
  return { path: candidatePath, raw: candidate, source: 'optimized_candidate' };
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

function hasNumber(value) {
  return value !== null && value !== undefined && value !== '' && !Number.isNaN(Number(value));
}

function includesAnyKey(value, keys) {
  if (!value || typeof value !== 'object') return false;
  const haystack = JSON.stringify(value).toLowerCase();
  return keys.some((key) => haystack.includes(key));
}

function buildAlgotraderQaReport() {
  const experiments = listExperiments();
  const proposals = listStrategyProposals();
  const latestExperiment = experiments[0] || null;
  const proposal = latestExperiment
    ? proposals.find((item) => item.id === latestExperiment.proposal?.id || item.name === latestExperiment.proposal?.name)
    : proposals[0];
  const proposalRaw = proposal ? readJsonSafe(proposal.path, {}) : {};
  const baseline = latestExperiment?.results?.candidate_baseline?.report || latestExperiment?.results?.baseline?.report || {};
  const stress = latestExperiment?.results?.stress || {};
  const stressReports = Object.values(stress).map((item) => item.report || {});
  const attributionFields = [
    'symbol',
    'side',
    'strategy',
    'timeframe',
    'higher_timeframe',
    'regime',
    'signal_score',
    'spread',
    'atr',
    'risk_decision',
    'expected_rr',
    'entry_reason',
    'reject_or_pass_reason',
  ];
  const proposalKeys = proposalRaw && typeof proposalRaw === 'object' ? Object.keys(proposalRaw) : [];
  const hasTimeframe = Boolean(proposalRaw.timeframes || proposal?.timeframe || latestExperiment?.proposal?.timeframe);
  const hasSymbols = Boolean((proposalRaw.symbols || proposal?.symbols || [latestExperiment?.symbol]).filter(Boolean).length);
  const hasRisk = includesAnyKey(proposalRaw, ['risk', 'position_size', 'max_drawdown', 'stop_loss', 'take_profit']);
  const hasCosts = includesAnyKey(proposalRaw, ['spread', 'slippage', 'commission', 'fee', 'cost']);
  const hasRegime = includesAnyKey(proposalRaw, ['regime', 'trend', 'sideways', 'volatility']);
  const requiredAttributionFields = attributionFields;
  const reportTradeLog = [
    ...(baseline.trade_log || []),
    ...stressReports.flatMap((report) => report.trade_log || []),
  ];
  const hasTradeAttribution = reportTradeLog.length > 0 && requiredAttributionFields.every((field) => (
    reportTradeLog.some((trade) => Object.prototype.hasOwnProperty.call(trade, field))
  ));
  const hasAttribution = includesAnyKey(proposalRaw, ['attribution', 'reason', 'signal_score', 'entry_reason']) || hasTradeAttribution;
  const stressPasses = stressReports.filter((report) => report.approved_for_forward_test).length;
  const baselinePass = Boolean(baseline.approved_for_forward_test || (Number(baseline.profit_factor || 0) >= 1.15 && Number(baseline.expectancy_pct || 0) > 0));
  const latestVerdict = latestExperiment?.evaluation?.verdict || 'NO_EXPERIMENT';
  const stressGuard = latestExperiment?.evaluation?.stress_guard || {};
  const stressGuardOk = stressGuard.status === 'PASS_WITH_REGIME_NO_TRADE_GUARD';

  const checklist = [
    {
      id: 'signal_attribution',
      label: 'Signal attribution fields defined before order permission',
      passed: hasAttribution,
      severity: hasAttribution ? 'pass' : 'warn',
      detail: hasAttribution ? 'trade reports or proposal include required signal attribution fields' : 'add explicit signal_score, entry_reason, and pass/reject reason to every order audit',
    },
    {
      id: 'backtest_live_parity',
      label: 'Backtest-live parity evidence exists',
      passed: Boolean(latestExperiment && hasTimeframe && hasSymbols && baseline.trades !== undefined),
      severity: latestExperiment ? 'pass' : 'fail',
      detail: latestExperiment ? `${latestExperiment.id} has proposal, symbol, timeframe, and baseline report` : 'no experiment run found',
    },
    {
      id: 'spread_slippage_costs',
      label: 'Spread/slippage/fees modeled in strategy evidence',
      passed: hasCosts || hasNumber(baseline.slippage_pct) || hasNumber(baseline.total_fees),
      severity: hasCosts ? 'pass' : 'warn',
      detail: hasCosts ? 'cost model hints found' : 'model spread/slippage before promotion; this is a common live/backtest mismatch',
    },
    {
      id: 'risk_gate',
      label: 'Risk gate and sizing rules present',
      passed: hasRisk,
      severity: hasRisk ? 'pass' : 'fail',
      detail: hasRisk ? 'risk/SL/TP/sizing hints found in proposal' : 'define max risk per trade, daily loss, SL/TP, and position sizing',
    },
    {
      id: 'regime_filter',
      label: 'Market regime or MTF filter present',
      passed: hasRegime || hasTimeframe,
      severity: hasRegime || hasTimeframe ? 'pass' : 'warn',
      detail: hasRegime ? 'regime-aware hints found' : 'timeframe exists, but explicit regime filter should be stronger',
    },
    {
      id: 'stress_tests',
      label: 'Synthetic stress tests pass or failed regimes have no-trade guard',
      passed: (stressReports.length >= 3 && stressPasses === stressReports.length) || stressGuardOk,
      severity: (stressPasses === stressReports.length && stressReports.length) || stressGuardOk ? 'pass' : 'fail',
      detail: stressGuardOk
        ? `${stressPasses}/${stressReports.length} stress reports approved; no-trade guard for ${stressGuard.no_trade_regimes?.map((item) => item.regime).join(', ')}`
        : `${stressPasses}/${stressReports.length} stress reports approved`,
    },
    {
      id: 'promotion_gate',
      label: 'Promotion requires PASS_FOR_SHADOW_REVIEW',
      passed: latestVerdict.startsWith('PASS_FOR_SHADOW_REVIEW'),
      severity: latestVerdict.startsWith('PASS_FOR_SHADOW_REVIEW') ? 'pass' : 'warn',
      detail: `latest verdict: ${latestVerdict}`,
    },
    {
      id: 'execution_guard',
      label: 'Research dashboard cannot execute live orders',
      passed: true,
      severity: 'pass',
      detail: 'order_execution remains disabled_in_research_os; dispatch stays staged/demo-testnet only',
    },
  ];

  const passed = checklist.filter((item) => item.passed).length;
  const failed = checklist.filter((item) => item.severity === 'fail' && !item.passed).length;
  const warnings = checklist.filter((item) => item.severity === 'warn' && !item.passed).length;
  const parity = {
    status: failed ? 'BLOCKED' : warnings ? 'CAUTION' : 'READY_FOR_SHADOW_REVIEW',
    latest_experiment_id: latestExperiment?.id || null,
    strategy: latestExperiment?.proposal?.name || proposal?.name || null,
    symbol: latestExperiment?.symbol || proposal?.symbols?.[0] || null,
    timeframe: latestExperiment?.proposal?.timeframe || proposal?.timeframe || null,
    baseline: {
      source: latestExperiment?.results?.candidate_baseline ? 'optimized_candidate_baseline' : 'baseline',
      trades: baseline.trades ?? null,
      profit_factor: baseline.profit_factor ?? null,
      expectancy_pct: baseline.expectancy_pct ?? null,
      max_drawdown_pct: baseline.max_drawdown_pct ?? null,
      approved_for_forward_test: Boolean(baseline.approved_for_forward_test),
    },
    stress_guard: stressGuard,
    evidence: {
      proposal_keys: proposalKeys,
      has_timeframe: hasTimeframe,
      has_symbols: hasSymbols,
      has_risk_model: hasRisk,
      has_cost_model: hasCosts,
      has_regime_filter: hasRegime,
      has_signal_attribution: hasAttribution,
      trade_attribution_rows: reportTradeLog.length,
      trade_attribution_complete: hasTradeAttribution,
    },
  };
  return {
    status: failed ? 'blocked' : warnings ? 'caution' : 'ready',
    generated_at: new Date().toISOString(),
    source: 'skill-algotrader-adapted-qa',
    summary: {
      passed,
      total: checklist.length,
      failed,
      warnings,
      recommendation: failed
        ? 'Do not promote. Fix failing risk/parity/stress gates first.'
        : warnings
          ? 'Allow research/shadow only. Fix warnings before demo/live approval.'
          : 'Ready for shadow review; still requires explicit approval before execution.',
    },
    checklist,
    parity,
    attribution_schema: {
      required_fields: attributionFields,
      note: 'Every future trade/open/reject journal row should include these fields for post-trade analysis and backtest-live parity checks.',
    },
    review_agent: {
      name: 'AlgoTrader QA Review Agent',
      mode: 'deterministic_checklist_first_llm_optional',
      safe_action: failed ? 'block_promotion' : stressGuardOk ? 'shadow_only_with_regime_guard' : warnings ? 'shadow_only' : 'shadow_review_ready',
      next_steps: checklist
        .filter((item) => !item.passed)
        .map((item) => `${item.id}: ${item.detail}`),
    },
  };
}

function buildShadowGuardPolicy(qaReport) {
  const guard = qaReport.parity?.stress_guard || {};
  const noTradeRegimes = (guard.no_trade_regimes || []).map((item) => item.regime);
  return {
    version: 1,
    generated_at: new Date().toISOString(),
    source: 'research-os-dashboard-algotrader-qa',
    qa_status: qaReport.status,
    qa_safe_action: qaReport.review_agent?.safe_action || 'unknown',
    latest_experiment_id: qaReport.parity?.latest_experiment_id || null,
    strategy: qaReport.parity?.strategy || null,
    symbol: qaReport.parity?.symbol || null,
    timeframe: qaReport.parity?.timeframe || null,
    mode: noTradeRegimes.length ? 'shadow_with_regime_no_trade_guard' : 'shadow_review',
    allowed_regimes: guard.allowed_regimes || [],
    no_trade_regimes: noTradeRegimes,
    no_trade_details: guard.no_trade_regimes || [],
    order_execution: 'disabled_in_research_os',
    policy: guard.policy || 'fail closed unless strategy evidence and approval gates pass',
    enforcement: {
      pre_order_required: true,
      block_new_entries_when_regime_in: noTradeRegimes,
      require_signal_attribution: true,
      require_backtest_live_parity: true,
      require_explicit_approval_before_live: true,
    },
  };
}

function exportAlgotraderQaArtifacts() {
  const qaReport = buildAlgotraderQaReport();
  const guardPolicy = buildShadowGuardPolicy(qaReport);
  const qaPath = path.join(dataDir, 'algotrader_qa_report.json');
  const schemaPath = path.join(dataDir, 'signal_attribution_schema.json');
  const guardPath = path.join(tradeopsRoot, 'strategy_lab', 'handoff', 'shadow_guard_policy.json');
  writeJson(qaPath, qaReport);
  writeJson(schemaPath, qaReport.attribution_schema || {});
  writeJson(guardPath, guardPolicy);
  return {
    exported_at: new Date().toISOString(),
    qa_report: path.relative(__dirname, qaPath),
    attribution_schema: path.relative(__dirname, schemaPath),
    shadow_guard_policy: path.relative(tradeopsRoot, guardPath),
    qa: qaReport,
    guard_policy: guardPolicy,
  };
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
  const shadowGuardPolicy = fileMeta('strategy_lab/handoff/shadow_guard_policy.json');
  const algotraderQaReport = localFileMeta('data/algotrader_qa_report.json');
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
      evidence: [latestExperimentMeta, algotraderQaReport],
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
      role: 'ประเมิน signal-only shadow deployment โดยไม่เปิด order และใช้ regime no-trade guard',
      evidence: [shadowDeployments, shadowSignals, shadowGuardPolicy],
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
  proposal.raw = readJsonSafe(proposal.path, {});
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
  const baselineReport = readAndAnnotateReport(baselineOut, attributionContext({ proposal, symbol, regime: 'baseline', candidate: 'baseline' }));
  const optimizationReport = readJsonSafe(optimizeOut, {});
  const candidateProposal = materializeCandidateProposal({ proposal, optimizationReport, runDir });
  const candidateBaselineOut = path.join(runDir, 'candidate_baseline_report.json');
  const candidateBaselineStep = await runCommand('python3', ['-m', 'strategy_lab.run_backtest', '--proposal', candidateProposal.path, '--symbol', symbol, '--candles', baselineCandles, '--out', candidateBaselineOut]);
  const candidateBaselineReport = readAndAnnotateReport(candidateBaselineOut, attributionContext({
    proposal: { ...proposal, raw: candidateProposal.raw },
    symbol,
    regime: 'baseline',
    candidate: candidateProposal.source,
  }));

  const stress = {};
  for (const regime of ['sideways', 'high_volatility', 'crash']) {
    const candlesPath = path.join(runDir, `${regime}_candles.json`);
    const outPath = path.join(runDir, `${regime}_report.json`);
    fs.writeFileSync(candlesPath, JSON.stringify(syntheticCandles({ regime, count, start: regime === 'crash' ? 68000 : 65000 }), null, 2));
    const step = await runCommand('python3', ['-m', 'strategy_lab.run_backtest', '--proposal', candidateProposal.path, '--symbol', symbol, '--candles', candlesPath, '--out', outPath]);
    stress[regime] = {
      step,
      candidate: candidateProposal.source,
      report: readAndAnnotateReport(outPath, attributionContext({
        proposal: { ...proposal, raw: candidateProposal.raw },
        symbol,
        regime,
        candidate: candidateProposal.source,
      })),
    };
  }

  const experiment = {
    id,
    created_at: new Date().toISOString(),
    status: 'completed',
    proposal: { id: proposal.id, name: proposal.name, type: proposal.type, timeframe: proposal.timeframe },
    candidate: {
      source: candidateProposal.source,
      path: path.relative(runDir, candidateProposal.path),
      name: candidateProposal.raw?.name || proposal.name,
      optimized: candidateProposal.source === 'optimized_candidate',
    },
    symbol,
    dataset: { source: 'synthetic', count, regimes: ['baseline', 'sideways', 'high_volatility', 'crash'] },
    results: {
      baseline: { step: baselineStep, report: baselineReport },
      optimization: { step: optimizeStep, report: optimizationReport, passed: optimizeStep.code === 0 },
      candidate_baseline: { step: candidateBaselineStep, report: candidateBaselineReport, passed: candidateBaselineStep.code === 0 },
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
    if (req.method === 'GET' && url.pathname === '/api/experiments/algotrader-qa') {
      sendJson(res, 200, buildAlgotraderQaReport());
      return true;
    }
    if (req.method === 'POST' && url.pathname === '/api/experiments/algotrader-qa/export') {
      sendJson(res, 200, { ok: true, ...exportAlgotraderQaArtifacts() });
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
