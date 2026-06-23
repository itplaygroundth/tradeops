import assert from 'node:assert/strict';
import fs from 'fs';
import os from 'os';
import path from 'path';
import test from 'node:test';

import {
  buildExecutionHandoffManifest,
  executeStagedDispatch,
  buildResearchFeedbackPackage,
  buildStrategyLineage,
  createManualEnableRequest,
  buildWalkForwardSteps,
  buildStrategyGateSteps,
  buildResearchPipelineSteps,
  collectResearchOsStatus,
  deployApprovedToShadow,
  discoverWalkForwardCandidates,
  evaluatePromotionCandidate,
  evaluateResearchLiveReadiness,
  heuristicResearchReview,
  loadPromotionPolicy,
  recordManualApprovalDecision,
  validateStagedDispatch,
  runResearchPipeline,
  runResearchFeedbackReview,
  runPromotionGate,
  runStrategyGates,
  runWalkForwardGates,
} from './researchOsStatus.js';

function writeJson(filePath, value) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(value, null, 2));
}

test('collectResearchOsStatus summarizes research and strategy lab files', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'research-os-'));
  fs.mkdirSync(path.join(root, 'research_lab', 'data'), { recursive: true });
  fs.writeFileSync(
    path.join(root, 'research_lab', 'data', 'paper_store.jsonl'),
    `${JSON.stringify({
      paper_id: 'p1',
      title: 'Crypto Volatility',
      source: 'arxiv',
      score: 12,
      url: 'https://example.test/p1',
      keywords: ['volatility'],
    })}\n`,
  );
  writeJson(path.join(root, 'research_lab', 'reports', 'latest_papers.json'), { found: 1, stored: 1 });
  writeJson(path.join(root, 'research_lab', 'reports', 'latest_hypotheses.json'), {
    hypotheses: 1,
    top: [{
      hypothesis_id: 'h1',
      regime: 'high_volatility',
      strategy_family: 'volatility_regime_filter',
      confidence: 0.7,
      source_paper_id: 'p1',
    }],
  });
  writeJson(path.join(root, 'research_lab', 'reports', 'latest_generated_proposals.json'), { proposals: 1 });
  writeJson(path.join(root, 'research_lab', 'hypotheses', 'h1.json'), { hypothesis_id: 'h1' });
  writeJson(path.join(root, 'strategy_lab', 'strategies', 'generated', 's1.json'), { name: 's1' });
  writeJson(path.join(root, 'strategy_lab', 'reports', 'batch_summary.json'), {
    proposals: 1,
    runs: 2,
    passed_runs: 0,
    best_overall: [{ proposal: 's1', symbol: 'BTCUSDT' }],
  });
  writeJson(path.join(root, 'strategy_lab', 'registry', 'approved_strategies.json'), {
    version: 1,
    strategies: [{ name: 's1', status: 'draft', type: 'market_structure' }],
  });

  const status = collectResearchOsStatus(root);

  assert.equal(status.researchLab.status, 'ready');
  assert.equal(status.researchLab.papers.stored, 1);
  assert.equal(status.researchLab.hypotheses.count, 1);
  assert.equal(status.researchLab.proposals.generated, 1);
  assert.equal(status.strategyLab.registry.total, 1);
  assert.equal(status.strategyLab.registry.byStatus.draft, 1);
  assert.equal(status.strategyLab.batch.runs, 2);
});

test('buildResearchPipelineSteps composes a full research-only pipeline', () => {
  const steps = buildResearchPipelineSteps({ mode: 'full', maxResults: 4 });

  assert.equal(steps.length, 4);
  assert.deepEqual(steps[0], [
    'python3',
    [
      '-m',
      'research_lab.run_scout',
      '--max-results',
      '4',
      '--out',
      'research_lab/reports/latest_papers.json',
    ],
  ]);
  assert.deepEqual(steps[1], ['python3', ['-m', 'research_lab.run_markdown_export']]);
  assert.deepEqual(steps[2], ['python3', ['-m', 'research_lab.run_digest']]);
  assert.deepEqual(steps[3], ['python3', ['-m', 'research_lab.run_proposal_builder']]);
});

test('runResearchPipeline stops after a failed step', async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'research-os-run-'));
  fs.mkdirSync(path.join(root, 'research_lab', 'data'), { recursive: true });
  const calls = [];
  const runner = async (_rootDir, command, args) => {
    calls.push(`${command} ${args.join(' ')}`);
    return {
      command: `${command} ${args.join(' ')}`,
      ok: calls.length === 1,
      code: calls.length === 1 ? 0 : 1,
      durationMs: 1,
      stdout: '',
      stderr: calls.length === 1 ? '' : 'markdown export failed',
    };
  };

  const result = await runResearchPipeline(root, { mode: 'full', maxResults: 2 }, runner);

  assert.equal(result.ok, false);
  assert.equal(result.steps.length, 2);
  assert.match(result.steps[1].stderr, /markdown export failed/);
  assert.equal(calls[0], 'python3 -m research_lab.run_scout --max-results 2 --out research_lab/reports/latest_papers.json');
  assert.equal(calls[1], 'python3 -m research_lab.run_markdown_export');
});

test('buildStrategyGateSteps composes batch optimize command with safe bounds', () => {
  const steps = buildStrategyGateSteps({ count: 50, top: 99, network: 'testnet' });

  assert.equal(steps.length, 1);
  assert.deepEqual(steps[0], [
    'python3',
    [
      '-m',
      'strategy_lab.run_batch_optimize',
      '--proposals',
      'strategy_lab/strategies/generated/*.json',
      '--network',
      'testnet',
      '--count',
      '100',
      '--top',
      '25',
      '--out',
      'strategy_lab/reports/batch_summary.json',
    ],
  ]);
});

test('runStrategyGates accepts optimizer code 2 as completed gate failure', async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'research-os-gates-'));
  fs.mkdirSync(path.join(root, 'strategy_lab', 'reports'), { recursive: true });
  writeJson(path.join(root, 'strategy_lab', 'reports', 'batch_summary.json'), {
    proposals: 2,
    runs: 4,
    passed_runs: 0,
    best_overall: [],
  });
  const runner = async (_rootDir, command, args) => ({
    command: `${command} ${args.join(' ')}`,
    ok: false,
    code: 2,
    durationMs: 1,
    stdout: '{"passed_runs":0}',
    stderr: '',
  });

  const result = await runStrategyGates(root, { count: 200, top: 3 }, runner);

  assert.equal(result.ok, true);
  assert.equal(result.gatePassed, false);
  assert.equal(result.steps[0].ok, true);
  assert.equal(result.steps[0].gatePassed, false);
  assert.equal(result.status.strategyLab.batch.runs, 4);
});

test('discoverWalkForwardCandidates selects passed batch candidates only', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'research-os-wf-'));
  writeJson(path.join(root, 'strategy_lab', 'strategies', 'generated', 'alpha.json'), {
    name: 'alpha',
    symbols: ['BTCUSDT'],
  });
  writeJson(path.join(root, 'strategy_lab', 'reports', 'batch_summary.json'), {
    best_overall: [
      { proposal: 'alpha', symbol: 'BTCUSDT', passed: 2 },
      { proposal: 'beta', symbol: 'ETHUSDT', passed: 0 },
    ],
  });

  const candidates = discoverWalkForwardCandidates(root);

  assert.deepEqual(candidates, [{
    proposal: 'alpha',
    symbol: 'BTCUSDT',
    proposalPath: path.join('strategy_lab', 'strategies', 'generated', 'alpha.json'),
  }]);
});

test('buildWalkForwardSteps composes walk-forward commands for optimized candidates', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'research-os-wf-steps-'));
  writeJson(path.join(root, 'strategy_lab', 'strategies', 'generated', 'alpha.json'), {
    name: 'alpha',
    symbols: ['BTCUSDT'],
  });
  writeJson(path.join(root, 'strategy_lab', 'reports', 'batch_summary.json'), {
    best_overall: [{ proposal: 'alpha', symbol: 'BTCUSDT', passed: 1 }],
  });

  const steps = buildWalkForwardSteps(root, { count: 100, trainSize: 10, testSize: 20, stepSize: 20, network: 'testnet' });

  assert.deepEqual(steps, [[
    'python3',
    [
      '-m',
      'strategy_lab.run_walk_forward',
      '--proposal',
      path.join('strategy_lab', 'strategies', 'generated', 'alpha.json'),
      '--symbol',
      'BTCUSDT',
      '--fetch-binance',
      '--network',
      'testnet',
      '--count',
      '360',
      '--train-size',
      '120',
      '--test-size',
      '60',
      '--step-size',
      '60',
      '--out',
      'strategy_lab/reports/walk_forward/alpha_btcusdt_walk_forward.json',
      '--registry',
      'strategy_lab/registry/approved_strategies.json',
    ],
  ]]);
});

test('runWalkForwardGates skips cleanly when there are no optimized candidates', async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'research-os-wf-skip-'));
  writeJson(path.join(root, 'strategy_lab', 'reports', 'batch_summary.json'), {
    best_overall: [{ proposal: 'alpha', symbol: 'BTCUSDT', passed: 0 }],
  });
  const runner = async () => {
    throw new Error('runner should not be called');
  };

  const result = await runWalkForwardGates(root, {}, runner);

  assert.equal(result.ok, true);
  assert.equal(result.skipped, true);
  assert.equal(result.gatePassed, false);
  assert.match(result.reason, /no optimized candidates/);
  assert.equal(result.steps.length, 0);
});

test('evaluatePromotionCandidate approves only clean forward-testing reports', () => {
  const strategy = {
    status: 'forward_testing',
    latest_report: {
      approved_for_forward_test: true,
      windows: 4,
      passed_windows: 3,
      pass_rate: 0.75,
      gate_reasons: [],
    },
  };

  const result = evaluatePromotionCandidate(strategy);

  assert.equal(result.approved, true);
  assert.deepEqual(result.reasons, []);
  assert.equal(result.metrics.pass_rate, 0.75);
});

test('runPromotionGate promotes passing forward-testing strategies and blocks weak ones', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'research-os-promotion-'));
  writeJson(path.join(root, 'strategy_lab', 'registry', 'approved_strategies.json'), {
    version: 1,
    strategies: [
      {
        name: 'alpha',
        version: 1,
        market: 'crypto',
        symbols: ['BTCUSDT'],
        timeframes: { entry: 'M15', confirm: 'H1', regime: 'H4' },
        type: 'trend_following',
        status: 'forward_testing',
        proposal: { name: 'alpha' },
        latest_report: {
          approved_for_forward_test: true,
          windows: 4,
          passed_windows: 3,
          pass_rate: 0.75,
          gate_reasons: [],
        },
      },
      {
        name: 'beta',
        version: 1,
        market: 'crypto',
        symbols: ['ETHUSDT'],
        timeframes: { entry: 'M15', confirm: 'H1', regime: 'H4' },
        type: 'mean_reversion',
        status: 'forward_testing',
        proposal: { name: 'beta' },
        latest_report: {
          approved_for_forward_test: false,
          windows: 4,
          passed_windows: 1,
          pass_rate: 0.25,
          gate_reasons: ['walk-forward pass rate below 60%'],
        },
      },
    ],
  });

  const result = runPromotionGate(root);
  const registry = JSON.parse(fs.readFileSync(path.join(root, 'strategy_lab', 'registry', 'approved_strategies.json'), 'utf8'));

  assert.equal(result.promoted, 1);
  assert.equal(registry.strategies[0].status, 'approved');
  assert.equal(registry.strategies[0].approval.gate, 'promotion');
  assert.equal(registry.strategies[1].status, 'forward_testing');
  assert.match(result.results[1].reasons.join(' '), /walk-forward report is not approved/);
});

test('runPromotionGate reads walk-forward thresholds from shared promotion policy', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'research-os-promotion-policy-'));
  writeJson(path.join(root, 'strategy_lab', 'config', 'promotion_policy.json'), {
    version: 1,
    walk_forward_promotion_gate: {
      min_pass_rate: 0.8,
      min_windows: 5,
    },
  });
  writeJson(path.join(root, 'strategy_lab', 'registry', 'approved_strategies.json'), {
    version: 1,
    strategies: [{
      name: 'strict-alpha',
      version: 1,
      market: 'crypto',
      symbols: ['BTCUSDT'],
      timeframes: { entry: 'M15', confirm: 'H1', regime: 'H4' },
      type: 'trend_following',
      status: 'forward_testing',
      latest_report: {
        approved_for_forward_test: true,
        windows: 4,
        passed_windows: 3,
        pass_rate: 0.75,
        gate_reasons: [],
      },
    }],
  });

  const policy = loadPromotionPolicy(root);
  const result = runPromotionGate(root);

  assert.equal(policy.walk_forward_promotion_gate.min_pass_rate, 0.8);
  assert.equal(result.promoted, 0);
  assert.match(result.results[0].reasons.join(' '), /windows below 5/);
  assert.match(result.results[0].reasons.join(' '), /pass rate below 80%/);
});

test('deployApprovedToShadow creates signal-only deployments with execution disabled', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'research-os-shadow-'));
  writeJson(path.join(root, 'strategy_lab', 'registry', 'approved_strategies.json'), {
    version: 1,
    strategies: [
      {
        name: 'alpha',
        version: 1,
        market: 'crypto',
        symbols: ['BTCUSDT'],
        timeframes: { entry: 'M15', confirm: 'H1', regime: 'H4' },
        type: 'trend_following',
        status: 'approved',
      },
      {
        name: 'beta',
        version: 1,
        market: 'crypto',
        symbols: ['ETHUSDT'],
        timeframes: { entry: 'M15', confirm: 'H1', regime: 'H4' },
        type: 'mean_reversion',
        status: 'forward_testing',
      },
    ],
  });

  const result = deployApprovedToShadow(root, { mode: 'testnet_shadow', network: 'testnet' });
  const shadow = JSON.parse(fs.readFileSync(path.join(root, 'strategy_lab', 'shadow', 'deployments.json'), 'utf8'));
  const events = fs.readFileSync(path.join(root, 'strategy_lab', 'shadow', 'events.jsonl'), 'utf8').trim().split(/\r?\n/);

  assert.equal(result.deployed, 1);
  assert.equal(shadow.deployments.length, 1);
  assert.equal(shadow.deployments[0].id, 'crypto:alpha:v1');
  assert.equal(shadow.deployments[0].status, 'active');
  assert.equal(shadow.deployments[0].mode, 'testnet_shadow');
  assert.equal(shadow.deployments[0].order_execution, 'disabled');
  assert.equal(events.length, 1);
  assert.match(events[0], /shadow_deployment_created/);
});

test('buildResearchFeedbackPackage summarizes gates and shadow deployments', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'research-os-feedback-'));
  writeJson(path.join(root, 'strategy_lab', 'registry', 'approved_strategies.json'), {
    version: 1,
    strategies: [{
      name: 'alpha',
      version: 1,
      market: 'crypto',
      symbols: ['BTCUSDT'],
      timeframes: { entry: 'M15', confirm: 'H1', regime: 'H4' },
      type: 'trend_following',
      status: 'approved',
      latest_report: { pass_rate: 0.75 },
    }],
  });
  writeJson(path.join(root, 'strategy_lab', 'reports', 'batch_summary.json'), {
    proposals: 1,
    runs: 2,
    passed_runs: 1,
    best_overall: [],
  });
  writeJson(path.join(root, 'strategy_lab', 'shadow', 'deployments.json'), {
    version: 1,
    deployments: [{ id: 'crypto:alpha:v1', status: 'active', mode: 'testnet_shadow' }],
  });
  fs.mkdirSync(path.join(root, 'strategy_lab', 'shadow'), { recursive: true });
  fs.writeFileSync(
    path.join(root, 'strategy_lab', 'shadow', 'signals.jsonl'),
    `${JSON.stringify({ strategy_name: 'alpha', action: 'LONG', theoretical_pnl_pct: -0.25 })}\n`,
  );

  const payload = buildResearchFeedbackPackage(root);
  const output = heuristicResearchReview(payload);

  assert.equal(payload.status.registry.byStatus.approved, 1);
  assert.equal(payload.status.shadow.active, 1);
  assert.equal(payload.status.shadow_metrics.signals, 1);
  assert.equal(payload.status.shadow_metrics.expectancy_pct, -0.25);
  assert.match(output, /Research OS Feedback Review/);
  assert.match(output, /Shadow metrics/);
  assert.match(output, /reject_or_tune_shadow/);
});

test('runResearchFeedbackReview stores MADS result when available', async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'research-os-mads-'));
  writeJson(path.join(root, 'strategy_lab', 'registry', 'approved_strategies.json'), {
    version: 1,
    strategies: [],
  });
  const fetchImpl = async () => ({
    ok: true,
    text: async () => `data: ${JSON.stringify({
      type: 'result',
      success: true,
      output: 'ควร research เพิ่ม',
      taskId: 'task-1',
    })}\n\n`,
  });

  const result = await runResearchFeedbackReview(root, { apiUrl: 'http://mads.test' }, fetchImpl);
  const rows = fs.readFileSync(path.join(root, 'strategy_lab', 'reviews', 'research_os_reviews.jsonl'), 'utf8').trim().split(/\r?\n/);

  assert.equal(result.ok, true);
  assert.equal(result.review.source, 'mads');
  assert.equal(result.review.taskId, 'task-1');
  assert.equal(rows.length, 1);
});

test('runResearchFeedbackReview falls back to heuristic when MADS is offline', async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'research-os-mads-fallback-'));
  writeJson(path.join(root, 'strategy_lab', 'registry', 'approved_strategies.json'), {
    version: 1,
    strategies: [],
  });
  const fetchImpl = async () => {
    throw new Error('connection refused');
  };

  const result = await runResearchFeedbackReview(root, { fallback: true }, fetchImpl);

  assert.equal(result.ok, true);
  assert.equal(result.review.source, 'heuristic');
  assert.match(result.review.reason, /connection refused/);
  assert.match(result.review.output, /Research OS Feedback Review/);
  assert.equal(result.status.strategyLab.latestReview.source, 'heuristic');
});

test('buildStrategyLineage links paper, hypothesis, gates, registry and shadow state', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'research-os-lineage-'));
  fs.mkdirSync(path.join(root, 'research_lab', 'data'), { recursive: true });
  fs.writeFileSync(
    path.join(root, 'research_lab', 'data', 'paper_store.jsonl'),
    `${JSON.stringify({
      paper_id: 'paper-1',
      title: 'Liquidity Driven Alpha',
      source: 'arxiv',
      score: 10,
    })}\n`,
  );
  writeJson(path.join(root, 'research_lab', 'hypotheses', 'hyp-1.json'), {
    hypothesis_id: 'hyp-1',
    source_paper_id: 'paper-1',
    strategy_family: 'order_flow_liquidity',
    regime: 'market_microstructure',
  });
  writeJson(path.join(root, 'strategy_lab', 'strategies', 'generated', 'alpha.json'), {
    name: 'alpha',
    version: 1,
    market: 'crypto',
    symbols: ['BTCUSDT'],
    timeframes: { entry: 'M15', confirm: 'H1', regime: 'H4' },
    type: 'market_structure',
    parameters: {
      source_paper_id: 'paper-1',
      source_hypothesis_id: 'hyp-1',
      research_confidence: 0.7,
    },
  });
  writeJson(path.join(root, 'strategy_lab', 'reports', 'batch_summary.json'), {
    best_overall: [{
      proposal: 'alpha',
      symbol: 'BTCUSDT',
      passed: 2,
      best: { score: 1.2, profit_factor: 1.5 },
    }],
  });
  writeJson(path.join(root, 'strategy_lab', 'reports', 'walk_forward', 'alpha_btcusdt_walk_forward.json'), {
    strategy_name: 'alpha',
    symbol: 'BTCUSDT',
    windows: 4,
    passed_windows: 3,
    pass_rate: 0.75,
    approved_for_forward_test: true,
    gate_reasons: [],
  });
  writeJson(path.join(root, 'strategy_lab', 'registry', 'approved_strategies.json'), {
    version: 1,
    strategies: [{
      name: 'alpha',
      version: 1,
      market: 'crypto',
      symbols: ['BTCUSDT'],
      timeframes: { entry: 'M15', confirm: 'H1', regime: 'H4' },
      type: 'market_structure',
      status: 'approved',
      latest_report: { pass_rate: 0.75 },
    }],
  });
  writeJson(path.join(root, 'strategy_lab', 'shadow', 'deployments.json'), {
    version: 1,
    deployments: [{ id: 'crypto:alpha:v1', strategy_name: 'alpha', status: 'active', mode: 'testnet_shadow' }],
  });

  const lineage = buildStrategyLineage(root);

  assert.equal(lineage.length, 1);
  assert.equal(lineage[0].strategy, 'alpha');
  assert.equal(lineage[0].source_paper_title, 'Liquidity Driven Alpha');
  assert.equal(lineage[0].hypothesis_family, 'order_flow_liquidity');
  assert.equal(lineage[0].batch.passed, 2);
  assert.equal(lineage[0].walk_forward.approved, 1);
  assert.equal(lineage[0].registry.status, 'approved');
  assert.equal(lineage[0].shadow.active, 1);
  assert.deepEqual(lineage[0].risk_flags, []);
});

test('evaluateResearchLiveReadiness blocks incomplete strategies and approves fully evidenced shadow state', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'research-os-readiness-'));
  writeJson(path.join(root, 'strategy_lab', 'strategies', 'generated', 'alpha.json'), {
    name: 'alpha',
    version: 1,
    market: 'crypto',
    symbols: ['BTCUSDT'],
    timeframes: { entry: 'M15', confirm: 'H1', regime: 'H4' },
    type: 'market_structure',
    parameters: {
      source_paper_id: 'paper-1',
      source_hypothesis_id: 'hyp-1',
      research_confidence: 0.7,
    },
  });

  const blocked = evaluateResearchLiveReadiness(root);
  assert.equal(blocked.status, 'BLOCKED');
  assert.match(blocked.blockers.join(' '), /strategy is not approved/);

  fs.mkdirSync(path.join(root, 'research_lab', 'data'), { recursive: true });
  fs.writeFileSync(
    path.join(root, 'research_lab', 'data', 'paper_store.jsonl'),
    `${JSON.stringify({ paper_id: 'paper-1', title: 'Alpha Paper' })}\n`,
  );
  writeJson(path.join(root, 'research_lab', 'hypotheses', 'hyp-1.json'), {
    hypothesis_id: 'hyp-1',
    source_paper_id: 'paper-1',
    strategy_family: 'order_flow_liquidity',
    regime: 'market_microstructure',
  });
  writeJson(path.join(root, 'strategy_lab', 'reports', 'walk_forward', 'alpha_btcusdt_walk_forward.json'), {
    strategy_name: 'alpha',
    symbol: 'BTCUSDT',
    windows: 4,
    passed_windows: 3,
    pass_rate: 0.75,
    approved_for_forward_test: true,
    gate_reasons: [],
  });
  writeJson(path.join(root, 'strategy_lab', 'registry', 'approved_strategies.json'), {
    version: 1,
    strategies: [{
      name: 'alpha',
      version: 1,
      market: 'crypto',
      symbols: ['BTCUSDT'],
      timeframes: { entry: 'M15', confirm: 'H1', regime: 'H4' },
      type: 'market_structure',
      status: 'approved',
      latest_report: { approved_for_forward_test: true, windows: 4, passed_windows: 3, pass_rate: 0.75, gate_reasons: [] },
    }],
  });
  writeJson(path.join(root, 'strategy_lab', 'shadow', 'deployments.json'), {
    version: 1,
    deployments: [{ id: 'crypto:alpha:v1', strategy_name: 'alpha', status: 'active', mode: 'testnet_shadow' }],
  });
  fs.mkdirSync(path.join(root, 'strategy_lab', 'reviews'), { recursive: true });
  fs.writeFileSync(
    path.join(root, 'strategy_lab', 'reviews', 'research_os_reviews.jsonl'),
    `${JSON.stringify({ created_at: '2026-06-22T00:00:00.000Z', source: 'mads', status: 'completed', output: 'ok' })}\n`,
  );

  const ready = evaluateResearchLiveReadiness(root);
  assert.equal(ready.status, 'READY_FOR_LIMITED_LIVE_REVIEW');
  assert.equal(ready.readyForLimitedLiveReview, 1);
  assert.deepEqual(ready.items[0].blockers, []);
});

test('buildExecutionHandoffManifest requires readiness and never enables execution', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'research-os-handoff-'));
  writeJson(path.join(root, 'strategy_lab', 'strategies', 'generated', 'alpha.json'), {
    name: 'alpha',
    version: 1,
    market: 'crypto',
    symbols: ['BTCUSDT'],
    timeframes: { entry: 'M15', confirm: 'H1', regime: 'H4' },
    type: 'market_structure',
    parameters: {
      source_paper_id: 'paper-1',
      source_hypothesis_id: 'hyp-1',
      research_confidence: 0.7,
    },
  });

  const blocked = buildExecutionHandoffManifest(root);
  assert.equal(blocked.manifest.status, 'blocked');
  assert.equal(blocked.built, 0);
  assert.equal(fs.existsSync(path.join(root, 'strategy_lab', 'handoff', 'execution_handoff.json')), false);

  fs.mkdirSync(path.join(root, 'research_lab', 'data'), { recursive: true });
  fs.writeFileSync(
    path.join(root, 'research_lab', 'data', 'paper_store.jsonl'),
    `${JSON.stringify({ paper_id: 'paper-1', title: 'Alpha Paper' })}\n`,
  );
  writeJson(path.join(root, 'research_lab', 'hypotheses', 'hyp-1.json'), {
    hypothesis_id: 'hyp-1',
    source_paper_id: 'paper-1',
    strategy_family: 'order_flow_liquidity',
    regime: 'market_microstructure',
  });
  writeJson(path.join(root, 'strategy_lab', 'reports', 'walk_forward', 'alpha_btcusdt_walk_forward.json'), {
    strategy_name: 'alpha',
    symbol: 'BTCUSDT',
    windows: 4,
    passed_windows: 3,
    pass_rate: 0.75,
    approved_for_forward_test: true,
    gate_reasons: [],
  });
  writeJson(path.join(root, 'strategy_lab', 'registry', 'approved_strategies.json'), {
    version: 1,
    strategies: [{
      name: 'alpha',
      version: 1,
      market: 'crypto',
      symbols: ['BTCUSDT'],
      timeframes: { entry: 'M15', confirm: 'H1', regime: 'H4' },
      type: 'market_structure',
      status: 'approved',
      latest_report: { approved_for_forward_test: true, windows: 4, passed_windows: 3, pass_rate: 0.75, gate_reasons: [] },
    }],
  });
  writeJson(path.join(root, 'strategy_lab', 'shadow', 'deployments.json'), {
    version: 1,
    deployments: [{ id: 'crypto:alpha:v1', strategy_name: 'alpha', status: 'active', mode: 'testnet_shadow' }],
  });
  fs.mkdirSync(path.join(root, 'strategy_lab', 'reviews'), { recursive: true });
  fs.writeFileSync(
    path.join(root, 'strategy_lab', 'reviews', 'research_os_reviews.jsonl'),
    `${JSON.stringify({ created_at: '2026-06-22T00:00:00.000Z', source: 'mads', status: 'completed', output: 'ok' })}\n`,
  );

  const ready = buildExecutionHandoffManifest(root);
  const saved = JSON.parse(fs.readFileSync(path.join(root, 'strategy_lab', 'handoff', 'execution_handoff.json'), 'utf8'));

  assert.equal(ready.manifest.status, 'ready_for_manual_enable');
  assert.equal(ready.built, 1);
  assert.equal(saved.order_execution, 'requires_manual_enable');
  assert.equal(saved.strategies[0].controls.order_execution, 'disabled');
  assert.equal(saved.strategies[0].controls.requires_manual_enable, true);
  assert.equal(ready.status.strategyLab.handoff.status, 'ready_for_manual_enable');
});

test('createManualEnableRequest records approval request without enabling execution', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'research-os-enable-'));

  const blocked = createManualEnableRequest(root, { requestedBy: 'test' });
  assert.equal(blocked.created, false);
  assert.equal(blocked.request.status, 'BLOCKED');
  assert.equal(blocked.request.order_execution, 'disabled');

  writeJson(path.join(root, 'strategy_lab', 'handoff', 'execution_handoff.json'), {
    id: 'handoff-1',
    created_at: '2026-06-22T00:00:00.000Z',
    status: 'ready_for_manual_enable',
    target_mode: 'limited_live_review',
    order_execution: 'requires_manual_enable',
    strategies: [{
      strategy: 'alpha',
      version: 1,
      stage: 'approved',
      controls: {
        order_execution: 'disabled',
        requires_manual_enable: true,
        max_risk_pct: 0.001,
        max_positions: 1,
        daily_loss_stop_usd: 5,
      },
    }],
    blockers: [],
    warnings: [],
  });

  const ready = createManualEnableRequest(root, { requestedBy: 'operator', reason: 'limited review' });
  const rows = fs.readFileSync(path.join(root, 'strategy_lab', 'handoff', 'enable_requests.jsonl'), 'utf8').trim().split(/\r?\n/);

  assert.equal(ready.created, true);
  assert.equal(ready.request.status, 'PENDING_MANUAL_APPROVAL');
  assert.equal(ready.request.order_execution, 'disabled');
  assert.equal(ready.request.strategies[0].order_execution, 'disabled');
  assert.equal(ready.request.strategies[0].max_positions, 1);
  assert.equal(ready.status.strategyLab.latestEnableRequest.status, 'PENDING_MANUAL_APPROVAL');
  assert.equal(rows.length, 2);
});

test('recordManualApprovalDecision stages dispatch plan without engine dispatch', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'research-os-decision-'));

  const blocked = recordManualApprovalDecision(root, { decision: 'approve', operator: 'test' });
  assert.equal(blocked.accepted, false);
  assert.equal(blocked.decision.status, 'BLOCKED');
  assert.equal(blocked.decision.engine_dispatch, 'disabled');

  fs.mkdirSync(path.join(root, 'strategy_lab', 'handoff'), { recursive: true });
  fs.writeFileSync(
    path.join(root, 'strategy_lab', 'handoff', 'enable_requests.jsonl'),
    `${JSON.stringify({
      id: 'enable-1',
      created_at: '2026-06-22T00:00:00.000Z',
      status: 'PENDING_MANUAL_APPROVAL',
      manifest_id: 'handoff-1',
      strategies: [{
        strategy: 'alpha',
        version: 1,
        max_risk_pct: 0.001,
        max_positions: 1,
        daily_loss_stop_usd: 5,
        order_execution: 'disabled',
      }],
      order_execution: 'disabled',
    })}\n`,
  );

  const approved = recordManualApprovalDecision(root, { decision: 'approve', operator: 'operator', reason: 'ok' });
  const plan = JSON.parse(fs.readFileSync(path.join(root, 'strategy_lab', 'handoff', 'dispatch_plan.json'), 'utf8'));

  assert.equal(approved.accepted, true);
  assert.equal(approved.decision.status, 'APPROVED_FOR_STAGED_DISPATCH');
  assert.equal(approved.decision.engine_dispatch, 'disabled');
  assert.equal(plan.status, 'STAGED');
  assert.equal(plan.engine_dispatch, 'disabled');
  assert.equal(plan.order_execution, 'disabled');
  assert.equal(plan.strategies[0].dispatch_status, 'staged');
  assert.equal(plan.strategies[0].order_execution, 'disabled');
  assert.equal(approved.status.strategyLab.latestApprovalDecision.status, 'APPROVED_FOR_STAGED_DISPATCH');
  assert.equal(approved.status.strategyLab.dispatchPlan.status, 'STAGED');
});

test('validateStagedDispatch fails closed without confirmation or readiness', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'research-os-dispatch-block-'));

  const result = validateStagedDispatch(root, {});

  assert.equal(result.allowed, false);
  assert.match(result.blockers.join(' '), /confirm must equal STAGE_DEMO_TESTNET/);
  assert.match(result.blockers.join(' '), /missing dispatch plan/);
});

test('executeStagedDispatch sends only pause and risk policy when fully staged', async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'research-os-dispatch-ok-'));
  writeJson(path.join(root, 'strategy_lab', 'strategies', 'generated', 'alpha.json'), {
    name: 'alpha',
    version: 1,
    market: 'crypto',
    symbols: ['BTCUSDT'],
    timeframes: { entry: 'M15', confirm: 'H1', regime: 'H4' },
    type: 'market_structure',
    parameters: {
      source_paper_id: 'paper-1',
      source_hypothesis_id: 'hyp-1',
      research_confidence: 0.7,
    },
  });
  fs.mkdirSync(path.join(root, 'research_lab', 'data'), { recursive: true });
  fs.writeFileSync(path.join(root, 'research_lab', 'data', 'paper_store.jsonl'), `${JSON.stringify({ paper_id: 'paper-1', title: 'Alpha Paper' })}\n`);
  writeJson(path.join(root, 'research_lab', 'hypotheses', 'hyp-1.json'), {
    hypothesis_id: 'hyp-1',
    source_paper_id: 'paper-1',
    strategy_family: 'order_flow_liquidity',
    regime: 'market_microstructure',
  });
  writeJson(path.join(root, 'strategy_lab', 'reports', 'walk_forward', 'alpha_btcusdt_walk_forward.json'), {
    strategy_name: 'alpha',
    symbol: 'BTCUSDT',
    windows: 4,
    passed_windows: 3,
    pass_rate: 0.75,
    approved_for_forward_test: true,
    gate_reasons: [],
  });
  writeJson(path.join(root, 'strategy_lab', 'registry', 'approved_strategies.json'), {
    version: 1,
    strategies: [{
      name: 'alpha',
      version: 1,
      market: 'crypto',
      symbols: ['BTCUSDT'],
      timeframes: { entry: 'M15', confirm: 'H1', regime: 'H4' },
      type: 'market_structure',
      status: 'approved',
      latest_report: { approved_for_forward_test: true, windows: 4, passed_windows: 3, pass_rate: 0.75, gate_reasons: [] },
    }],
  });
  writeJson(path.join(root, 'strategy_lab', 'shadow', 'deployments.json'), {
    version: 1,
    deployments: [{ id: 'crypto:alpha:v1', strategy_name: 'alpha', status: 'active', mode: 'testnet_shadow' }],
  });
  fs.mkdirSync(path.join(root, 'strategy_lab', 'reviews'), { recursive: true });
  fs.writeFileSync(
    path.join(root, 'strategy_lab', 'reviews', 'research_os_reviews.jsonl'),
    `${JSON.stringify({ created_at: '2026-06-22T00:00:00.000Z', source: 'mads', status: 'completed', output: 'ok' })}\n`,
  );
  buildExecutionHandoffManifest(root);
  createManualEnableRequest(root);
  recordManualApprovalDecision(root, { decision: 'approve', operator: 'operator', reason: 'ok' });
  const calls = [];
  const dispatchControlCommand = async (_getSettings, command) => {
    calls.push(command);
    return { ok: true, status: 200, data: { staged: true } };
  };

  const result = await executeStagedDispatch(root, { confirm: 'STAGE_DEMO_TESTNET' }, {
    getSettings: () => ({ tradingControl: {} }),
    dispatchControlCommand,
  });

  assert.equal(result.accepted, true);
  assert.equal(result.order_execution, 'disabled');
  assert.deepEqual(calls.map((item) => item.action), ['pause', 'set-risk-policy']);
  assert.equal(calls[0].engineId, 'crypto-ai');
  assert.equal(calls[1].payload.max_positions, 1);
  assert.equal(calls.some((item) => item.action === 'resume'), false);
});
