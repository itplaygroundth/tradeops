// madsBridge.js — OpenAI-compatible endpoint so MADS dispatchHttp can talk to tradeops.
// Commands in the prompt: "pause mtai|crypto-ai", "resume mtai|crypto-ai", anything else → overview.

function chatReply(text) {
  return {
    id: `tradeops-${Date.now()}`,
    object: 'chat.completion',
    choices: [{ index: 0, message: { role: 'assistant', content: text }, finish_reason: 'stop' }],
  };
}

function summarizeOverview(overview) {
  const lines = [`Trading overview @ ${overview.timestamp}`];
  for (const e of overview.engines) {
    lines.push(`- ${e.name} (${e.id}): ${e.status}${e.error ? ` — ${e.error}` : ''}`);
    if (e.status === 'online') {
      const p = e.portfolio || {};
      if (p.balance != null) lines.push(`    balance=${p.balance} equity=${p.equity ?? '-'} openPositions=${(e.positions || []).length}`);
      for (const r of (e.recommendations || []).slice(0, 3)) {
        const msg = typeof r === 'string' ? r : `[${r.severity}] ${r.action}: ${r.reason}`;
        lines.push(`    rec: ${msg}`);
      }
    }
  }
  return lines.join('\n');
}

export function installMadsBridgeRoutes(app, { db, getSettings, collectTradingOverview, dispatchControlCommand, recordControlAction }) {
  app.post('/v1/chat/completions', async (req, res) => {
    try {
      const messages = req.body?.messages || [];
      const prompt = (messages[messages.length - 1]?.content || '').trim().toLowerCase();

      const cmd = prompt.match(/\b(pause|resume)\s+(mtai|crypto-ai)\b/);
      if (cmd) {
        const [, action, engineId] = cmd;
        const result = await dispatchControlCommand(getSettings, { engineId, action, payload: {} });
        recordControlAction(db, {
          engineId, action,
          status: result.ok ? 'ok' : 'error',
          reason: 'mads-dispatch',
          payload: {},
          result,
        });
        return res.json(chatReply(`${action} ${engineId}: ${result.ok ? 'OK' : `FAILED — ${result.error}`}`));
      }

      const overview = await collectTradingOverview(getSettings);
      return res.json(chatReply(summarizeOverview(overview)));
    } catch (err) {
      return res.status(500).json({ error: { message: err.message } });
    }
  });
}
