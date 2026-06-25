const state = {
  research: null,
  settings: null,
  notifications: null,
  proposals: [],
  experiments: [],
  agents: null,
  algotraderQa: null,
  busy: false,
  ui: {
    theme: localStorage.getItem('researchOsTheme') || 'trading-floor',
    sidebarCollapsed: localStorage.getItem('researchOsSidebarCollapsed') === 'true',
  },
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

function text(value, fallback = '-') {
  if (value === null || value === undefined || value === '') return fallback;
  return String(value);
}

function setToast(message, tone = 'good') {
  const toast = $('#toast');
  toast.textContent = message;
  toast.className = `toast ${tone}`;
  clearTimeout(setToast.timer);
  setToast.timer = setTimeout(() => toast.classList.add('hidden'), 6000);
}

function setApiStatus(ok, label) {
  $('#apiDot').className = `dot ${ok ? 'good' : 'bad'}`;
  $('#apiStatus').textContent = label;
  const strip = $('#stripApi');
  if (strip) strip.textContent = ok ? 'online' : 'offline';
}

function applyUiPreferences() {
  document.body.dataset.theme = state.ui.theme;
  document.body.classList.toggle('sidebar-collapsed', state.ui.sidebarCollapsed);
  $$('.theme-option').forEach((button) => {
    button.classList.toggle('active', button.dataset.themeChoice === state.ui.theme);
  });
  const toggle = $('#sidebarToggle');
  if (toggle) {
    toggle.textContent = state.ui.sidebarCollapsed ? '→' : '←';
    toggle.setAttribute('aria-label', state.ui.sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar');
    toggle.setAttribute('title', state.ui.sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar');
  }
}

function setTheme(theme) {
  state.ui.theme = theme;
  localStorage.setItem('researchOsTheme', theme);
  applyUiPreferences();
}

function toggleSidebar() {
  state.ui.sidebarCollapsed = !state.ui.sidebarCollapsed;
  localStorage.setItem('researchOsSidebarCollapsed', String(state.ui.sidebarCollapsed));
  applyUiPreferences();
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    ...options,
    headers: {
      'content-type': 'application/json',
      ...(options.headers || {}),
    },
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const error = new Error(data.error || data.detail || `HTTP ${res.status}`);
    error.data = data;
    error.status = res.status;
    throw error;
  }
  return data;
}

function metric(label, value, tone = '') {
  return `<div class="metric">
    <div class="metric-label">${label}</div>
    <div class="metric-value ${tone}">${text(value)}</div>
  </div>`;
}

function metricTone(label, value) {
  const key = String(label).toLowerCase();
  const raw = String(value ?? '').toUpperCase();
  const numeric = Number(value);
  if (raw.includes('BLOCK') || raw.includes('REJECT') || raw.includes('HARD') || raw.includes('FAILED')) return 'bad-text';
  if (raw.includes('NEEDS_TUNING') || raw.includes('CAUTION')) return 'tune-text';
  if (raw.includes('READY') || raw.includes('PASS') || raw.includes('APPROVED')) return 'good-text';
  if (raw.includes('DISABLED') || raw.includes('PENDING') || raw.includes('WAIT')) return 'warn-text';
  if (key.includes('paper') || key.includes('hyp') || key.includes('registry') || key.includes('signal')) return 'info-text';
  if (key.includes('risk') && numeric > 0) return 'bad-text';
  if (numeric > 0) return 'good-text';
  return 'num-neutral';
}

function semanticPill(value) {
  const raw = String(value ?? '').toUpperCase();
  if (raw.includes('PASS') || raw.includes('READY') || raw.includes('APPROVED')) return 'good';
  if (raw.includes('BLOCK') || raw.includes('FAIL') || raw.includes('REJECT')) return 'bad';
  if (raw.includes('NEEDS_TUNING') || raw.includes('TUNE')) return 'tune';
  if (raw.includes('DISABLED') || raw.includes('PENDING') || raw.includes('CAUTION')) return 'warn';
  if (raw.includes('INFO') || raw.includes('REVIEW') || raw.includes('SHADOW')) return 'info';
  return 'muted';
}

function verdictTextClass(verdict) {
  const raw = String(verdict || '').toUpperCase();
  if (raw.includes('PASS')) return 'good-text';
  if (raw.includes('BLOCK') || raw.includes('FAIL')) return 'bad-text';
  if (raw.includes('NEEDS_TUNING') || raw.includes('TUNE')) return 'tune-text';
  return 'warn-text';
}

function renderSummary() {
  const research = state.research?.researchLab || {};
  const strategy = state.research?.strategyLab || {};
  const live = strategy.liveReadiness || {};
  const shadowMetrics = strategy.shadowMetrics || strategy.shadow_metrics || {};
  $('#summaryMetrics').innerHTML = [
    metric('Papers', research.papers?.stored || 0, 'info-text'),
    metric('Hypotheses', research.hypotheses?.count || 0, 'info-text'),
    metric('Registry', strategy.registry?.total || 0, 'num-blue'),
    metric('Passed Runs', strategy.batch?.passedRuns || 0, metricTone('Passed Runs', strategy.batch?.passedRuns || 0)),
    metric('Shadow Active', strategy.shadow?.active || 0, (strategy.shadow?.active || 0) > 0 ? 'good-text' : 'warn-text'),
    metric('Shadow Signals', shadowMetrics.signals || 0, 'num-blue'),
    metric('Live Readiness', live.status || 'BLOCKED', metricTone('Live Readiness', live.status || 'BLOCKED')),
    metric('Dispatch Plan', strategy.dispatchPlan?.status || 'none', metricTone('Dispatch Plan', strategy.dispatchPlan?.status || 'none')),
  ].join('');

  $('#readinessStatus').textContent = live.status || 'BLOCKED';
  $('#readinessStatus').className = `pill ${semanticPill(live.status || 'BLOCKED')}`;
  const blockers = live.blockers || [];
  const warnings = live.warnings || [];
  $('#readinessBody').innerHTML = [
    `<div>Ready for shadow: <strong>${live.readyForShadow || 0}</strong></div>`,
    `<div>Ready for limited live review: <strong>${live.readyForLimitedLiveReview || 0}</strong></div>`,
    `<div>Strategies evaluated: <strong>${live.total || 0}</strong></div>`,
    blockers.length ? `<div class="bad">Blockers: ${blockers.join('; ')}</div>` : '<div>Blockers: none</div>',
    warnings.length ? `<div class="warn">Warnings: ${warnings.join('; ')}</div>` : '',
  ].filter(Boolean).join('');

  const review = strategy.latestReview;
  $('#reviewSource').textContent = review?.source || 'none';
  $('#reviewSource').className = `pill ${review ? 'good' : 'muted'}`;
  $('#reviewOutput').textContent = review?.output || review?.reason || 'No review yet.';
}

function renderLineage() {
  const lineage = state.research?.strategyLab?.lineage?.items || [];
  $('#lineageRows').innerHTML = lineage.length ? lineage.map((item) => `
    <tr>
      <td><strong>${text(item.strategy)}</strong><br><span class="small">${text(item.type)} · ${(item.symbols || []).join(', ')}</span></td>
      <td>${text(item.stage)}</td>
      <td>${item.batch?.passed || 0}/${item.batch?.runs || 0}</td>
      <td>${item.walk_forward?.approved || 0}/${item.walk_forward?.reports || 0}</td>
      <td>${item.shadow?.active || 0}/${item.shadow?.deployments || 0}</td>
      <td>${(item.risk_flags || []).join('; ') || '-'}</td>
    </tr>
  `).join('') : '<tr><td colspan="6">No strategy lineage yet.</td></tr>';
}

function renderApproval() {
  const strategy = state.research?.strategyLab || {};
  const plan = strategy.dispatchPlan;
  const dispatch = strategy.stagedDispatch;
  $('#dispatchPlan').innerHTML = plan ? [
    `<div>ID: <strong>${text(plan.id)}</strong></div>`,
    `<div>Status: <strong>${text(plan.status)}</strong></div>`,
    `<div>Engine dispatch: <strong>${text(plan.engine_dispatch)}</strong></div>`,
    `<div>Order execution: <strong>${text(plan.order_execution)}</strong></div>`,
    `<div>Strategies: <strong>${(plan.strategies || []).length}</strong></div>`,
    `<div>Next: ${text(plan.next_required_action)}</div>`,
  ].join('') : '<div>No staged dispatch plan yet.</div>';

  $('#stagedDispatch').innerHTML = dispatch ? [
    `<div>Status: <strong>${text(dispatch.status)}</strong></div>`,
    `<div>Accepted: <strong>${dispatch.accepted ? 'yes' : 'no'}</strong></div>`,
    `<div>Engine dispatch: <strong>${text(dispatch.engine_dispatch)}</strong></div>`,
    `<div>Order execution: <strong>${text(dispatch.order_execution)}</strong></div>`,
    `<div>Commands: <strong>${(dispatch.commands || []).length}</strong></div>`,
    (dispatch.blockers || []).length ? `<div class="bad">Blockers: ${dispatch.blockers.join('; ')}</div>` : '<div>Blockers: none</div>',
  ].join('') : '<div>No staged dispatch attempt yet.</div>';
}

function pct(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-';
  return `${Number(value).toFixed(2)}%`;
}

function toneForVerdict(verdict) {
  if (!verdict) return 'warn';
  const raw = String(verdict).toUpperCase();
  if (raw.includes('PASS')) return 'up';
  if (raw.includes('NEEDS_TUNING') || raw.includes('TUNE')) return 'tune';
  if (raw.includes('BLOCK') || raw.includes('FAIL')) return 'down';
  return 'warn';
}

function renderTickerTape() {
  const strategy = state.research?.strategyLab || {};
  const research = state.research?.researchLab || {};
  const live = strategy.liveReadiness || {};
  const agents = state.agents?.agents || [];
  const latest = state.agents?.selection?.latest_experiment || state.experiments[0];
  const readyAgents = agents.filter((agent) => agent.status === 'ready').length;
  const selectors = agents.filter((agent) => agent.can_select_strategy).length;
  const items = [
    ['AGENTS', `${readyAgents}/${agents.length || 0}`, readyAgents ? 'up' : 'warn'],
    ['SELECTORS', selectors, selectors ? 'info' : 'warn'],
    ['EXEC', state.agents?.selection?.order_execution || 'disabled', 'warn'],
    ['PAPERS', research.papers?.stored || 0, 'info'],
    ['HYP', research.hypotheses?.count || 0, 'info'],
    ['REGISTRY', strategy.registry?.total || 0, 'info'],
    ['SHADOW', strategy.shadow?.active || 0, (strategy.shadow?.active || 0) ? 'up' : 'warn'],
    ['READINESS', live.status || 'BLOCKED', live.status === 'READY_FOR_LIMITED_LIVE_REVIEW' ? 'up' : 'down'],
    ['LATEST', latest?.verdict || latest?.evaluation?.verdict || 'none', toneForVerdict(latest?.verdict || latest?.evaluation?.verdict)],
  ];
  const html = [...items, ...items].map(([key, value, tone]) => `
    <span class="ticker-item">
      <span class="ticker-key">${key}</span>
      <span class="ticker-${tone}">${text(value)}</span>
    </span>
  `).join('');
  const track = $('#tickerTrack');
  if (track) track.innerHTML = html;
}

function renderStatusStrip() {
  const agents = state.agents?.agents || [];
  const readyAgents = agents.filter((agent) => agent.status === 'ready').length;
  const latest = state.agents?.selection?.latest_experiment || state.experiments[0];
  const execution = state.agents?.selection?.order_execution || 'disabled_in_research_os';
  const stripExecution = $('#stripExecution');
  const stripVerdict = $('#stripVerdict');
  const stripAgents = $('#stripAgents');
  if (stripExecution) {
    stripExecution.textContent = execution.replaceAll('_', ' ');
    stripExecution.className = execution.includes('disabled') ? 'num-yellow' : 'num-red';
  }
  if (stripVerdict) {
    const verdict = latest?.verdict || latest?.evaluation?.verdict || 'none';
    stripVerdict.textContent = verdict;
    stripVerdict.className = verdictTextClass(verdict);
  }
  if (stripAgents) {
    stripAgents.textContent = `${readyAgents}/${agents.length || 0}`;
    stripAgents.className = readyAgents ? 'num-green' : 'num-yellow';
  }
}

function renderTradingFloor() {
  renderStatusStrip();
  renderTickerTape();
  const agents = state.agents?.agents || [];
  const floor = $('#agentFloor');
  if (floor) {
    floor.innerHTML = agents.length ? agents.slice(0, 8).map((agent) => {
      const status = agent.status === 'ready' ? 'good' : agent.status === 'idle' ? 'warn' : 'bad';
      return `
        <div class="floor-tile">
          <div class="floor-title">
            <span>${text(agent.name)}</span>
            <span class="pulse-dot ${status}"></span>
          </div>
          <div class="floor-role">${text(agent.role)}</div>
          <div class="floor-meta">
            <span>${agent.can_select_strategy ? 'selector' : 'observer'}</span>
            <span>${agent.latest_at ? new Date(agent.latest_at).toLocaleTimeString('th-TH', { timeZone: 'Asia/Bangkok' }) : '--:--'}</span>
          </div>
        </div>
      `;
    }).join('') : '<div class="small">Waiting for agent telemetry.</div>';
  }

  const rows = $('#activityTape');
  if (rows) {
    const experiments = state.experiments.slice(0, 8);
    rows.innerHTML = experiments.length ? experiments.map((item) => {
      const verdict = item.evaluation?.verdict || 'unknown';
      const cls = verdictTextClass(verdict);
      return `
        <div class="activity-row">
          <div class="activity-time">${new Date(item.created_at).toLocaleTimeString('th-TH', { timeZone: 'Asia/Bangkok' })}</div>
          <div class="activity-main">${text(item.proposal?.name)} · ${text(item.symbol)} · ${verdict}</div>
          <div class="activity-score ${cls}">${text(item.evaluation?.score)}</div>
        </div>
      `;
    }).join('') : '<div class="small">No experiment tape yet.</div>';
  }

  const pulse = $('#activityPulse');
  if (pulse) {
    const latestVerdict = state.experiments[0]?.evaluation?.verdict;
    pulse.textContent = latestVerdict || 'idle';
    pulse.className = `pill ${semanticPill(latestVerdict || 'idle')}`;
  }
}

function renderExperimentOptions() {
  const select = $('#experimentProposal');
  if (!select) return;
  select.innerHTML = state.proposals.length ? state.proposals.map((item) => `
    <option value="${item.id}">${item.name} · ${item.type} · ${(item.symbols || []).join(', ')}</option>
  `).join('') : '<option value="strategies/btc_eth_mean_reversion_v1.json">btc_eth_mean_reversion_v1</option>';
}

function stressSummary(experiment) {
  const stress = experiment.results?.stress || {};
  return Object.entries(stress).map(([regime, item]) => {
    const report = item.report || {};
    const ok = report.approved_for_forward_test;
    const pfOk = Number(report.profit_factor || 0) >= 1.15;
    return `${regime}: <span class="${ok ? 'good-text' : 'bad-text'}">${ok ? 'PASS' : 'BLOCK'}</span> PF <span class="${pfOk ? 'good-text' : 'bad-text'}">${text(report.profit_factor)}</span>`;
  }).join(' | ') || '-';
}

function renderExperiments() {
  renderExperimentOptions();
  const rows = $('#experimentRows');
  if (!rows) return;
  rows.innerHTML = state.experiments.length ? state.experiments.map((item) => {
    const baseline = item.results?.candidate_baseline?.report || item.results?.baseline?.report || {};
    const baselineSource = item.results?.candidate_baseline ? 'candidate' : 'raw';
    const optimization = item.results?.optimization || {};
    const verdict = item.evaluation?.verdict || 'unknown';
    const verdictClass = verdictTextClass(verdict);
    const pfClass = Number(baseline.profit_factor || 0) >= 1.15 ? 'good-text' : 'bad-text';
    const expClass = Number(baseline.expectancy_pct || 0) > 0 ? 'good-text' : 'bad-text';
    return `
      <tr>
        <td>${new Date(item.created_at).toLocaleString('th-TH', { timeZone: 'Asia/Bangkok' })}</td>
        <td><strong>${text(item.proposal?.name)}</strong><br><span class="small">${text(item.proposal?.type)} · ${text(item.proposal?.timeframe)}</span></td>
        <td>${text(item.symbol)}</td>
        <td>${baseline.approved_for_forward_test ? '<span class="good-text">PASS</span>' : '<span class="bad-text">BLOCK</span>'}<br><span class="small">${baselineSource} · PF <span class="${pfClass}">${text(baseline.profit_factor)}</span> · EXP <span class="${expClass}">${pct(baseline.expectancy_pct)}</span></span></td>
        <td>${optimization.passed ? '<span class="good-text">PASS</span>' : '<span class="tune-text">TUNE</span>'}<br><span class="small">code ${text(optimization.step?.code)}</span></td>
        <td><span class="small">${stressSummary(item)}</span></td>
        <td><span class="${verdictClass}">${verdict}</span><br><span class="small">score ${text(item.evaluation?.score)}</span></td>
        <td><span class="small">${text(item.evaluation?.summary_th)} ${(item.evaluation?.blockers || []).join('; ')}</span></td>
      </tr>
    `;
  }).join('') : '<tr><td colspan="8">No experiment runs yet.</td></tr>';
}

function statusClass(status) {
  if (status === 'ready' || status === 'online') return 'good';
  if (status === 'blocked' || status === 'failed') return 'bad';
  if (status === 'running' || status === 'warning') return 'warn';
  return 'muted';
}

function renderAgents() {
  const payload = state.agents || {};
  const agents = payload.agents || [];
  const ready = agents.filter((agent) => agent.status === 'ready').length;
  const selectors = agents.filter((agent) => agent.can_select_strategy).length;
  const executors = agents.filter((agent) => agent.can_execute_orders).length;
  const latest = payload.selection?.latest_experiment;
  const metrics = $('#agentMetrics');
  if (!metrics) return;
  metrics.innerHTML = [
    metric('Agents Ready', `${ready}/${agents.length}`, ready ? 'good-text' : ''),
    metric('Strategy Selectors', selectors, selectors ? 'num-blue' : 'warn-text'),
    metric('Order Executors', executors, executors ? 'bad-text' : 'good-text'),
    metric('Latest Verdict', latest?.verdict || 'none', verdictTextClass(latest?.verdict || 'none')),
  ].join('');

  $('#agentWorkbenchStatus').textContent = payload.status || 'unknown';
  $('#agentWorkbenchStatus').className = `pill ${semanticPill(payload.status || 'unknown')}`;
  $('#agentCards').innerHTML = agents.length ? agents.map((agent) => {
    const evidence = (agent.evidence || []).map((item) => `${item.exists ? 'OK' : 'MISS'} ${item.path}${item.updated_at ? ` @ ${new Date(item.updated_at).toLocaleString('th-TH', { timeZone: 'Asia/Bangkok' })}` : ''}`);
    return `
      <div class="agent-card">
        <div class="agent-top">
          <div>
            <div class="agent-name">${text(agent.name)}</div>
            <div class="agent-role">${text(agent.role)}</div>
          </div>
          <span class="pill ${statusClass(agent.status)}">${text(agent.status)}</span>
        </div>
        <div class="small">Mode: <strong>${text(agent.mode)}</strong> · Select strategy: <strong>${agent.can_select_strategy ? 'yes' : 'no'}</strong> · Execute orders: <strong>${agent.can_execute_orders ? 'yes' : 'no'}</strong></div>
        <div class="agent-evidence">${evidence.join('<br>') || 'No evidence files yet.'}</div>
      </div>
    `;
  }).join('') : '<div class="small">No agent status available.</div>';

  $('#selectionMode').textContent = payload.selection?.mode || 'unknown';
  $('#selectionMode').className = 'pill info';
  $('#selectionState').innerHTML = [
    `<div>Selection enabled: <strong>${payload.selection?.enabled ? 'yes' : 'no'}</strong></div>`,
    `<div>Order execution: <strong class="${payload.selection?.order_execution === 'disabled_in_research_os' ? 'good-text' : 'bad-text'}">${text(payload.selection?.order_execution)}</strong></div>`,
    latest ? `<div>Latest experiment: <strong>${latest.id}</strong></div>` : '<div>Latest experiment: none</div>',
    latest ? `<div>Strategy: <strong>${text(latest.strategy)}</strong> · Symbol: <strong>${text(latest.symbol)}</strong></div>` : '',
    latest ? `<div>Verdict: <strong>${text(latest.verdict)}</strong> · Score: <strong>${text(latest.score)}</strong></div>` : '',
    latest ? `<div>Selected for shadow review: <strong>${latest.selected_for_shadow_review ? 'yes' : 'no'}</strong></div>` : '',
    `<div>${text(payload.selection?.note)}</div>`,
  ].filter(Boolean).join('');
}

function renderAlgotraderQa() {
  const qa = state.algotraderQa;
  const status = $('#algotraderQaStatus');
  if (!status) return;
  if (!qa) {
    status.textContent = 'loading';
    status.className = 'pill muted';
    return;
  }
  status.textContent = qa.status || 'unknown';
  status.className = `pill ${semanticPill(qa.status || 'unknown')}`;
  $('#algotraderQaMetrics').innerHTML = [
    metric('QA Passed', `${qa.summary?.passed || 0}/${qa.summary?.total || 0}`, qa.summary?.failed ? 'bad-text' : qa.summary?.warnings ? 'warn-text' : 'good-text'),
    metric('Warnings', qa.summary?.warnings || 0, qa.summary?.warnings ? 'warn-text' : 'good-text'),
    metric('Failed Gates', qa.summary?.failed || 0, qa.summary?.failed ? 'bad-text' : 'good-text'),
    metric('Safe Action', qa.review_agent?.safe_action || 'unknown', metricTone('Safe Action', qa.review_agent?.safe_action || 'unknown')),
  ].join('');
  $('#algotraderChecklist').innerHTML = (qa.checklist || []).map((item) => `
    <div class="qa-card ${item.passed ? 'pass' : item.severity}">
      <div class="qa-card-head">
        <strong>${text(item.label)}</strong>
        <span class="pill ${item.passed ? 'good' : semanticPill(item.severity)}">${item.passed ? 'PASS' : text(item.severity).toUpperCase()}</span>
      </div>
      <div class="small">${text(item.detail)}</div>
    </div>
  `).join('');
  const parity = qa.parity || {};
  $('#algotraderParity').innerHTML = [
    `<strong>Backtest-Live Parity</strong>`,
    `Status: <span class="${metricTone('parity', parity.status)}">${text(parity.status)}</span>`,
    `Strategy: ${text(parity.strategy)} · Symbol: ${text(parity.symbol)} · TF: ${text(parity.timeframe)}`,
    `Baseline: trades ${text(parity.baseline?.trades)} · PF ${text(parity.baseline?.profit_factor)} · EXP ${pct(parity.baseline?.expectancy_pct)} · DD ${pct(parity.baseline?.max_drawdown_pct)}`,
    `Evidence: timeframe ${parity.evidence?.has_timeframe ? 'yes' : 'no'} · risk ${parity.evidence?.has_risk_model ? 'yes' : 'no'} · costs ${parity.evidence?.has_cost_model ? 'yes' : 'no'} · attribution ${parity.evidence?.has_signal_attribution ? 'yes' : 'no'}`,
  ].join('<br>');
  $('#algotraderAttribution').innerHTML = [
    `<strong>Signal Attribution Schema</strong>`,
    (qa.attribution_schema?.required_fields || []).map((field) => `<code>${field}</code>`).join(' '),
    `<br><br><strong>Review Agent</strong>`,
    `Mode: ${text(qa.review_agent?.mode)}`,
    qa.parity?.stress_guard ? `Stress guard: ${text(qa.parity.stress_guard.status)} · allow ${text((qa.parity.stress_guard.allowed_regimes || []).join(', '), 'none')} · block ${text((qa.parity.stress_guard.no_trade_regimes || []).map((item) => item.regime).join(', '), 'none')}` : '',
    `Next: ${(qa.review_agent?.next_steps || []).join('<br>') || text(qa.summary?.recommendation)}`,
  ].filter(Boolean).join('<br>');
}

function renderSettings() {
  const settings = state.settings || {};
  $('#telegramBotToken').value = settings.telegramBotToken || '';
  $('#telegramChatId').value = settings.telegramChatId || '';
  $('#lineChannelAccessToken').value = settings.lineChannelAccessToken || '';
  $('#lineTargetId').value = settings.lineTargetId || '';
  $('#lineNotifyToken').value = settings.lineNotifyToken || '';
  $('#dailyReportTime').value = settings.tradingControl?.dailyReportTime || '08:00';
  $('#autoSendDailyReport').checked = Boolean(settings.tradingControl?.autoSendDailyReport);

  const configured = state.notifications?.configured || {};
  const ready = configured.telegram || configured.line;
  $('#notificationReady').textContent = ready ? 'ready' : 'not configured';
  $('#notificationReady').className = `pill ${ready ? 'good' : 'warn'}`;
  const recent = state.notifications?.recent || [];
  $('#notificationAudit').innerHTML = [
    `<div>Telegram: <strong>${configured.telegram ? 'ready' : 'off'}</strong></div>`,
    `<div>LINE: <strong>${configured.line ? 'ready' : 'off'}</strong></div>`,
    state.notifications?.dailyReport?.nextDueAt ? `<div>Next daily: ${new Date(state.notifications.dailyReport.nextDueAt).toLocaleString('th-TH', { timeZone: 'Asia/Bangkok' })}</div>` : '',
    '<hr>',
    ...recent.slice(0, 6).map((item) => `<div>${text(item.created_at || item.sent_at)} · ${text(item.channel)} · ${text(item.status)}</div>`),
  ].filter(Boolean).join('');
}

function renderAll() {
  renderStatusStrip();
  renderSummary();
  renderLineage();
  renderApproval();
  renderExperiments();
  renderAgents();
  renderAlgotraderQa();
  renderTradingFloor();
  renderSettings();
}

async function refreshExperiments(silent = false) {
  try {
    const [proposals, experiments, agents, algotraderQa] = await Promise.all([
      api('/api/experiments/proposals'),
      api('/api/experiments'),
      api('/api/experiments/agents/status'),
      api('/api/experiments/algotrader-qa'),
    ]);
    state.proposals = proposals.items || [];
    state.experiments = experiments.items || [];
    state.agents = agents;
    state.algotraderQa = algotraderQa;
    renderExperiments();
    renderAgents();
    renderAlgotraderQa();
    renderTradingFloor();
    if (!silent) setToast('Experiments refreshed');
  } catch (error) {
    if (!silent) setToast(error.message, 'bad');
  }
}

async function refreshAll(silent = false) {
  try {
    const [research, settings, notifications] = await Promise.all([
      api('/api/research-os/status'),
      api('/api/settings'),
      api('/api/notifications/status'),
    ]);
    state.research = research;
    state.settings = settings;
    state.notifications = notifications;
    setApiStatus(true, 'TradeOps API online');
    renderAll();
    await refreshExperiments(true);
    if (!silent) setToast('Dashboard refreshed');
  } catch (error) {
    setApiStatus(false, 'TradeOps API offline');
    if (!silent) setToast(error.message, 'bad');
  }
}

async function runExperiment() {
  const button = $('#runExperimentBtn');
  const status = $('#experimentStatus');
  button.disabled = true;
  status.textContent = 'running';
  status.className = 'pill warn';
  try {
    const data = await api('/api/experiments/run', {
      method: 'POST',
      body: JSON.stringify({
        proposal: $('#experimentProposal').value,
        symbol: $('#experimentSymbol').value.trim() || 'BTCUSDT',
        count: Number($('#experimentCount').value || 520),
      }),
    });
    await refreshExperiments(true);
    status.textContent = data.experiment?.evaluation?.verdict || 'completed';
    status.className = `pill ${data.experiment?.evaluation?.verdict?.includes('PASS') ? 'good' : 'warn'}`;
    setToast(`Experiment completed: ${data.experiment?.evaluation?.summary_th || 'done'}`, data.experiment?.evaluation?.verdict?.includes('PASS') ? 'good' : 'warn');
  } catch (error) {
    status.textContent = 'failed';
    status.className = 'pill bad';
    setToast(error.message, 'bad');
  } finally {
    button.disabled = false;
  }
}

async function postAction(path, body, successLabel, warningLabel = successLabel) {
  try {
    const data = await api(path, {
      method: 'POST',
      body: JSON.stringify(body || {}),
    });
    if (data.status) state.research = data.status;
    if (data.status_snapshot) state.research = data.status_snapshot;
    await refreshAll(true);
    setToast(data.accepted === false || data.created === false || data.built === 0 ? warningLabel : successLabel, data.accepted === false ? 'warn' : 'good');
  } catch (error) {
    if (error.status === 409 && error.data?.status_snapshot) {
      state.research = error.data.status_snapshot;
      renderAll();
      setToast(`Blocked: ${(error.data.blockers || []).join('; ')}`, 'warn');
      return;
    }
    setToast(error.message, 'bad');
  }
}

function activeView(view) {
  $$('.nav-item').forEach((item) => item.classList.toggle('active', item.dataset.view === view));
  $$('[data-view-panel]').forEach((panel) => panel.classList.toggle('hidden', panel.dataset.viewPanel !== view));
}

function settingsPayload() {
  const current = state.settings || {};
  return {
    telegramBotToken: $('#telegramBotToken').value.trim(),
    telegramChatId: $('#telegramChatId').value.trim(),
    lineChannelAccessToken: $('#lineChannelAccessToken').value.trim(),
    lineTargetId: $('#lineTargetId').value.trim(),
    lineNotifyToken: $('#lineNotifyToken').value.trim(),
    tradingControl: {
      ...(current.tradingControl || {}),
      dailyReportTime: $('#dailyReportTime').value || '08:00',
      autoSendDailyReport: $('#autoSendDailyReport').checked,
    },
  };
}

function bindEvents() {
  applyUiPreferences();
  $('#sidebarToggle')?.addEventListener('click', toggleSidebar);
  $$('.theme-option').forEach((button) => {
    button.addEventListener('click', () => setTheme(button.dataset.themeChoice));
  });
  $$('.nav-item').forEach((item) => item.addEventListener('click', () => activeView(item.dataset.view)));
  $('#refreshBtn').addEventListener('click', () => refreshAll(false));
  $('#runPipelineBtn').addEventListener('click', () => postAction('/api/research-os/run', { mode: 'full', maxResults: 8 }, 'Research pipeline completed'));
  $('#refreshExperimentsBtn').addEventListener('click', () => refreshExperiments(false));
  $('#experimentForm').addEventListener('submit', (event) => {
    event.preventDefault();
    runExperiment();
  });
  $('#runGatesBtn').addEventListener('click', () => postAction('/api/research-os/gates/run', { count: 10, top: 3, network: 'testnet' }, 'Strategy gates completed'));
  $('#runWalkForwardBtn').addEventListener('click', () => postAction('/api/research-os/walk-forward/run', {}, 'Walk-forward completed'));
  $('#runPromotionBtn').addEventListener('click', () => postAction('/api/research-os/promotion/run', {}, 'Promotion gate completed'));
  $('#deployShadowBtn').addEventListener('click', () => postAction('/api/research-os/shadow/deploy', { mode: 'testnet_shadow', network: 'testnet' }, 'Shadow deployment updated'));
  $('#runReviewBtn').addEventListener('click', () => postAction('/api/research-os/mads/review', { fallback: true }, 'MADS review completed'));
  $('#exportQaGuardBtn')?.addEventListener('click', () => postAction('/api/experiments/algotrader-qa/export', {}, 'AlgoTrader QA guard exported'));
  $('#buildHandoffBtn').addEventListener('click', () => postAction('/api/research-os/handoff/build', { targetMode: 'limited_live_review', maxStrategies: 3 }, 'Handoff manifest built', 'Handoff blocked'));
  $('#requestEnableBtn').addEventListener('click', () => postAction('/api/research-os/enable/request', { requestedBy: 'research-os-dashboard', reason: 'limited live review request' }, 'Manual enable request created', 'Manual enable request blocked'));
  $('#approveStageBtn').addEventListener('click', () => postAction('/api/research-os/enable/decision', { decision: 'approve', operator: 'research-os-dashboard', reason: 'approve staged dispatch' }, 'Approval recorded', 'Approval blocked'));
  $('#stageDispatchBtn').addEventListener('click', () => postAction('/api/research-os/dispatch/stage', { confirm: 'STAGE_DEMO_TESTNET' }, 'Staged controls sent; execution remains disabled', 'Staged dispatch blocked'));

  $('#settingsForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    try {
      const data = await api('/api/settings', { method: 'PUT', body: JSON.stringify(settingsPayload()) });
      state.settings = data.settings || data;
      await refreshAll(true);
      setToast('Settings saved');
    } catch (error) {
      setToast(error.message, 'bad');
    }
  });

  $('#testTelegramBtn').addEventListener('click', () => postAction('/api/telegram/test', {
    telegramBotToken: $('#telegramBotToken').value.trim(),
    telegramChatId: $('#telegramChatId').value.trim(),
  }, 'Telegram test sent'));
  $('#testLineBtn').addEventListener('click', () => postAction('/api/line/test', {
    lineChannelAccessToken: $('#lineChannelAccessToken').value.trim(),
    lineTargetId: $('#lineTargetId').value.trim(),
    lineNotifyToken: $('#lineNotifyToken').value.trim(),
  }, 'LINE test sent'));
  $('#sendDailyBtn').addEventListener('click', () => postAction('/api/trading/notifications/send-daily', { force: true }, 'Daily trade summary sent'));
}

bindEvents();
setInterval(() => {
  const clock = $('#floorClock');
  if (clock) clock.textContent = new Date().toLocaleTimeString('th-TH', { timeZone: 'Asia/Bangkok' });
}, 1000);
refreshAll(false);
setInterval(() => refreshAll(true), 15000);
