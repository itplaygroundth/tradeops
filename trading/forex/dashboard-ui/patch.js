const fs = require('fs');
let css = fs.readFileSync('src/App.css', 'utf-8');

// Replace .main, .middle-left, .agents-panel, .details-panel with new layout
css = css.replace(/\.main \{[\s\S]*?\/\* ===========/g, `
/* =========== MAIN LAYOUT (Forex Pro Style) =========== */
.main {
  flex: 1;
  display: flex;
  gap: 4px;
  padding: 4px;
  overflow: hidden;
}

.left-panel {
  width: 260px;
  min-width: 260px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  overflow-y: auto;
  border-radius: var(--radius-md);
  padding: 6px;
  background: var(--bg-secondary);
  border: 0.5px solid var(--border-subtle);
}

.center-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
  overflow: hidden;
}

.chart-area {
  flex: 1;
  background: var(--bg-card);
  border-radius: var(--radius-md);
  border: 0.5px solid var(--border-subtle);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.bottom-terminal {
  height: 280px;
  min-height: 280px;
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  border: 0.5px solid var(--border-subtle);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.terminal-header {
  padding: 6px 12px;
  background: var(--bg-card3);
  border-bottom: 0.5px solid var(--border-subtle);
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  color: var(--text-secondary);
  letter-spacing: 0.5px;
}

.terminal-content {
  flex: 1;
  display: flex;
  gap: 6px;
  padding: 6px;
  overflow-y: auto;
}

.terminal-col {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
  background: var(--bg-card);
  border-radius: var(--radius-sm);
  padding: 6px;
  border: 0.5px solid var(--border-subtle);
  overflow-y: auto;
}

.right-panel {
  width: 320px;
  min-width: 320px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  overflow-y: auto;
  border-radius: var(--radius-md);
  padding: 6px;
  background: var(--bg-secondary);
  border: 0.5px solid var(--border-subtle);
}

.panel-title {
  font-size: 11px;
  font-weight: 700;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 2px;
  display: flex;
  justify-content: space-between;
}

/* ===========`);

fs.writeFileSync('src/App.css', css);
console.log('App.css patched.');
