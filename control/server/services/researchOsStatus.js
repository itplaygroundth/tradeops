import fs from 'fs';
import path from 'path';
import { spawn } from 'child_process';

function readJson(filePath, fallback = null) {
  try {
    if (!fs.existsSync(filePath)) return fallback;
    return JSON.parse(fs.readFileSync(filePath, 'utf8'));
  } catch (error) {
    return { error: error.message };
  }
}

function writeJsonAtomic(filePath, value) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  const tmp = `${filePath}.tmp`;
  fs.writeFileSync(tmp, JSON.stringify(value, null, 2));
  fs.renameSync(tmp, filePath);
}

function readJsonl(filePath, limit = 20) {
  try {
    if (!fs.existsSync(filePath)) return [];
    return fs.readFileSync(filePath, 'utf8')
      .split(/\r?\n/)
      .filter(Boolean)
      .slice(0, limit)
      .map((line) => JSON.parse(line));
  } catch {
    return [];
  }
}

function appendJsonl(filePath, value) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.appendFileSync(filePath, `${JSON.stringify(value)}\n`);
}

function listJsonFiles(dirPath, limit = 50) {
  try {
    if (!fs.existsSync(dirPath)) return [];
    return fs.readdirSync(dirPath)
      .filter((name) => name.endsWith('.json'))
      .sort()
      .slice(0, limit)
      .map((name) => path.join(dirPath, name));
  } catch {
    return [];
  }
}

function readJsonFiles(paths, rootDir, limit = 20) {
  return paths.slice(0, limit).map((file) => {
    const data = readJson(file, {});
    return {
      file: path.relative(rootDir, file),
      strategy_name: data.strategy_name,
      symbol: data.symbol,
      windows: data.windows || 0,
      passed_windows: data.passed_windows || 0,
      pass_rate: data.pass_rate || 0,
      approved_for_forward_test: Boolean(data.approved_for_forward_test),
      gate_reasons: data.gate_reasons || [],
    };
  });
}

function summarizeRegistry(registry) {
  const rows = Array.isArray(registry?.strategies) ? registry.strategies : [];
  const byStatus = {};
  const byType = {};
  for (const row of rows) {
    const status = row.status || 'unknown';
    const type = row.type || 'unknown';
    byStatus[status] = (byStatus[status] || 0) + 1;
    byType[type] = (byType[type] || 0) + 1;
  }
  return {
    total: rows.length,
    byStatus,
    byType,
    latest: rows.slice(-10),
  };
}

function registryPath(rootDir) {
  return path.join(rootDir, 'strategy_lab', 'registry', 'approved_strategies.json');
}

function shadowDeploymentsPath(rootDir) {
  return path.join(rootDir, 'strategy_lab', 'shadow', 'deployments.json');
}

function shadowEventsPath(rootDir) {
  return path.join(rootDir, 'strategy_lab', 'shadow', 'events.jsonl');
}

function shadowSignalsPath(rootDir) {
  return path.join(rootDir, 'strategy_lab', 'shadow', 'signals.jsonl');
}

function researchReviewsPath(rootDir) {
  return path.join(rootDir, 'strategy_lab', 'reviews', 'research_os_reviews.jsonl');
}

function handoffManifestPath(rootDir) {
  return path.join(rootDir, 'strategy_lab', 'handoff', 'execution_handoff.json');
}

function enableRequestsPath(rootDir) {
  return path.join(rootDir, 'strategy_lab', 'handoff', 'enable_requests.jsonl');
}

function approvalDecisionsPath(rootDir) {
  return path.join(rootDir, 'strategy_lab', 'handoff', 'approval_decisions.jsonl');
}

function promotionPolicyPath(rootDir) {
  return path.join(rootDir, 'strategy_lab', 'config', 'promotion_policy.json');
}

function dispatchPlanPath(rootDir) {
  return path.join(rootDir, 'strategy_lab', 'handoff', 'dispatch_plan.json');
}

function stagedDispatchResultsPath(rootDir) {
  return path.join(rootDir, 'strategy_lab', 'handoff', 'staged_dispatch_results.jsonl');
}

function loadRegistry(rootDir) {
  return readJson(registryPath(rootDir), { version: 1, strategies: [] });
}

function saveRegistry(rootDir, registry) {
  writeJsonAtomic(registryPath(rootDir), registry);
}

function loadShadowDeployments(rootDir) {
  return readJson(shadowDeploymentsPath(rootDir), { version: 1, deployments: [] });
}

function saveShadowDeployments(rootDir, data) {
  writeJsonAtomic(shadowDeploymentsPath(rootDir), data);
}

function deploymentId(strategy) {
  return `${strategy.market}:${strategy.name}:v${strategy.version || 1}`;
}

function summarizeShadow(rootDir) {
  const data = loadShadowDeployments(rootDir);
  const deployments = Array.isArray(data.deployments) ? data.deployments : [];
  const byStatus = {};
  const byMode = {};
  for (const item of deployments) {
    byStatus[item.status || 'unknown'] = (byStatus[item.status || 'unknown'] || 0) + 1;
    byMode[item.mode || 'unknown'] = (byMode[item.mode || 'unknown'] || 0) + 1;
  }
  return {
    deployments: deployments.length,
    active: deployments.filter((item) => item.status === 'active').length,
    byStatus,
    byMode,
    latest: deployments.slice(-10),
  };
}

function latestResearchReview(rootDir) {
  const rows = readJsonl(researchReviewsPath(rootDir), 50);
  return rows.length ? rows[rows.length - 1] : null;
}

function latestHandoffManifest(rootDir) {
  return readJson(handoffManifestPath(rootDir), null);
}

function latestEnableRequest(rootDir) {
  const rows = readJsonl(enableRequestsPath(rootDir), 50);
  return rows.length ? rows[rows.length - 1] : null;
}

function latestApprovalDecision(rootDir) {
  const rows = readJsonl(approvalDecisionsPath(rootDir), 50);
  return rows.length ? rows[rows.length - 1] : null;
}

function latestDispatchPlan(rootDir) {
  return readJson(dispatchPlanPath(rootDir), null);
}

function latestStagedDispatchResult(rootDir) {
  const rows = readJsonl(stagedDispatchResultsPath(rootDir), 50);
  return rows.length ? rows[rows.length - 1] : null;
}

function summarizeShadowSignals(rootDir) {
  const rows = readJsonl(shadowSignalsPath(rootDir), 1000);
  const actionable = rows.filter((row) => ['LONG', 'SHORT'].includes(row.action));
  const pnls = rows
    .map((row) => row.theoretical_pnl_pct ?? row.paper_pnl_pct ?? row.testnet_pnl_pct ?? row.pnl_pct ?? row.outcome?.pnl_pct)
    .filter((value) => Number.isFinite(Number(value)))
    .map(Number);
  const wins = pnls.filter((value) => value > 0);
  const losses = pnls.filter((value) => value <= 0);
  const profitFactor = losses.length && Math.abs(losses.reduce((sum, value) => sum + value, 0)) > 0
    ? wins.reduce((sum, value) => sum + value, 0) / Math.abs(losses.reduce((sum, value) => sum + value, 0))
    : wins.length ? 999 : 0;
  return {
    signals: rows.length,
    actionable: actionable.length,
    outcomes: pnls.length,
    wins: wins.length,
    losses: losses.length,
    win_rate: pnls.length ? wins.length / pnls.length : 0,
    expectancy_pct: pnls.length ? pnls.reduce((sum, value) => sum + value, 0) / pnls.length : 0,
    profit_factor: profitFactor,
    total_pnl_pct: pnls.reduce((sum, value) => sum + value, 0),
  };
}

export function loadPromotionPolicy(rootDir) {
  return readJson(promotionPolicyPath(rootDir), { version: 1 });
}

function walkForwardPromotionThresholds(rootDir, options = {}) {
  const policy = loadPromotionPolicy(rootDir);
  const gate = policy.walk_forward_promotion_gate || {};
  return {
    minPassRate: Number(options.minPassRate ?? gate.min_pass_rate ?? 0.6),
    minWindows: Number(options.minWindows ?? gate.min_windows ?? 2),
  };
}

function findBatchForProposal(batchSummary, proposalName) {
  const rows = Array.isArray(batchSummary?.best_overall) ? batchSummary.best_overall : [];
  return rows.filter((item) => item.proposal === proposalName);
}

function findWalkForwardForProposal(walkForwardFiles, rootDir, proposalName) {
  return readJsonFiles(walkForwardFiles, rootDir, 50)
    .filter((item) => item.strategy_name === proposalName);
}

function findShadowForProposal(shadowData, proposalName) {
  return (shadowData.deployments || []).filter((item) => item.strategy_name === proposalName);
}

export function buildStrategyLineage(rootDir) {
  const researchDir = path.join(rootDir, 'research_lab');
  const strategyDir = path.join(rootDir, 'strategy_lab');
  const paperStore = readJsonl(path.join(researchDir, 'data', 'paper_store.jsonl'), 200);
  const papersById = new Map(paperStore.map((paper) => [paper.paper_id, paper]));
  const hypotheses = listJsonFiles(path.join(researchDir, 'hypotheses'), 200)
    .map((file) => readJson(file, {}));
  const hypothesesById = new Map(hypotheses.map((item) => [item.hypothesis_id, item]));
  const proposals = listJsonFiles(path.join(strategyDir, 'strategies', 'generated'), 200)
    .map((file) => ({
      file: path.relative(rootDir, file),
      data: readJson(file, {}),
    }));
  const batchSummary = readJson(path.join(strategyDir, 'reports', 'batch_summary.json'), {});
  const registry = loadRegistry(rootDir);
  const registryByName = new Map((registry.strategies || []).map((item) => [item.name, item]));
  const shadow = loadShadowDeployments(rootDir);
  const walkForwardFiles = listJsonFiles(path.join(strategyDir, 'reports', 'walk_forward'), 200);

  return proposals.map(({ file, data }) => {
    const params = data.parameters || {};
    const paper = papersById.get(params.source_paper_id) || null;
    const hypothesis = hypothesesById.get(params.source_hypothesis_id) || null;
    const registryEntry = registryByName.get(data.name) || null;
    const batchRows = findBatchForProposal(batchSummary, data.name);
    const walkForwardRows = findWalkForwardForProposal(walkForwardFiles, rootDir, data.name);
    const shadowRows = findShadowForProposal(shadow, data.name);
    const batchPassed = batchRows.reduce((total, row) => total + Number(row.passed || 0), 0);
    const walkForwardApproved = walkForwardRows.filter((row) => row.approved_for_forward_test).length;
    const stage = registryEntry?.status
      || (walkForwardApproved > 0 ? 'forward_testing'
        : batchPassed > 0 ? 'optimized'
          : 'draft');
    const riskFlags = [];
    if (!paper) riskFlags.push('missing source paper');
    if (!hypothesis) riskFlags.push('missing source hypothesis');
    if (batchRows.length && batchPassed === 0) riskFlags.push('batch gate failed');
    if (walkForwardRows.length && walkForwardApproved === 0) riskFlags.push('walk-forward gate failed');
    if (stage === 'approved' && shadowRows.length === 0) riskFlags.push('approved but not shadow deployed');
    return {
      strategy: data.name,
      version: data.version || 1,
      market: data.market,
      type: data.type,
      symbols: data.symbols || [],
      stage,
      proposal_file: file,
      source_paper_id: params.source_paper_id || '',
      source_paper_title: paper?.title || '',
      source_hypothesis_id: params.source_hypothesis_id || '',
      hypothesis_family: hypothesis?.strategy_family || '',
      hypothesis_regime: hypothesis?.regime || '',
      research_confidence: Number(params.research_confidence || 0),
      batch: {
        runs: batchRows.length,
        passed: batchPassed,
        best_score: batchRows[0]?.best?.score ?? null,
        best_profit_factor: batchRows[0]?.best?.profit_factor ?? null,
      },
      walk_forward: {
        reports: walkForwardRows.length,
        approved: walkForwardApproved,
        best_pass_rate: walkForwardRows.reduce((best, row) => Math.max(best, Number(row.pass_rate || 0)), 0),
      },
      registry: registryEntry ? {
        status: registryEntry.status,
        updated_at: registryEntry.updated_at,
        approval: registryEntry.approval || null,
      } : null,
      shadow: {
        deployments: shadowRows.length,
        active: shadowRows.filter((item) => item.status === 'active').length,
        modes: [...new Set(shadowRows.map((item) => item.mode).filter(Boolean))],
      },
      risk_flags: riskFlags,
    };
  });
}

export function evaluateResearchLiveReadiness(rootDir) {
  const lineage = buildStrategyLineage(rootDir);
  const latestReview = latestResearchReview(rootDir);
  const items = lineage.map((item) => {
    const blockers = [];
    const warnings = [];
    if (item.stage !== 'approved') blockers.push('strategy is not approved');
    if ((item.walk_forward?.approved || 0) === 0) blockers.push('missing approved walk-forward report');
    if ((item.shadow?.active || 0) === 0) blockers.push('missing active shadow deployment');
    if ((item.risk_flags || []).length > 0) blockers.push(...item.risk_flags);
    if (!latestReview) warnings.push('missing Research OS review');
    if (latestReview?.source === 'heuristic') warnings.push('latest review used heuristic fallback');
    if (latestReview?.status && latestReview.status !== 'completed') blockers.push(`latest review status is ${latestReview.status}`);
    const readyForShadow = item.stage === 'approved' && blockers.every((reason) => reason !== 'missing active shadow deployment');
    const readyForLimitedLiveReview = blockers.length === 0;
    return {
      strategy: item.strategy,
      version: item.version,
      stage: item.stage,
      ready_for_shadow: readyForShadow,
      ready_for_limited_live_review: readyForLimitedLiveReview,
      blockers,
      warnings,
      evidence: {
        paper: item.source_paper_id,
        hypothesis: item.source_hypothesis_id,
        batch_passed: item.batch?.passed || 0,
        walk_forward_approved: item.walk_forward?.approved || 0,
        shadow_active: item.shadow?.active || 0,
        review_source: latestReview?.source || '',
      },
    };
  });
  const readyForShadow = items.filter((item) => item.ready_for_shadow).length;
  const readyForLimitedLiveReview = items.filter((item) => item.ready_for_limited_live_review).length;
  const status = readyForLimitedLiveReview > 0
    ? 'READY_FOR_LIMITED_LIVE_REVIEW'
    : readyForShadow > 0
      ? 'READY_FOR_SHADOW'
      : 'BLOCKED';
  return {
    status,
    total: items.length,
    readyForShadow,
    readyForLimitedLiveReview,
    blockers: [...new Set(items.flatMap((item) => item.blockers))],
    warnings: [...new Set(items.flatMap((item) => item.warnings))],
    latestReview: latestReview ? {
      source: latestReview.source,
      status: latestReview.status,
      created_at: latestReview.created_at,
    } : null,
    items,
  };
}

export function buildExecutionHandoffManifest(rootDir, {
  targetMode = 'limited_live_review',
  maxStrategies = 3,
} = {}) {
  const readiness = evaluateResearchLiveReadiness(rootDir);
  const eligible = readiness.items
    .filter((item) => item.ready_for_limited_live_review)
    .slice(0, Math.min(Math.max(Number(maxStrategies) || 3, 1), 10));
  const manifest = {
    id: `handoff-${Date.now()}`,
    created_at: new Date().toISOString(),
    status: eligible.length > 0 ? 'ready_for_manual_enable' : 'blocked',
    target_mode: targetMode === 'paper' ? 'paper' : 'limited_live_review',
    order_execution: 'requires_manual_enable',
    readiness_status: readiness.status,
    strategies: eligible.map((item) => ({
      strategy: item.strategy,
      version: item.version,
      stage: item.stage,
      evidence: item.evidence,
      controls: {
        order_execution: 'disabled',
        requires_manual_enable: true,
        max_risk_pct: 0.001,
        max_positions: 1,
        daily_loss_stop_usd: 5,
        require_shadow_observation: true,
      },
    })),
    blockers: readiness.blockers,
    warnings: readiness.warnings,
    audit: {
      readiness,
      generated_by: 'research_os',
      note: 'This manifest does not start engines or place orders. Execution remains disabled until a separate manual enable step is implemented.',
    },
  };
  if (eligible.length > 0) {
    writeJsonAtomic(handoffManifestPath(rootDir), manifest);
  }
  return {
    ok: true,
    built: eligible.length,
    manifest,
    status: collectResearchOsStatus(rootDir),
  };
}

export function createManualEnableRequest(rootDir, {
  requestedBy = 'dashboard',
  reason = 'manual limited live review request',
} = {}) {
  const manifest = latestHandoffManifest(rootDir);
  if (!manifest || manifest.status !== 'ready_for_manual_enable') {
    const request = {
      id: `enable-request-${Date.now()}`,
      created_at: new Date().toISOString(),
      status: 'BLOCKED',
      requested_by: requestedBy,
      reason,
      blockers: ['handoff manifest is not ready_for_manual_enable'],
      order_execution: 'disabled',
      next_required_action: 'build a ready handoff manifest first',
    };
    appendJsonl(enableRequestsPath(rootDir), request);
    return {
      ok: true,
      created: false,
      request,
      status: collectResearchOsStatus(rootDir),
    };
  }
  const request = {
    id: `enable-request-${Date.now()}`,
    created_at: new Date().toISOString(),
    status: 'PENDING_MANUAL_APPROVAL',
    requested_by: requestedBy,
    reason,
    manifest_id: manifest.id,
    target_mode: manifest.target_mode,
    strategies: (manifest.strategies || []).map((item) => ({
      strategy: item.strategy,
      version: item.version,
      max_risk_pct: item.controls?.max_risk_pct,
      max_positions: item.controls?.max_positions,
      daily_loss_stop_usd: item.controls?.daily_loss_stop_usd,
      order_execution: 'disabled',
    })),
    checklist: [
      'Confirm demo/test account only',
      'Confirm spread and liquidity are normal',
      'Confirm kill switch and daily loss stop are active',
      'Confirm shadow observation has no unresolved blockers',
      'Manually enable execution in the engine after this request is approved',
    ],
    order_execution: 'disabled',
    next_required_action: 'manual operator approval outside Research OS',
  };
  appendJsonl(enableRequestsPath(rootDir), request);
  return {
    ok: true,
    created: true,
    request,
    status: collectResearchOsStatus(rootDir),
  };
}

export function recordManualApprovalDecision(rootDir, {
  decision = 'approve',
  operator = 'dashboard',
  reason = 'operator decision',
} = {}) {
  const request = latestEnableRequest(rootDir);
  const normalizedDecision = decision === 'reject' ? 'reject' : 'approve';
  if (!request || request.status !== 'PENDING_MANUAL_APPROVAL') {
    const record = {
      id: `approval-decision-${Date.now()}`,
      created_at: new Date().toISOString(),
      decision: normalizedDecision,
      status: 'BLOCKED',
      operator,
      reason,
      blockers: ['no pending manual enable request'],
      engine_dispatch: 'disabled',
    };
    appendJsonl(approvalDecisionsPath(rootDir), record);
    return {
      ok: true,
      accepted: false,
      decision: record,
      dispatchPlan: latestDispatchPlan(rootDir),
      status: collectResearchOsStatus(rootDir),
    };
  }
  const record = {
    id: `approval-decision-${Date.now()}`,
    created_at: new Date().toISOString(),
    request_id: request.id,
    manifest_id: request.manifest_id || '',
    decision: normalizedDecision,
    status: normalizedDecision === 'approve' ? 'APPROVED_FOR_STAGED_DISPATCH' : 'REJECTED',
    operator,
    reason,
    engine_dispatch: 'disabled',
  };
  appendJsonl(approvalDecisionsPath(rootDir), record);
  let dispatchPlan = latestDispatchPlan(rootDir);
  if (normalizedDecision === 'approve') {
    dispatchPlan = {
      id: `dispatch-plan-${Date.now()}`,
      created_at: new Date().toISOString(),
      approval_decision_id: record.id,
      request_id: request.id,
      manifest_id: request.manifest_id || '',
      status: 'STAGED',
      engine_dispatch: 'disabled',
      order_execution: 'disabled',
      next_required_action: 'manual engine integration and explicit execution enablement',
      strategies: (request.strategies || []).map((item) => ({
        ...item,
        dispatch_status: 'staged',
        order_execution: 'disabled',
      })),
      safety: {
        requires_manual_engine_enable: true,
        requires_demo_or_testnet_account: true,
        requires_kill_switch: true,
        requires_daily_loss_stop: true,
      },
    };
    writeJsonAtomic(dispatchPlanPath(rootDir), dispatchPlan);
  }
  return {
    ok: true,
    accepted: normalizedDecision === 'approve',
    decision: record,
    dispatchPlan,
    status: collectResearchOsStatus(rootDir),
  };
}

function engineIdsForDispatchPlan(plan) {
  const ids = new Set();
  for (const item of plan?.strategies || []) {
    const market = String(item.evidence?.market || item.market || '').toLowerCase();
    const strategyName = String(item.strategy || '').toLowerCase();
    if (market === 'forex' || strategyName.includes('forex')) ids.add('mtai');
    if (market === 'crypto' || strategyName.includes('btc') || strategyName.includes('eth')) ids.add('crypto-ai');
  }
  if (ids.size === 0 && (plan?.strategies || []).length > 0) ids.add('crypto-ai');
  return [...ids];
}

export function validateStagedDispatch(rootDir, { confirm = '' } = {}) {
  const readiness = evaluateResearchLiveReadiness(rootDir);
  const request = latestEnableRequest(rootDir);
  const decision = latestApprovalDecision(rootDir);
  const plan = latestDispatchPlan(rootDir);
  const blockers = [];

  if (confirm !== 'STAGE_DEMO_TESTNET') blockers.push('confirm must equal STAGE_DEMO_TESTNET');
  if (!plan) blockers.push('missing dispatch plan');
  if (plan && plan.status !== 'STAGED') blockers.push(`dispatch plan status is ${plan.status}`);
  if (plan && plan.order_execution !== 'disabled') blockers.push('dispatch plan order_execution must remain disabled');
  if (plan && plan.engine_dispatch !== 'disabled') blockers.push('dispatch plan engine_dispatch must start disabled');
  if (!request || request.status !== 'PENDING_MANUAL_APPROVAL') blockers.push('missing pending manual enable request');
  if (!decision || decision.status !== 'APPROVED_FOR_STAGED_DISPATCH') blockers.push('missing approved staged dispatch decision');
  if (readiness.status !== 'READY_FOR_LIMITED_LIVE_REVIEW') blockers.push(`live readiness is ${readiness.status}`);
  if (!plan?.strategies?.length) blockers.push('dispatch plan has no strategies');
  for (const item of plan?.strategies || []) {
    if (item.order_execution !== 'disabled') blockers.push(`${item.strategy} order execution is not disabled`);
    if (Number(item.max_risk_pct || 0) > 0.001) blockers.push(`${item.strategy} max risk exceeds staged limit`);
    if (Number(item.max_positions || 0) > 1) blockers.push(`${item.strategy} max positions exceeds staged limit`);
  }

  return {
    allowed: blockers.length === 0,
    blockers,
    readiness,
    request,
    decision,
    plan,
    engineIds: plan ? engineIdsForDispatchPlan(plan) : [],
  };
}

export async function executeStagedDispatch(rootDir, options = {}, { getSettings, dispatchControlCommand } = {}) {
  const validation = validateStagedDispatch(rootDir, options);
  const blockedRecord = (blockers) => {
    const record = {
      id: `staged-dispatch-${Date.now()}`,
      created_at: new Date().toISOString(),
      ok: true,
      accepted: false,
      status: 'BLOCKED',
      blockers,
      engine_dispatch: 'disabled',
      order_execution: 'disabled',
    };
    appendJsonl(stagedDispatchResultsPath(rootDir), record);
    return {
      ...record,
      status_snapshot: collectResearchOsStatus(rootDir),
    };
  };

  if (!validation.allowed) return blockedRecord(validation.blockers);
  if (!getSettings || !dispatchControlCommand) return blockedRecord(['engine dispatch integration unavailable']);

  const commands = [];
  for (const engineId of validation.engineIds) {
    commands.push({
      engineId,
      action: 'pause',
      payload: { reason: 'Research OS staged dispatch safety lock' },
    });
    commands.push({
      engineId,
      action: 'set-risk-policy',
      payload: {
        mode: 'CAUTION',
        risk_scale: 0.25,
        max_positions: 1,
        reason: 'Research OS staged dispatch: demo/testnet observation only',
        strategies: validation.plan.strategies,
      },
    });
  }

  const results = [];
  for (const command of commands) {
    const result = await dispatchControlCommand(getSettings, command);
    results.push({ command, result });
  }
  const failed = results.filter((item) => !item.result?.ok);
  const record = {
    id: `staged-dispatch-${Date.now()}`,
    created_at: new Date().toISOString(),
    ok: failed.length === 0,
    accepted: failed.length === 0,
    status: failed.length === 0 ? 'STAGED_CONTROLS_SENT' : 'FAILED',
    engine_dispatch: failed.length === 0 ? 'pause_and_policy_sent' : 'partial_failure',
    order_execution: 'disabled',
    commands,
    results,
    blockers: failed.map((item) => `${item.command.engineId}:${item.command.action}:${item.result?.error || 'failed'}`),
  };
  appendJsonl(stagedDispatchResultsPath(rootDir), record);
  if (failed.length === 0) {
    writeJsonAtomic(dispatchPlanPath(rootDir), {
      ...validation.plan,
      status: record.status,
      engine_dispatch: record.engine_dispatch,
      order_execution: 'disabled',
      dispatched_at: record.created_at,
      dispatch_result_id: record.id,
    });
  }
  return {
    ...record,
    status_snapshot: collectResearchOsStatus(rootDir),
  };
}

export function evaluatePromotionCandidate(strategy, {
  minPassRate = 0.6,
  minWindows = 2,
} = {}) {
  const report = strategy.latest_report || {};
  const reasons = [];
  if (strategy.status !== 'forward_testing') reasons.push('strategy is not in forward_testing');
  if (!report.approved_for_forward_test) reasons.push('walk-forward report is not approved');
  if (Number(report.windows || 0) < minWindows) reasons.push(`walk-forward windows below ${minWindows}`);
  if (Number(report.pass_rate || 0) < minPassRate) reasons.push(`walk-forward pass rate below ${Math.round(minPassRate * 100)}%`);
  if ((report.gate_reasons || []).length) reasons.push(`walk-forward gate reasons remain: ${report.gate_reasons.join('; ')}`);
  return {
    approved: reasons.length === 0,
    reasons,
    metrics: {
      windows: Number(report.windows || 0),
      passed_windows: Number(report.passed_windows || 0),
      pass_rate: Number(report.pass_rate || 0),
    },
  };
}

export function collectResearchOsStatus(rootDir) {
  const researchDir = path.join(rootDir, 'research_lab');
  const strategyDir = path.join(rootDir, 'strategy_lab');
  const paperStore = readJsonl(path.join(researchDir, 'data', 'paper_store.jsonl'), 100);
  const latestPapers = readJson(path.join(researchDir, 'reports', 'latest_papers.json'), {});
  const latestHypotheses = readJson(path.join(researchDir, 'reports', 'latest_hypotheses.json'), {});
  const generatedProposals = readJson(path.join(researchDir, 'reports', 'latest_generated_proposals.json'), {});
  const batchSummary = readJson(path.join(strategyDir, 'reports', 'batch_summary.json'), {});
  const registry = readJson(path.join(strategyDir, 'registry', 'approved_strategies.json'), { version: 1, strategies: [] });
  const hypothesisFiles = listJsonFiles(path.join(researchDir, 'hypotheses'));
  const generatedStrategyFiles = listJsonFiles(path.join(strategyDir, 'strategies', 'generated'));
  const walkForwardFiles = listJsonFiles(path.join(strategyDir, 'reports', 'walk_forward'), 20);
  const lineage = buildStrategyLineage(rootDir);
  const liveReadiness = evaluateResearchLiveReadiness(rootDir);

  return {
    generatedAt: new Date().toISOString(),
    researchLab: {
      status: fs.existsSync(researchDir) ? 'ready' : 'missing',
      papers: {
        stored: paperStore.length,
        latestFound: latestPapers?.found || 0,
        markdownBrief: fs.existsSync(path.join(researchDir, 'reports', 'latest_papers.md')),
        top: paperStore.slice(0, 10).map((paper) => ({
          paper_id: paper.paper_id,
          title: paper.title,
          source: paper.source,
          score: paper.score,
          url: paper.url,
          keywords: paper.keywords || [],
        })),
      },
      hypotheses: {
        count: hypothesisFiles.length,
        latestCount: latestHypotheses?.hypotheses || 0,
        top: (latestHypotheses?.top || []).slice(0, 10).map((item) => ({
          hypothesis_id: item.hypothesis_id,
          regime: item.regime,
          strategy_family: item.strategy_family,
          confidence: item.confidence,
          source_paper_id: item.source_paper_id,
        })),
      },
      proposals: {
        generated: generatedStrategyFiles.length,
        latestGenerated: generatedProposals?.proposals || 0,
        files: generatedStrategyFiles.map((file) => path.relative(rootDir, file)),
      },
    },
    strategyLab: {
      status: fs.existsSync(strategyDir) ? 'ready' : 'missing',
      registry: summarizeRegistry(registry),
      batch: {
        proposals: batchSummary?.proposals || 0,
        runs: batchSummary?.runs || 0,
        passedRuns: batchSummary?.passed_runs || 0,
        bestOverall: batchSummary?.best_overall || [],
      },
      reports: {
        batchSummary: fs.existsSync(path.join(strategyDir, 'reports', 'batch_summary.json')),
      },
      walkForward: {
        reports: walkForwardFiles.length,
        approved: readJsonFiles(walkForwardFiles, rootDir).filter((item) => item.approved_for_forward_test).length,
        latest: readJsonFiles(walkForwardFiles, rootDir, 10),
      },
      shadow: summarizeShadow(rootDir),
      latestReview: latestResearchReview(rootDir),
      lineage: {
        total: lineage.length,
        riskCount: lineage.filter((item) => item.risk_flags.length > 0).length,
        items: lineage.slice(0, 20),
      },
      liveReadiness,
      handoff: latestHandoffManifest(rootDir),
      latestEnableRequest: latestEnableRequest(rootDir),
      latestApprovalDecision: latestApprovalDecision(rootDir),
      dispatchPlan: latestDispatchPlan(rootDir),
      stagedDispatch: latestStagedDispatchResult(rootDir),
    },
  };
}

function runCommand(rootDir, command, args, timeoutMs = 120000) {
  return new Promise((resolve) => {
    const startedAt = Date.now();
    const child = spawn(command, args, {
      cwd: rootDir,
      env: { ...process.env, PYTHONUNBUFFERED: '1' },
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    let stdout = '';
    let stderr = '';
    const timer = setTimeout(() => {
      child.kill('SIGTERM');
      stderr += `\nTimed out after ${timeoutMs}ms`;
    }, timeoutMs);
    child.stdout.on('data', (chunk) => { stdout += chunk.toString(); });
    child.stderr.on('data', (chunk) => { stderr += chunk.toString(); });
    child.on('error', (error) => {
      clearTimeout(timer);
      resolve({
        command: `${command} ${args.join(' ')}`,
        ok: false,
        code: null,
        durationMs: Date.now() - startedAt,
        stdout: stdout.trim(),
        stderr: (stderr || error.message).trim(),
      });
    });
    child.on('close', (code) => {
      clearTimeout(timer);
      resolve({
        command: `${command} ${args.join(' ')}`,
        ok: code === 0,
        code,
        durationMs: Date.now() - startedAt,
        stdout: stdout.trim(),
        stderr: stderr.trim(),
      });
    });
  });
}

export function buildResearchPipelineSteps({ mode = 'full', maxResults = 8 } = {}) {
  const normalizedMode = ['scout', 'digest', 'proposals', 'full'].includes(mode) ? mode : 'full';
  const safeMaxResults = Math.min(Math.max(Number(maxResults) || 8, 1), 20);
  const scout = [
    'python3',
    [
      '-m',
      'research_lab.run_scout',
      '--max-results',
      String(safeMaxResults),
      '--out',
      'research_lab/reports/latest_papers.json',
    ],
  ];
  const markdown = ['python3', ['-m', 'research_lab.run_markdown_export']];
  const digest = ['python3', ['-m', 'research_lab.run_digest']];
  const proposals = ['python3', ['-m', 'research_lab.run_proposal_builder']];
  if (normalizedMode === 'scout') return [scout, markdown];
  if (normalizedMode === 'digest') return [digest];
  if (normalizedMode === 'proposals') return [proposals];
  return [scout, markdown, digest, proposals];
}

export async function runResearchPipeline(rootDir, options = {}, runner = runCommand) {
  const steps = buildResearchPipelineSteps(options);
  const results = [];
  for (const [command, args] of steps) {
    const result = await runner(rootDir, command, args);
    results.push(result);
    if (!result.ok) break;
  }
  return {
    ok: results.every((result) => result.ok),
    mode: options.mode || 'full',
    steps: results,
    status: collectResearchOsStatus(rootDir),
  };
}

export function buildStrategyGateSteps({ count = 500, top = 10, network = 'production' } = {}) {
  const safeCount = Math.min(Math.max(Number(count) || 500, 100), 2000);
  const safeTop = Math.min(Math.max(Number(top) || 10, 1), 25);
  const safeNetwork = network === 'testnet' ? 'testnet' : 'production';
  return [[
    'python3',
    [
      '-m',
      'strategy_lab.run_batch_optimize',
      '--proposals',
      'strategy_lab/strategies/generated/*.json',
      '--network',
      safeNetwork,
      '--count',
      String(safeCount),
      '--top',
      String(safeTop),
      '--out',
      'strategy_lab/reports/batch_summary.json',
    ],
  ]];
}

export async function runStrategyGates(rootDir, options = {}, runner = runCommand) {
  const steps = buildStrategyGateSteps(options);
  const results = [];
  for (const [command, args] of steps) {
    const result = await runner(rootDir, command, args, 180000);
    const accepted = result.ok || result.code === 2;
    results.push({
      ...result,
      ok: accepted,
      gatePassed: result.code === 0,
    });
    if (!accepted) break;
  }
  const status = collectResearchOsStatus(rootDir);
  return {
    ok: results.every((result) => result.ok),
    gatePassed: results.some((result) => result.gatePassed),
    steps: results,
    status,
  };
}

export function discoverWalkForwardCandidates(rootDir, { limit = 5 } = {}) {
  const batchPath = path.join(rootDir, 'strategy_lab', 'reports', 'batch_summary.json');
  const batchSummary = readJson(batchPath, {});
  const rows = Array.isArray(batchSummary?.best_overall) ? batchSummary.best_overall : [];
  const safeLimit = Math.min(Math.max(Number(limit) || 5, 1), 20);
  return rows
    .filter((item) => Number(item.passed || 0) > 0)
    .slice(0, safeLimit)
    .map((item) => {
      const generatedPath = path.join(rootDir, 'strategy_lab', 'strategies', 'generated', `${item.proposal}.json`);
      const basePath = path.join(rootDir, 'strategy_lab', 'strategies', `${item.proposal}.json`);
      return {
        proposal: item.proposal,
        symbol: String(item.symbol || '').toUpperCase(),
        proposalPath: fs.existsSync(generatedPath) ? path.relative(rootDir, generatedPath) : path.relative(rootDir, basePath),
      };
    })
    .filter((item) => item.symbol && fs.existsSync(path.join(rootDir, item.proposalPath)));
}

export function buildWalkForwardSteps(rootDir, {
  limit = 5,
  count = 720,
  trainSize = 240,
  testSize = 120,
  stepSize = 120,
  network = 'production',
} = {}) {
  const candidates = discoverWalkForwardCandidates(rootDir, { limit });
  const safeCount = Math.min(Math.max(Number(count) || 720, 360), 2000);
  const safeTrainSize = Math.min(Math.max(Number(trainSize) || 240, 120), 1000);
  const safeTestSize = Math.min(Math.max(Number(testSize) || 120, 60), 500);
  const safeStepSize = Math.min(Math.max(Number(stepSize) || 120, 60), 500);
  const safeNetwork = network === 'testnet' ? 'testnet' : 'production';
  return candidates.map((candidate) => [
    'python3',
    [
      '-m',
      'strategy_lab.run_walk_forward',
      '--proposal',
      candidate.proposalPath,
      '--symbol',
      candidate.symbol,
      '--fetch-binance',
      '--network',
      safeNetwork,
      '--count',
      String(safeCount),
      '--train-size',
      String(safeTrainSize),
      '--test-size',
      String(safeTestSize),
      '--step-size',
      String(safeStepSize),
      '--out',
      `strategy_lab/reports/walk_forward/${candidate.proposal}_${candidate.symbol.toLowerCase()}_walk_forward.json`,
      '--registry',
      'strategy_lab/registry/approved_strategies.json',
    ],
  ]);
}

export async function runWalkForwardGates(rootDir, options = {}, runner = runCommand) {
  const steps = buildWalkForwardSteps(rootDir, options);
  const results = [];
  for (const [command, args] of steps) {
    const result = await runner(rootDir, command, args, 240000);
    const accepted = result.ok || result.code === 2;
    results.push({
      ...result,
      ok: accepted,
      gatePassed: result.code === 0,
    });
    if (!accepted) break;
  }
  const status = collectResearchOsStatus(rootDir);
  return {
    ok: results.every((result) => result.ok),
    gatePassed: results.some((result) => result.gatePassed),
    skipped: steps.length === 0,
    reason: steps.length === 0 ? 'no optimized candidates passed batch gates yet' : '',
    steps: results,
    status,
  };
}

export function runPromotionGate(rootDir, options = {}) {
  const registry = loadRegistry(rootDir);
  const thresholds = walkForwardPromotionThresholds(rootDir, options);
  const strategies = Array.isArray(registry.strategies) ? registry.strategies : [];
  const results = strategies.map((strategy) => {
    const evaluation = evaluatePromotionCandidate(strategy, thresholds);
    return {
      name: strategy.name,
      version: strategy.version || 1,
      market: strategy.market,
      previousStatus: strategy.status,
      nextStatus: evaluation.approved ? 'approved' : strategy.status,
      approved: evaluation.approved,
      reasons: evaluation.reasons,
      metrics: evaluation.metrics,
    };
  });
  const now = new Date().toISOString();
  let promoted = 0;
  registry.strategies = strategies.map((strategy) => {
    const result = results.find((item) => item.name === strategy.name && item.version === (strategy.version || 1));
    if (!result?.approved) return strategy;
    promoted += 1;
    return {
      ...strategy,
      status: 'approved',
      updated_at: Date.now() / 1000,
      approval: {
        approved_at: now,
        gate: 'promotion',
        metrics: result.metrics,
        requirements: {
          min_pass_rate: thresholds.minPassRate,
          min_windows: thresholds.minWindows,
        },
      },
    };
  });
  if (promoted > 0) saveRegistry(rootDir, registry);
  return {
    ok: true,
    promoted,
    evaluated: results.length,
    results,
    status: collectResearchOsStatus(rootDir),
  };
}

export function deployApprovedToShadow(rootDir, {
  mode = 'signal_only',
  network = 'testnet',
} = {}) {
  const safeMode = ['signal_only', 'paper', 'testnet_shadow'].includes(mode) ? mode : 'signal_only';
  const safeNetwork = network === 'production' ? 'production' : 'testnet';
  const registry = loadRegistry(rootDir);
  const approved = (registry.strategies || []).filter((strategy) => strategy.status === 'approved');
  const store = loadShadowDeployments(rootDir);
  const existing = new Map((store.deployments || []).map((item) => [item.id, item]));
  const now = new Date().toISOString();
  const deployments = [];
  for (const strategy of approved) {
    const id = deploymentId(strategy);
    const existed = existing.has(id);
    const deployment = {
      ...(existing.get(id) || {}),
      id,
      strategy_name: strategy.name,
      version: strategy.version || 1,
      market: strategy.market,
      symbols: strategy.symbols || [],
      timeframes: strategy.timeframes || {},
      mode: safeMode,
      network: safeNetwork,
      order_execution: 'disabled',
      status: 'active',
      source_status: strategy.status,
      deployed_at: existing.get(id)?.deployed_at || now,
      updated_at: now,
      latest_signal: null,
      notes: 'Shadow deployment observes approved strategies only; live order execution remains disabled.',
    };
    existing.set(id, deployment);
    deployments.push(deployment);
    appendJsonl(shadowEventsPath(rootDir), {
      ts: now,
      event: existed ? 'shadow_deployment_upserted' : 'shadow_deployment_created',
      deployment_id: id,
      strategy_name: strategy.name,
      mode: safeMode,
      network: safeNetwork,
      order_execution: 'disabled',
    });
  }
  store.version = 1;
  store.deployments = Array.from(existing.values());
  if (deployments.length > 0) saveShadowDeployments(rootDir, store);
  return {
    ok: true,
    deployed: deployments.length,
    deployments,
    status: collectResearchOsStatus(rootDir),
  };
}

function parseMadsSse(text) {
  let result = null;
  for (const block of String(text || '').split(/\n\n+/)) {
    const line = block.split('\n').find((item) => item.startsWith('data:'));
    if (!line) continue;
    try {
      const event = JSON.parse(line.slice(5).trim());
      if (event.type === 'result') result = event;
      if (event.type === 'error') throw new Error(event.message || 'MADS task failed');
    } catch (error) {
      if (error instanceof SyntaxError) continue;
      throw error;
    }
  }
  if (!result) throw new Error('MADS returned no result event');
  return result;
}

export function buildResearchFeedbackPackage(rootDir) {
  const status = collectResearchOsStatus(rootDir);
  const registry = loadRegistry(rootDir);
  const shadow = loadShadowDeployments(rootDir);
  const shadowMetrics = summarizeShadowSignals(rootDir);
  const lineage = buildStrategyLineage(rootDir);
  return {
    generated_at: new Date().toISOString(),
    status: {
      registry: status.strategyLab.registry,
      batch: status.strategyLab.batch,
      walk_forward: status.strategyLab.walkForward,
      shadow: status.strategyLab.shadow,
      shadow_metrics: shadowMetrics,
      live_readiness: status.strategyLab.liveReadiness,
    },
    lineage,
    strategies: (registry.strategies || []).map((strategy) => ({
      name: strategy.name,
      version: strategy.version || 1,
      market: strategy.market,
      symbols: strategy.symbols || [],
      timeframes: strategy.timeframes || {},
      type: strategy.type,
      status: strategy.status,
      approval: strategy.approval || null,
      latest_report: strategy.latest_report || {},
    })),
    shadow_deployments: shadow.deployments || [],
  };
}

export function heuristicResearchReview(feedbackPackage) {
  const registry = feedbackPackage.status.registry || {};
  const batch = feedbackPackage.status.batch || {};
  const walkForward = feedbackPackage.status.walk_forward || {};
  const shadow = feedbackPackage.status.shadow || {};
  const shadowMetrics = feedbackPackage.status.shadow_metrics || {};
  const actions = [];
  if ((batch.passedRuns || 0) === 0) {
    actions.push({
      action: 'research_more',
      severity: 'high',
      reason: 'No batch optimize candidate passed; generate new hypotheses or relax only research-side search space, not live guards.',
    });
  }
  if ((walkForward.approved || 0) === 0) {
    actions.push({
      action: 'hold_promotion',
      severity: 'high',
      reason: 'No walk-forward report is approved; do not promote strategies to live use.',
    });
  }
  if ((registry.byStatus?.approved || 0) > 0 && (shadow.active || 0) === 0) {
    actions.push({
      action: 'deploy_shadow',
      severity: 'medium',
      reason: 'Approved strategies exist but no active shadow deployment is observing them.',
    });
  }
  if ((shadow.active || 0) > 0) {
    actions.push({
      action: 'observe_shadow',
      severity: 'low',
      reason: 'Shadow deployments are active with order execution disabled; collect signal decay and slippage evidence before live enablement.',
    });
  }
  if ((shadowMetrics.outcomes || 0) > 0 && Number(shadowMetrics.expectancy_pct || 0) <= 0) {
    actions.push({
      action: 'reject_or_tune_shadow',
      severity: 'high',
      reason: `Shadow outcomes show non-positive expectancy (${Number(shadowMetrics.expectancy_pct || 0).toFixed(4)}%). Keep execution disabled and tune or reject.`,
    });
  }
  if (actions.length === 0) {
    actions.push({
      action: 'hold',
      severity: 'medium',
      reason: 'Research OS has no approved live-ready strategy yet; continue gated research cycle.',
    });
  }
  return [
    'Research OS Feedback Review',
    `Registry: total=${registry.total || 0}, approved=${registry.byStatus?.approved || 0}, forward_testing=${registry.byStatus?.forward_testing || 0}`,
    `Batch: runs=${batch.runs || 0}, passed=${batch.passedRuns || 0}`,
    `Walk-forward: approved=${walkForward.approved || 0}/${walkForward.reports || 0}`,
    `Shadow: active=${shadow.active || 0}/${shadow.deployments || 0}`,
    `Shadow metrics: signals=${shadowMetrics.signals || 0}, outcomes=${shadowMetrics.outcomes || 0}, expectancy=${Number(shadowMetrics.expectancy_pct || 0).toFixed(4)}, PF=${Number(shadowMetrics.profit_factor || 0).toFixed(2)}`,
    'Actions:',
    ...actions.map((item) => `- [${item.severity}] ${item.action}: ${item.reason}`),
  ].join('\n');
}

export async function requestResearchMadsReview({
  fetchImpl = globalThis.fetch,
  apiUrl = process.env.MADS_API_URL || 'http://127.0.0.1:4311',
  feedbackPackage,
}) {
  if (!fetchImpl) throw new Error('fetch is not available');
  const task = [
    'Review this TradeOps Research OS strategy pipeline as a hedge-fund research committee.',
    'Advisory only: do not place orders and do not enable live execution.',
    'Evaluate paper quality, batch optimization, walk-forward robustness, promotion readiness, and shadow deployment readiness.',
    'Recommend one or more actions: research_more, tune_parameters, reject_strategy, promote_strategy, deploy_shadow, observe_shadow, or hold.',
    'Return concise Thai output with evidence and next actions.',
    `Research OS JSON:\n${JSON.stringify(feedbackPackage)}`,
  ].join('\n');
  const response = await fetchImpl(`${apiUrl.replace(/\/$/, '')}/api/zeus/task`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ task, forceFull: true }),
    signal: AbortSignal.timeout(360000),
  });
  const text = await response.text();
  if (!response.ok) throw new Error(`MADS HTTP ${response.status}: ${text.slice(0, 200)}`);
  const result = parseMadsSse(text);
  return {
    source: 'mads',
    status: result.success ? 'completed' : 'vetoed',
    output: result.output || '',
    reason: result.reason || '',
    taskId: result.taskId || '',
    council: result.council || null,
  };
}

export async function runResearchFeedbackReview(rootDir, {
  apiUrl = process.env.MADS_API_URL || 'http://127.0.0.1:4311',
  fallback = true,
} = {}, fetchImpl = globalThis.fetch) {
  const feedbackPackage = buildResearchFeedbackPackage(rootDir);
  let review;
  try {
    review = await requestResearchMadsReview({ fetchImpl, apiUrl, feedbackPackage });
  } catch (error) {
    if (!fallback) throw error;
    review = {
      source: 'heuristic',
      status: 'completed',
      output: heuristicResearchReview(feedbackPackage),
      reason: `MADS unavailable: ${error.message}`,
      taskId: '',
      council: null,
    };
  }
  const record = {
    id: `research-review-${Date.now()}`,
    created_at: new Date().toISOString(),
    ...review,
    feedback: feedbackPackage,
  };
  appendJsonl(researchReviewsPath(rootDir), record);
  return {
    ok: true,
    review: record,
    status: collectResearchOsStatus(rootDir),
  };
}

export function installResearchOsRoutes(app, {
  rootDir,
  runner = runCommand,
  fetchImpl = globalThis.fetch,
  getSettings,
  dispatchControlCommand,
} = {}) {
  app.get('/api/research-os/status', (_req, res) => {
    res.json(collectResearchOsStatus(rootDir));
  });

  app.post('/api/research-os/run', async (req, res) => {
    try {
      const result = await runResearchPipeline(rootDir, req.body || {}, runner);
      res.status(result.ok ? 200 : 500).json(result);
    } catch (error) {
      res.status(500).json({
        ok: false,
        error: error.message,
        status: collectResearchOsStatus(rootDir),
      });
    }
  });

  app.post('/api/research-os/gates/run', async (req, res) => {
    try {
      const result = await runStrategyGates(rootDir, req.body || {}, runner);
      res.status(result.ok ? 200 : 500).json(result);
    } catch (error) {
      res.status(500).json({
        ok: false,
        error: error.message,
        status: collectResearchOsStatus(rootDir),
      });
    }
  });

  app.post('/api/research-os/walk-forward/run', async (req, res) => {
    try {
      const result = await runWalkForwardGates(rootDir, req.body || {}, runner);
      res.status(result.ok ? 200 : 500).json(result);
    } catch (error) {
      res.status(500).json({
        ok: false,
        error: error.message,
        status: collectResearchOsStatus(rootDir),
      });
    }
  });

  app.post('/api/research-os/promotion/run', (req, res) => {
    try {
      res.json(runPromotionGate(rootDir, req.body || {}));
    } catch (error) {
      res.status(500).json({
        ok: false,
        error: error.message,
        status: collectResearchOsStatus(rootDir),
      });
    }
  });

  app.post('/api/research-os/shadow/deploy', (req, res) => {
    try {
      res.json(deployApprovedToShadow(rootDir, req.body || {}));
    } catch (error) {
      res.status(500).json({
        ok: false,
        error: error.message,
        status: collectResearchOsStatus(rootDir),
      });
    }
  });

  app.post('/api/research-os/mads/review', async (req, res) => {
    try {
      const result = await runResearchFeedbackReview(rootDir, req.body || {}, fetchImpl);
      res.json(result);
    } catch (error) {
      res.status(500).json({
        ok: false,
        error: error.message,
        status: collectResearchOsStatus(rootDir),
      });
    }
  });

  app.post('/api/research-os/handoff/build', (req, res) => {
    try {
      res.json(buildExecutionHandoffManifest(rootDir, req.body || {}));
    } catch (error) {
      res.status(500).json({
        ok: false,
        error: error.message,
        status: collectResearchOsStatus(rootDir),
      });
    }
  });

  app.post('/api/research-os/enable/request', (req, res) => {
    try {
      res.json(createManualEnableRequest(rootDir, req.body || {}));
    } catch (error) {
      res.status(500).json({
        ok: false,
        error: error.message,
        status: collectResearchOsStatus(rootDir),
      });
    }
  });

  app.post('/api/research-os/enable/decision', (req, res) => {
    try {
      res.json(recordManualApprovalDecision(rootDir, req.body || {}));
    } catch (error) {
      res.status(500).json({
        ok: false,
        error: error.message,
        status: collectResearchOsStatus(rootDir),
      });
    }
  });

  app.post('/api/research-os/dispatch/stage', async (req, res) => {
    try {
      const result = await executeStagedDispatch(rootDir, req.body || {}, { getSettings, dispatchControlCommand });
      res.status(result.accepted ? 200 : 409).json(result);
    } catch (error) {
      res.status(500).json({
        ok: false,
        error: error.message,
        status: collectResearchOsStatus(rootDir),
      });
    }
  });
}
