import assert from 'node:assert/strict';
import test from 'node:test';

import { listDashboardVersions } from './dashboardVersions.js';

test('dashboard version registry exposes Research OS as prototype v1', () => {
  const registry = listDashboardVersions();
  const researchOs = registry.versions.find((item) => item.id === 'research-os-prototype-v1');

  assert.equal(registry.status, 'ready');
  assert.ok(researchOs);
  assert.equal(researchOs.status, 'prototype');
  assert.equal(researchOs.tab, 'research-os');
  assert.equal(researchOs.safetyProfile.execution, 'disabled_by_default');
  assert.equal(researchOs.safetyProfile.requiresManualApproval, true);
  assert.ok(researchOs.modules.includes('staged_dispatch'));
});
