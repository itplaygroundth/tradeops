import fetch from 'node-fetch';

function nowIso() {
  return new Date().toISOString();
}

function trimText(text, max = 2000) {
  const value = String(text || '');
  return value.length > max ? `${value.slice(0, max - 3)}...` : value;
}

export function ensureNotificationSchema(db) {
  db.exec(`
    CREATE TABLE IF NOT EXISTS notification_audit (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      created_at TEXT NOT NULL,
      type TEXT NOT NULL,
      channel TEXT NOT NULL,
      status TEXT NOT NULL,
      message TEXT NOT NULL DEFAULT '',
      error TEXT NOT NULL DEFAULT '',
      meta TEXT NOT NULL DEFAULT '{}'
    );
  `);
}

export function createNotificationService({ db, getSettings }) {
  ensureNotificationSchema(db);

  function record(entry) {
    db.prepare(`
      INSERT INTO notification_audit (created_at, type, channel, status, message, error, meta)
      VALUES (?, ?, ?, ?, ?, ?, ?)
    `).run(
      entry.createdAt || nowIso(),
      entry.type || 'general',
      entry.channel,
      entry.status,
      trimText(entry.message),
      trimText(entry.error || '', 1000),
      JSON.stringify(entry.meta || {}),
    );
  }

  async function sendTelegramMessage(text, customToken = null, customChatId = null, meta = {}) {
    let token = customToken;
    let chatId = customChatId;

    if (!token || !chatId) {
      try {
        const currentSettings = getSettings();
        token = currentSettings.telegramBotToken;
        chatId = currentSettings.telegramChatId;
      } catch (_) {}
    }

    if (!token || !chatId) {
      record({ ...meta, channel: 'telegram', status: 'skipped', message: text, error: 'Telegram not configured' });
      console.log("Telegram not configured. Log: ", text);
      return false;
    }

    try {
      const url = `https://api.telegram.org/bot${token}/sendMessage`;
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chat_id: chatId, text, parse_mode: 'Markdown' }),
      });
      const result = await response.json().catch(() => ({}));
      const ok = Boolean(response.ok && result.ok);
      record({
        ...meta,
        channel: 'telegram',
        status: ok ? 'success' : 'failed',
        message: text,
        error: ok ? '' : (result.description || `Telegram HTTP ${response.status}`),
      });
      return ok;
    } catch (error) {
      record({ ...meta, channel: 'telegram', status: 'failed', message: text, error: error.message });
      console.error("Error sending Telegram message:", error);
      return false;
    }
  }

  async function sendLineMessage(text, customChannelAccessToken = null, customTargetId = null, customNotifyToken = null, meta = {}) {
    let channelAccessToken = customChannelAccessToken;
    let targetId = customTargetId;
    let notifyToken = customNotifyToken;

    if ((!channelAccessToken || !targetId) && !notifyToken) {
      try {
        const currentSettings = getSettings();
        channelAccessToken = currentSettings.lineChannelAccessToken;
        targetId = currentSettings.lineTargetId;
        notifyToken = currentSettings.lineNotifyToken;
      } catch (_) {}
    }

    try {
      if (channelAccessToken && targetId) {
        const response = await fetch('https://api.line.me/v2/bot/message/push', {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${channelAccessToken}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ to: targetId, messages: [{ type: 'text', text }] }),
        });
        const ok = response.ok;
        const body = ok ? {} : await response.json().catch(() => ({}));
        record({
          ...meta,
          channel: 'line',
          status: ok ? 'success' : 'failed',
          message: text,
          error: ok ? '' : (body.message || `LINE HTTP ${response.status}`),
          meta: { ...(meta.meta || {}), provider: 'messaging_api' },
        });
        return ok;
      }

      if (notifyToken) {
        const response = await fetch('https://notify-api.line.me/api/notify', {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${notifyToken}`,
            'Content-Type': 'application/x-www-form-urlencoded',
          },
          body: new URLSearchParams({ message: text }),
        });
        const ok = response.ok;
        const body = ok ? {} : await response.json().catch(() => ({}));
        record({
          ...meta,
          channel: 'line',
          status: ok ? 'success' : 'failed',
          message: text,
          error: ok ? '' : (body.message || `LINE Notify HTTP ${response.status}`),
          meta: { ...(meta.meta || {}), provider: 'notify' },
        });
        return ok;
      }
    } catch (error) {
      record({ ...meta, channel: 'line', status: 'failed', message: text, error: error.message });
      console.error("Error sending LINE message:", error);
      return false;
    }

    record({ ...meta, channel: 'line', status: 'skipped', message: text, error: 'LINE not configured' });
    console.log("LINE not configured. Log: ", text);
    return false;
  }

  async function sendChannels({ text, settings = null, type = 'general', meta = {} }) {
    const config = settings || getSettings();
    const [telegram, line] = await Promise.all([
      sendTelegramMessage(text, config.telegramBotToken, config.telegramChatId, { type, meta }),
      sendLineMessage(text, config.lineChannelAccessToken, config.lineTargetId, config.lineNotifyToken, { type, meta }),
    ]);
    return { telegram, line };
  }

  function recent(limit = 50) {
    const rows = db.prepare(`
      SELECT * FROM notification_audit
      ORDER BY created_at DESC, id DESC
      LIMIT ?
    `).all(Math.max(1, Math.min(Number(limit) || 50, 200)));
    return rows.map((row) => ({ ...row, meta: JSON.parse(row.meta || '{}') }));
  }

  function status() {
    const settings = getSettings();
    const rows = recent(20);
    return {
      configured: {
        telegram: Boolean(settings.telegramBotToken && settings.telegramChatId),
        line: Boolean((settings.lineChannelAccessToken && settings.lineTargetId) || settings.lineNotifyToken),
      },
      latest: rows[0] || null,
      recent: rows,
    };
  }

  return { record, sendTelegramMessage, sendLineMessage, sendChannels, recent, status };
}

export function installNotificationRoutes(app, { notifications }) {
  app.get('/api/notifications/status', (req, res) => {
    try {
      res.json(notifications.status());
    } catch (err) {
      res.status(500).json({ error: err.message });
    }
  });

  app.get('/api/notifications/audit', (req, res) => {
    try {
      res.json({ items: notifications.recent(req.query.limit) });
    } catch (err) {
      res.status(500).json({ error: err.message });
    }
  });
}
