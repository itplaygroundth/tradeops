export const DASHBOARD_VERSIONS = [
  {
    id: 'research-os-prototype-v1',
    title: 'Research OS Prototype',
    version: 'v1',
    status: 'prototype',
    tab: 'research-os',
    route: '#research-os',
    owner: 'strategy-research',
    description: 'Standalone prototype for paper research, strategy gates, shadow deployment, MADS review, and staged dispatch controls.',
    modules: [
      'research_pipeline',
      'strategy_gate',
      'walk_forward',
      'promotion_gate',
      'shadow_signals',
      'mads_review',
      'manual_approval',
      'staged_dispatch',
    ],
    safetyProfile: {
      execution: 'disabled_by_default',
      dispatch: 'demo_testnet_controls_only',
      requiresManualApproval: true,
      failClosed: true,
    },
  },
];

export function listDashboardVersions() {
  return {
    status: 'ready',
    count: DASHBOARD_VERSIONS.length,
    versions: DASHBOARD_VERSIONS,
  };
}

export function installDashboardVersionRoutes(app) {
  app.get('/api/dashboard-versions', (_req, res) => {
    res.json(listDashboardVersions());
  });
}
